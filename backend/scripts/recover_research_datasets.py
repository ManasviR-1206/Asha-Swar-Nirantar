"""Recover original public/research dataset records from a verified backup DB.

Additive, idempotent recovery into the current database:
- Restores `dataset_imports`, `public_dataset_observations`, and `synthetic_voice_analyses`
  records from the specified backup (preserving original IDs/fields/provenance).
- Does NOT overwrite the active database with the backup.
- Does NOT modify/delete registered beneficiaries, households, synthetic demo records,
  or other operational tables.
- Safe to re-run: existing recovered records are not duplicated.

Usage (run from backend/):
  python scripts/recover_research_datasets.py --backup "data/backups/asha_swar_pre_feature_removal_20261120_013059.db" --dry-run
  python scripts/recover_research_datasets.py --backup "data/backups/asha_swar_pre_feature_removal_20261120_013059.db"
  python scripts/recover_research_datasets.py --verify
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import inspect, text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import DatasetImport, PublicDatasetObservation, SyntheticVoiceAnalysis  # noqa: E402

DEFAULT_BACKUP = os.path.join(
    BACKEND_DIR,
    "data",
    "backups",
    "asha_swar_pre_feature_removal_20261120_013059.db",
)

DATASET_TABLES = ["dataset_imports", "public_dataset_observations", "synthetic_voice_analyses"]


def _q(cur: sqlite3.Cursor, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    cur.execute(sql, args)
    return [dict(r) for r in cur.fetchall()]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _parse_dt(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        # SQLite often stores "YYYY-MM-DD HH:MM:SS[.ffffff]"
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
    return val


def inspect_backup(backup_path: str) -> dict[str, Any]:
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    conn = sqlite3.connect(backup_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("select name from sqlite_master where type='table'")
    tables = {r[0] for r in cur.fetchall()}
    result: dict[str, Any] = {"backup_path": backup_path, "tables": sorted(tables)}
    for t in DATASET_TABLES:
        if t not in tables:
            result[t] = {"present": False}
            continue
        cur.execute(f"select count(*) c from {t}")
        total = cur.fetchone()["c"]
        info: dict[str, Any] = {"present": True, "count": total}
        if t == "dataset_imports":
            info["rows"] = _q(cur, "select id,dataset_key,source_name,survey_year,survey_cycle,record_count,imported_count,duplicate_count,rejected_count,status,file_name,file_format from dataset_imports order by id")
        if t == "public_dataset_observations":
            info["by_dataset_key"] = _q(cur, "select dataset_key, count(*) c from public_dataset_observations group by dataset_key order by dataset_key")
            info["by_import_id"] = _q(cur, "select import_id, count(*) c from public_dataset_observations group by import_id order by import_id")
            cur.execute("select count(distinct dedup_hash) c from public_dataset_observations")
            info["distinct_dedup_hash"] = cur.fetchone()["c"]
            cur.execute("select count(*) c from public_dataset_observations where dataset_key='nhanes'")
            info["nhanes_count"] = cur.fetchone()["c"]
            cur.execute("select count(*) c from public_dataset_observations where dataset_key='nfhs5'")
            info["nfhs5_count"] = cur.fetchone()["c"]
        result[t] = info
    conn.close()
    return result


def current_counts() -> dict[str, Any]:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    db = SessionLocal()
    try:
        out: dict[str, Any] = {"tables_present": {t: (t in tables) for t in DATASET_TABLES}}
        if "dataset_imports" in tables:
            out["dataset_imports"] = db.query(DatasetImport).count()
            out["dataset_import_rows"] = [
                {
                    "id": r.id,
                    "dataset_key": r.dataset_key,
                    "imported_count": r.imported_count,
                    "record_count": r.record_count,
                    "status": r.status,
                }
                for r in db.query(DatasetImport).order_by(DatasetImport.id.asc()).all()
            ]
        else:
            out["dataset_imports"] = 0
            out["dataset_import_rows"] = []
        if "public_dataset_observations" in tables:
            out["public_dataset_observations"] = db.query(PublicDatasetObservation).count()
            out["obs_by_dataset_key"] = [
                {"dataset_key": k, "c": c}
                for k, c in db.query(PublicDatasetObservation.dataset_key, text("count(*)"))
            ] if False else []
            # portable counts
            conn = engine.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute("select dataset_key, count(*) c from public_dataset_observations group by dataset_key order by dataset_key")
                out["obs_by_dataset_key"] = [{"dataset_key": r[0], "c": r[1]} for r in cur.fetchall()]
                cur.execute("select import_id, count(*) c from public_dataset_observations group by import_id order by import_id")
                out["obs_by_import_id"] = [{"import_id": r[0], "c": r[1]} for r in cur.fetchall()]
            finally:
                conn.close()
        else:
            out["public_dataset_observations"] = 0
            out["obs_by_dataset_key"] = []
            out["obs_by_import_id"] = []
        if "synthetic_voice_analyses" in tables:
            out["synthetic_voice_analyses"] = db.query(SyntheticVoiceAnalysis).count()
        else:
            out["synthetic_voice_analyses"] = 0
        # operational preservation snapshot
        out["registered_beneficiaries"] = db.execute(text("select count(*) c from beneficiaries where data_origin='registered'")).scalar() if "beneficiaries" in inspect(engine).get_table_names() else None
        out["synthetic_demo_beneficiaries"] = db.execute(text("select count(*) c from beneficiaries where data_origin='synthetic_demo'")).scalar() if "beneficiaries" in inspect(engine).get_table_names() else None
        out["synthetic_demo_households"] = db.execute(text("select count(*) c from households where data_origin='synthetic_demo'")).scalar() if "households" in inspect(engine).get_table_names() else None
        return out
    finally:
        db.close()


def ensure_tables() -> None:
    # Create only missing tables; additive and non-destructive.
    Base.metadata.create_all(bind=engine, tables=[
        DatasetImport.__table__,
        PublicDatasetObservation.__table__,
        SyntheticVoiceAnalysis.__table__,
    ])


def recover(backup_path: str, dry_run: bool = False) -> dict[str, Any]:
    backup = inspect_backup(backup_path)
    before = current_counts()
    ensure_tables()

    # Validate expected source presence
    if not backup.get("dataset_imports", {}).get("present"):
        raise RuntimeError("Backup missing dataset_imports table")
    if not backup.get("public_dataset_observations", {}).get("present"):
        raise RuntimeError("Backup missing public_dataset_observations table")

    conn = sqlite3.connect(backup_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    db = SessionLocal()
    report: dict[str, Any] = {
        "backup": backup_path,
        "dry_run": dry_run,
        "before": before,
        "backup_summary": {
            "dataset_imports": backup.get("dataset_imports", {}),
            "public_dataset_observations": {
                k: v for k, v in backup.get("public_dataset_observations", {}).items() if k != "rows"
            },
            "synthetic_voice_analyses": backup.get("synthetic_voice_analyses", {}),
        },
        "inserted": {"dataset_imports": 0, "public_dataset_observations": 0, "synthetic_voice_analyses": 0},
        "skipped_existing": {"dataset_imports": 0, "public_dataset_observations": 0, "synthetic_voice_analyses": 0},
        "notes": [],
        "source_files_present_in_repo": False,
    }

    try:
        # --- dataset_imports ---
        cur.execute("select * from dataset_imports order by id")
        import_rows = [_row_to_dict(r) for r in cur.fetchall()]
        existing_import_ids = {r[0] for r in db.execute(text("select id from dataset_imports")).fetchall()} if inspect(engine).has_table("dataset_imports") else set()
        for row in import_rows:
            if row["id"] in existing_import_ids:
                report["skipped_existing"]["dataset_imports"] += 1
                continue
            if not dry_run:
                obj = DatasetImport(
                    id=row["id"],
                    source_name=row.get("source_name") or "",
                    source_url=row.get("source_url") or "",
                    license_info=row.get("license_info") or "",
                    classification=row.get("classification") or "",
                    notes=row.get("notes") or "",
                    mapping_info=row.get("mapping_info") or "",
                    record_count=int(row.get("record_count") or 0),
                    imported_by=row.get("imported_by"),
                    imported_at=_parse_dt(row.get("imported_at")) or datetime.utcnow(),
                    dataset_key=row.get("dataset_key") or "",
                    source_documentation=row.get("source_documentation") or "",
                    survey_year=row.get("survey_year") or "",
                    survey_cycle=row.get("survey_cycle") or "",
                    geographical_coverage=row.get("geographical_coverage") or "",
                    country=row.get("country") or "",
                    file_name=row.get("file_name") or "",
                    file_format=row.get("file_format") or "",
                    status=row.get("status") or "completed",
                    validation_errors=row.get("validation_errors") or "[]",
                    imported_count=int(row.get("imported_count") or 0),
                    duplicate_count=int(row.get("duplicate_count") or 0),
                    rejected_count=int(row.get("rejected_count") or 0),
                )
                db.add(obj)
            report["inserted"]["dataset_imports"] += 1
        if not dry_run:
            db.flush()

        # --- public_dataset_observations ---
        existing_obs_ids = set()
        if inspect(engine).has_table("public_dataset_observations"):
            # For large table, check by count/coverage quickly; load ids only if small-ish
            existing_count = db.execute(text("select count(*) c from public_dataset_observations")).scalar() or 0
        else:
            existing_count = 0

        cur.execute("select count(*) c from public_dataset_observations")
        backup_obs_count = cur.fetchone()["c"]

        if existing_count >= backup_obs_count and existing_count > 0:
            # assume already recovered if counts satisfied (idempotent fast path)
            report["skipped_existing"]["public_dataset_observations"] = backup_obs_count
            report["notes"].append("public_dataset_observations already present with >= backup count; skipped copy (idempotent).")
        else:
            # load existing ids/dedup hashes to avoid duplicates on partial rerun
            if existing_count > 0:
                existing_obs_ids = {r[0] for r in db.execute(text("select id from public_dataset_observations")).fetchall()}
            cur.execute("select * from public_dataset_observations order by id")
            batch = []
            BATCH_SIZE = 1000
            for r in cur.fetchall():
                row = _row_to_dict(r)
                if row["id"] in existing_obs_ids:
                    report["skipped_existing"]["public_dataset_observations"] += 1
                    continue
                if dry_run:
                    report["inserted"]["public_dataset_observations"] += 1
                    continue
                batch.append(PublicDatasetObservation(
                    id=row["id"],
                    import_id=int(row["import_id"]),
                    dataset_key=row.get("dataset_key") or "",
                    source_name=row.get("source_name") or "",
                    source_url=row.get("source_url") or "",
                    survey_year=row.get("survey_year") or "",
                    survey_cycle=row.get("survey_cycle") or "",
                    geographical_coverage=row.get("geographical_coverage") or "",
                    country=row.get("country") or "",
                    indicator_group=row.get("indicator_group") or "",
                    indicator_name=row.get("indicator_name") or "",
                    indicator_code=row.get("indicator_code") or "",
                    record_type=row.get("record_type") or "",
                    source_record_id=row.get("source_record_id") or "",
                    values_json=row.get("values_json") or "{}",
                    data_origin=row.get("data_origin") or "",
                    verification_status=row.get("verification_status") or "",
                    import_date=_parse_dt(row.get("import_date")) or datetime.utcnow(),
                    dedup_hash=row.get("dedup_hash") or "",
                    created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                ))
                report["inserted"]["public_dataset_observations"] += 1
                if len(batch) >= BATCH_SIZE:
                    db.bulk_save_objects(batch)
                    db.flush()
                    batch.clear()
            if batch and not dry_run:
                db.bulk_save_objects(batch)
                db.flush()

        # --- synthetic_voice_analyses (preservation) ---
        if backup.get("synthetic_voice_analyses", {}).get("present"):
            cur.execute("select * from synthetic_voice_analyses order by id")
            sva_rows = [_row_to_dict(r) for r in cur.fetchall()]
            existing_sva_ids = {r[0] for r in db.execute(text("select id from synthetic_voice_analyses")).fetchall()} if inspect(engine).has_table("synthetic_voice_analyses") else set()
            for row in sva_rows:
                if row["id"] in existing_sva_ids:
                    report["skipped_existing"]["synthetic_voice_analyses"] += 1
                    continue
                if not dry_run:
                    db.add(SyntheticVoiceAnalysis(
                        id=row["id"],
                        worker_id=int(row.get("worker_id") or 1),
                        filename=row.get("filename") or "",
                        duration_ms=int(row.get("duration_ms") or 0),
                        sample_rate=int(row.get("sample_rate") or 0),
                        verdict=row.get("verdict") or "",
                        score=float(row.get("score") or 0.0),
                        indicators=row.get("indicators") or "[]",
                        quality_notes=row.get("quality_notes") or "[]",
                        language=row.get("language") or "",
                        created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                    ))
                report["inserted"]["synthetic_voice_analyses"] += 1

        if not dry_run:
            db.commit()
            # reset sqlite sequences if needed (best-effort)
            try:
                conn2 = engine.raw_connection()
                cur2 = conn2.cursor()
                for t in DATASET_TABLES:
                    cur2.execute("select name from sqlite_master where type='table' and name='sqlite_sequence'")
                    if cur2.fetchone():
                        cur2.execute(f"select max(id) from {t}")
                        mx = cur2.fetchone()[0]
                        if mx is not None:
                            cur2.execute("select count(*) from sqlite_sequence where name=?", (t,))
                            if cur2.fetchone()[0]:
                                cur2.execute("update sqlite_sequence set seq=? where name=?", (int(mx), t))
                            else:
                                cur2.execute("insert into sqlite_sequence(name,seq) values(?,?)", (t, int(mx)))
                conn2.commit()
                conn2.close()
            except Exception:
                pass
        else:
            db.rollback()

        # preserve integrity checks (counts before/after operational tables in same DB snapshot context)
        after = current_counts()
        report["after"] = after
        report["preserved"] = {
            "registered_beneficiaries_before": before.get("registered_beneficiaries"),
            "registered_beneficiaries_after": after.get("registered_beneficiaries"),
            "synthetic_demo_beneficiaries_before": before.get("synthetic_demo_beneficiaries"),
            "synthetic_demo_beneficiaries_after": after.get("synthetic_demo_beneficiaries"),
            "synthetic_demo_households_before": before.get("synthetic_demo_households"),
            "synthetic_demo_households_after": after.get("synthetic_demo_households"),
        }
        return report
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        conn.close()


def verify_only() -> dict[str, Any]:
    ensure_tables()
    return {"current": current_counts()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover original research dataset records from verified backup DB")
    parser.add_argument("--backup", default=DEFAULT_BACKUP, help="Path to verified backup SQLite DB")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and report without writing to current DB")
    parser.add_argument("--verify", action="store_true", help="Show current research dataset counts/state only")
    args = parser.parse_args()

    if args.verify:
        print(json.dumps(verify_only(), indent=2, default=str))
        return 0

    backup_path = args.backup
    if not os.path.isabs(backup_path):
        # try relative to backend or cwd
        cand1 = os.path.abspath(os.path.join(BACKEND_DIR, backup_path))
        cand2 = os.path.abspath(backup_path)
        backup_path = cand1 if os.path.exists(cand1) else cand2

    report = recover(backup_path, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
