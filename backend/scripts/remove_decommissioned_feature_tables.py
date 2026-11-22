"""One-time, explicitly invoked cleanup for decommissioned feature tables.

Removes obsolete tables that were exclusive to decommissioned features:
- Voice Authenticity Check / Synthetic Voice Verification
- Dataset Management (NFHS-5 / CDC NHANES import & dataset-backed insights)

Safety guarantees:
- NOT run automatically at application startup.
- Requires an explicitly provided, verified backup path before proceeding.
- Inspects foreign-key/dependency relationships and aborts on unsafe references.
- Scans active application code for references to the obsolete tables/features and aborts if found.
- Uses a migration/version marker to prevent accidental repeated execution.
- Reports tables to be removed and never deletes unrelated tables/records.
- Supports dry-run by default; actual removal requires --execute.

Usage (from repo root or backend/):
  python backend/scripts/remove_decommissioned_feature_tables.py --backup-path "C:\\path\\to\\backup.db" [--database "sqlite:///./backend/asha_swar.db"] [--execute]

Notes:
- "Verified backup" in this script means the provided backup file exists, is readable,
  is non-empty, and (for SQLite files) can be opened and queried successfully.
  Operators must also ensure the backup is complete and restorable for their environment.
- If conditions cannot be guaranteed, do not pass --execute; leave obsolete tables untouched.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse


OBSOLETE_TABLES = [
    "public_dataset_observations",  # may reference dataset_imports; drop first
    "dataset_imports",
    "synthetic_voice_analyses",
]
SCRIPT_ID = "remove_decommissioned_voice_auth_dataset_tables_v1"
MARKER_TABLE = "decommissioning_migrations"

# Patterns that indicate active feature/code references (excluding this script itself and backups/docs by caller policy)
ACTIVE_CODE_PATTERNS = [
    r"\bsynthetic_voice_analyses\b",
    r"\bdataset_imports\b",
    r"\bpublic_dataset_observations\b",
    r"\bSyntheticVoiceAnalysis\b",
    r"\bDatasetImport\b",
    r"\bPublicDatasetObservation\b",
    r"/api/voice-verification",
    r"/api/datasets\b",
    r"app\.routers\.voiceprint",
    r"app\.routers\.datasets",
    r"app\.services\.voiceprint",
    r"app\.services\.datasets",
]


def _repo_root() -> Path:
    # backend/scripts/<this file> -> repo root
    return Path(__file__).resolve().parents[2]


def _resolve_sqlite_path(database: str) -> Path:
    database = (database or "").strip()
    if not database:
        database = os.getenv("DATABASE_URL", "sqlite:///./asha_swar.db")
    if database.startswith("sqlite:///"):
        raw = database[len("sqlite:///"):]
        # sqlite:///C:/path or sqlite:///./path or sqlite:////abs/path
        if re.match(r"^[A-Za-z]:/", raw):
            p = Path(unquote(raw))
        elif raw.startswith("/"):
            p = Path(unquote(raw))
        else:
            p = (_repo_root() / unquote(raw)).resolve()
        return p
    if database.startswith("sqlite://"):
        raw = database[len("sqlite://"):]
        return Path(unquote(raw)).resolve()
    raise SystemExit(
        "This script currently supports SQLite database URLs/paths only. "
        f"Refusing to proceed for DATABASE_URL={database!r}."
    )


def _verify_backup(backup_path: Path) -> tuple[bool, str]:
    if not backup_path.exists():
        return False, f"Backup path does not exist: {backup_path}"
    if not backup_path.is_file():
        return False, f"Backup path is not a file: {backup_path}"
    try:
        size = backup_path.stat().st_size
    except OSError as e:
        return False, f"Cannot stat backup file: {e}"
    if size <= 0:
        return False, f"Backup file is empty: {backup_path}"
    # Best-effort SQLite verification
    try:
        con = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            cur = con.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            # quick integrity sample (full integrity_check can be slow on large DBs; pragma quick_check is lighter)
            try:
                cur.execute("PRAGMA quick_check")
                row = cur.fetchone()
                if row and str(row[0]).lower() != "ok":
                    return False, f"Backup SQLite quick_check failed: {row[0]}"
            except Exception:
                # If quick_check unavailable/fails unexpectedly, still require readable DB
                pass
        finally:
            con.close()
    except Exception as e:
        return False, f"Backup file could not be verified as a readable SQLite database: {e}"
    return True, f"Backup verified (exists, non-empty, readable SQLite): {backup_path} ({size} bytes)"


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path), timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _row_count(con: sqlite3.Connection, table: str) -> int | None:
    if not _table_exists(con, table):
        return None
    cur = con.cursor()
    cur.execute(f'SELECT COUNT(*) AS c FROM "{table}"')
    row = cur.fetchone()
    return int(row["c"]) if row else 0


def _incoming_fk_refs(con: sqlite3.Connection, target_tables: list[str]) -> list[tuple[str, str, str]]:
    """Return (referencing_table, from_col, referenced_table) for FKs from non-target tables into target tables."""
    refs = []
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    all_tables = [r[0] for r in cur.fetchall()]
    targets = set(target_tables)
    for t in all_tables:
        if t in targets:
            continue
        try:
            cur.execute(f'PRAGMA foreign_key_list("{t}")')
            for fk in cur.fetchall():
                ref_table = fk[2]
                if ref_table in targets:
                    refs.append((t, fk[3], ref_table))
        except Exception:
            # If table cannot be inspected, be conservative
            refs.append((t, "<unknown>", "<inspection failed>"))
    return refs


def _internal_fk_report(con: sqlite3.Connection, target_tables: list[str]) -> list[tuple[str, str, str]]:
    refs = []
    cur = con.cursor()
    targets = set(target_tables)
    for t in target_tables:
        if not _table_exists(con, t):
            continue
        cur.execute(f'PRAGMA foreign_key_list("{t}")')
        for fk in cur.fetchall():
            ref_table = fk[2]
            refs.append((t, fk[3], ref_table))
    return refs


def _scan_active_code(repo_root: Path, script_path: Path) -> list[str]:
    hits: list[str] = []
    include_roots = [repo_root / "backend" / "app", repo_root / "frontend" / "src", repo_root / "backend" / "scripts", repo_root / "scripts"]
    exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".sql", ".yml", ".yaml"}
    compiled = [re.compile(p) for p in ACTIVE_CODE_PATTERNS]
    for root in include_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.resolve() == script_path.resolve():
                continue
            if "__pycache__" in path.parts or "node_modules" in path.parts or ".git" in path.parts:
                continue
            if path.suffix.lower() not in exts:
                continue
            # skip obvious non-active/report locations in repo root scan context if any
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                for rx in compiled:
                    if rx.search(line):
                        hits.append(f"{path.relative_to(repo_root)}:{i}: {line.strip()[:200]}")
                        break
                if len(hits) >= 50:
                    return hits
    return hits


def _ensure_marker_table(con: sqlite3.Connection) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MARKER_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT ''
        )
        """
    )


def _marker_exists(con: sqlite3.Connection, script_id: str) -> bool:
    _ensure_marker_table(con)
    cur = con.cursor()
    cur.execute(f"SELECT 1 FROM {MARKER_TABLE} WHERE script_id=?", (script_id,))
    return cur.fetchone() is not None


def _record_marker(con: sqlite3.Connection, script_id: str, details: str) -> None:
    _ensure_marker_table(con)
    con.execute(
        f"INSERT INTO {MARKER_TABLE} (script_id, applied_at, details) VALUES (?, ?, ?)",
        (script_id, datetime.now(timezone.utc).isoformat(), details),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicitly remove decommissioned feature tables (safe, one-time).")
    parser.add_argument("--database", default=os.getenv("DATABASE_URL", "sqlite:///./asha_swar.db"), help="Target database URL/path (SQLite supported).")
    parser.add_argument("--backup-path", required=True, help="Path to a verified backup of the target database (required).")
    parser.add_argument("--execute", action="store_true", help="Actually perform table removal. Without this flag, runs checks/report only (dry-run).")
    args = parser.parse_args()

    repo_root = _repo_root()
    script_path = Path(__file__).resolve()
    db_path = _resolve_sqlite_path(args.database)
    backup_path = Path(args.backup_path).expanduser()
    if not backup_path.is_absolute():
        backup_path = (Path.cwd() / backup_path).resolve()

    print("=== Decommissioned Feature Table Removal (explicit, one-time) ===")
    print(f"Script ID: {SCRIPT_ID}")
    print(f"Target DB: {db_path}")
    print(f"Backup path: {backup_path}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN/CHECKS ONLY'}")
    print()
    print("Tables targeted for removal (if present and safe):")
    for t in OBSOLETE_TABLES:
        print(f" - {t}")
    print()

    ok, msg = _verify_backup(backup_path)
    print(f"[backup] {msg}")
    if not ok:
        print("ABORT: Verified database backup is required before proceeding.")
        return 2

    if not db_path.exists():
        print(f"ABORT: Target database file does not exist: {db_path}")
        return 2

    try:
        con = _connect(db_path)
    except Exception as e:
        print(f"ABORT: Could not open target database: {e}")
        return 2

    try:
        con.execute("PRAGMA foreign_keys=ON")
        existing = [t for t in OBSOLETE_TABLES if _table_exists(con, t)]
        print("Table presence / row counts:")
        for t in OBSOLETE_TABLES:
            c = _row_count(con, t)
            state = "MISSING" if c is None else f"EXISTS (rows={c})"
            print(f" - {t}: {state}")
        print()

        if _marker_exists(con, SCRIPT_ID):
            print(f"ABORT: Migration marker already exists for {SCRIPT_ID}. Refusing repeated execution.")
            return 3

        incoming = _incoming_fk_refs(con, OBSOLETE_TABLES)
        if incoming:
            print("ABORT: Incoming foreign-key dependencies found from non-target tables:")
            for rt, col, ref in incoming:
                print(f" - {rt}.{col} -> {ref}")
            return 4
        print("[deps] No incoming foreign-key references from non-target tables found.")

        internal = _internal_fk_report(con, OBSOLETE_TABLES)
        if internal:
            print("[deps] Internal foreign-key relationships among target tables (informational):")
            for t, col, ref in internal:
                print(f" - {t}.{col} -> {ref}")
        else:
            print("[deps] No internal foreign-key relationships reported among target tables.")
        print()

        code_hits = _scan_active_code(repo_root, script_path)
        if code_hits:
            print("ABORT: Active application code references to decommissioned tables/features were found:")
            for h in code_hits:
                print(f" - {h}")
            print("Resolve/remove active references before physical table removal.")
            return 5
        print("[code-scan] No active application code references found for targeted tables/features (scanned backend/app, frontend/src, backend/scripts, scripts).")
        print()

        if not existing:
            print("No targeted obsolete tables are present. Nothing to drop.")
            if args.execute:
                with con:
                    _record_marker(con, SCRIPT_ID, "no-op: targeted tables already absent")
                print(f"Recorded migration marker {SCRIPT_ID} (no-op).")
            else:
                print("Dry-run complete. Re-run with --execute to record no-op marker if desired.")
            return 0

        print("Planned action:")
        print(f" - DROP TABLE IF EXISTS {existing[0]} (and other present target tables in safe order)")
        print(" - No unrelated tables/records will be modified.")
        print()

        if not args.execute:
            print("Dry-run complete. No changes made. Re-run with --execute to apply (after ensuring backup/restorability).")
            return 0

        # Apply in safe order (children/dependents first)
        drop_order = [t for t in ["public_dataset_observations", "dataset_imports", "synthetic_voice_analyses"] if t in existing]
        with con:
            con.execute("PRAGMA foreign_keys=OFF")
            for t in drop_order:
                print(f"Dropping table: {t}")
                con.execute(f'DROP TABLE IF EXISTS "{t}"')
            _record_marker(con, SCRIPT_ID, f"dropped_tables={','.join(drop_order)}")
            con.execute("PRAGMA foreign_keys=ON")

        # Post-check
        remaining = [t for t in OBSOLETE_TABLES if _table_exists(con, t)]
        if remaining:
            print(f"ABORT/ERROR: Some targeted tables still exist after execution: {remaining}")
            return 6

        print(f"SUCCESS: Removed tables {drop_order} and recorded marker {SCRIPT_ID}.")
        return 0
    except Exception as e:
        print(f"ABORT: Unexpected error: {e}")
        return 1
    finally:
        try:
            con.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
