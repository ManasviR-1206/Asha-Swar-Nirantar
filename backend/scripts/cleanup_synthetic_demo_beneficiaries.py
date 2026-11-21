"""Safely remove legacy synthetic beneficiary seed data from a SQLite database.

Dry-run is the default. Applying the cleanup requires --apply and --backup-path.
User-authored records created after the seed cohort protect their beneficiary;
the cleanup then removes only unprotected seed records and their FK descendants.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


MARKER = "%[SYNTHETIC_DEMO]%"
RESERVED_DEMO_EMAIL = "%@example.invalid"
PROTECTION_TIME_COLUMNS = (
    "created_at",
    "recorded_at",
    "generated_at",
    "submitted_at",
    "changed_at",
    "sent_at",
)
SEED_TIME_COLUMNS = ("created_at", "recorded_at", "generated_at", "submitted_at", "sent_at")


def _database_path(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    return Path(__file__).resolve().parents[1] / "asha_swar.db"


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
    }


def _text_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        row[1]
        for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
        if any(kind in (row[2] or "").upper() for kind in ("CHAR", "CLOB", "TEXT"))
    ]


def _find_targets(connection: sqlite3.Connection) -> tuple[set[int], set[int]]:
    searchable = _text_columns(connection, "beneficiaries")
    marker_terms = [
        f"upper(COALESCE({_quote(column)}, '')) LIKE ?"
        for column in searchable
    ]
    predicates = ["lower(COALESCE(data_origin, '')) = 'demo'"]
    predicates.extend(marker_terms)
    if "email" in searchable:
        predicates.append(f"lower(COALESCE({_quote('email')}, '')) LIKE ?")
    parameters = [MARKER.upper()] * len(marker_terms)
    if "email" in searchable:
        parameters.append(RESERVED_DEMO_EMAIL)
    beneficiary_ids = {
        int(row[0])
        for row in connection.execute(
            "SELECT id FROM beneficiaries WHERE " + " OR ".join(predicates),
            parameters,
        )
    }
    if not beneficiary_ids:
        return set(), set()

    placeholders = ",".join("?" for _ in beneficiary_ids)
    household_ids = {
        int(row[0])
        for row in connection.execute(
            f"""
            SELECT DISTINCT h.id
            FROM households h
            WHERE lower(COALESCE(h.data_origin, '')) = 'demo'
               OR upper(COALESCE(h.village, '')) LIKE ?
               OR upper(COALESCE(h.qr_id, '')) LIKE ?
               OR (
                    EXISTS (
                        SELECT 1 FROM household_members m
                        WHERE m.household_id = h.id
                          AND m.beneficiary_id IN ({placeholders})
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM household_members m
                        WHERE m.household_id = h.id
                          AND m.beneficiary_id IS NOT NULL
                          AND m.beneficiary_id NOT IN ({placeholders})
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM beneficiaries b
                        WHERE b.household_id = h.id
                          AND b.id NOT IN ({placeholders})
                    )
               )
            """,
            [
                MARKER.upper(),
                MARKER.upper(),
                *beneficiary_ids,
                *beneficiary_ids,
                *beneficiary_ids,
            ],
        )
    }
    return beneficiary_ids, household_ids


def _seed_cutoff(connection: sqlite3.Connection, beneficiary_ids: set[int]) -> datetime:
    placeholders = ",".join("?" for _ in beneficiary_ids)
    values = [
        datetime.fromisoformat(row[0])
        for row in connection.execute(
            f"SELECT created_at FROM beneficiaries WHERE id IN ({placeholders}) AND created_at IS NOT NULL",
            list(beneficiary_ids),
        )
    ]
    if not values:
        raise RuntimeError("Synthetic beneficiary candidates have no creation timestamps; refusing cleanup.")
    return max(values) + timedelta(minutes=1)


def _protected_beneficiaries(
    connection: sqlite3.Connection,
    beneficiary_ids: set[int],
    cutoff: datetime,
) -> set[int]:
    protected: set[int] = set()
    for table in _tables(connection):
        columns = _columns(connection, table)
        if "id" not in columns:
            continue
        time_columns = [column for column in PROTECTION_TIME_COLUMNS if column in columns]
        source_column = "source_type" if "source_type" in columns else None
        demo_column = "is_demo" if "is_demo" in columns else None
        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({_quote(table)})"
        ).fetchall()
        for fk in foreign_keys:
            if fk[2] != "beneficiaries":
                continue
            source_column_sql = f", {_quote(source_column)}" if source_column else ""
            demo_column_sql = f", {_quote(demo_column)}" if demo_column else ""
            time_sql = "".join(f", {_quote(column)}" for column in time_columns)
            placeholders = ",".join("?" for _ in beneficiary_ids)
            rows = connection.execute(
                f"""
                SELECT {_quote(fk[3])}{source_column_sql}{demo_column_sql}{time_sql}
                FROM {_quote(table)}
                WHERE {_quote(fk[3])} IN ({placeholders})
                """,
                list(beneficiary_ids),
            )
            for row in rows:
                parent_id = int(row[0])
                index = 1
                source_type = row[index] if source_column else None
                index += 1 if source_column else 0
                is_demo = row[index] if demo_column else None
                index += 1 if demo_column else 0
                timestamps = row[index:]
                if source_type == "rule" or bool(is_demo):
                    continue
                for timestamp in timestamps:
                    if not timestamp:
                        continue
                    try:
                        created = datetime.fromisoformat(str(timestamp))
                    except ValueError:
                        continue
                    if created > cutoff:
                        protected.add(parent_id)
                        break

    if "field_audits" in _tables(connection):
        columns = _columns(connection, "field_audits")
        if {"entity_type", "entity_id"}.issubset(columns):
            placeholders = ",".join("?" for _ in beneficiary_ids)
            protected.update(
                int(row[0])
                for row in connection.execute(
                    f"""
                    SELECT DISTINCT entity_id FROM field_audits
                    WHERE lower(entity_type) = 'beneficiary'
                      AND entity_id IN ({placeholders})
                    """,
                    list(beneficiary_ids),
                )
            )
    return protected


def _protected_households(
    connection: sqlite3.Connection,
    household_ids: set[int],
    cutoff: datetime,
) -> set[int]:
    protected: set[int] = set()
    for table in _tables(connection):
        columns = _columns(connection, table)
        if "id" not in columns:
            continue
        time_columns = [column for column in PROTECTION_TIME_COLUMNS if column in columns]
        source_column = "source_type" if "source_type" in columns else None
        demo_column = "is_demo" if "is_demo" in columns else None
        for fk in connection.execute(f"PRAGMA foreign_key_list({_quote(table)})"):
            if fk[2] != "households":
                continue
            source_column_sql = f", {_quote(source_column)}" if source_column else ""
            demo_column_sql = f", {_quote(demo_column)}" if demo_column else ""
            time_sql = "".join(f", {_quote(column)}" for column in time_columns)
            placeholders = ",".join("?" for _ in household_ids)
            rows = connection.execute(
                f"""
                SELECT {_quote(fk[3])}{source_column_sql}{demo_column_sql}{time_sql}
                FROM {_quote(table)}
                WHERE {_quote(fk[3])} IN ({placeholders})
                """,
                list(household_ids),
            )
            for row in rows:
                parent_id = int(row[0])
                index = 1
                source_type = row[index] if source_column else None
                index += 1 if source_column else 0
                is_demo = row[index] if demo_column else None
                index += 1 if demo_column else 0
                for timestamp in row[index:]:
                    if not timestamp or source_type == "rule" or bool(is_demo):
                        continue
                    try:
                        created = datetime.fromisoformat(str(timestamp))
                    except ValueError:
                        continue
                    if created > cutoff:
                        protected.add(parent_id)
                        break
    return protected


def _seed_child_roots(
    connection: sqlite3.Connection,
    beneficiary_ids: set[int],
    cutoff: datetime,
) -> dict[str, set[int]]:
    seed_rows: dict[str, set[int]] = {}
    for table in _tables(connection):
        columns = _columns(connection, table)
        if "id" not in columns:
            continue
        time_columns = [column for column in SEED_TIME_COLUMNS if column in columns]
        source_column = "source_type" if "source_type" in columns else None
        demo_column = "is_demo" if "is_demo" in columns else None
        origin_column = "data_origin" if "data_origin" in columns else None
        for fk in connection.execute(f"PRAGMA foreign_key_list({_quote(table)})"):
            if fk[2] != "beneficiaries":
                continue
            metadata = [
                column
                for column in (source_column, demo_column, origin_column, *time_columns)
                if column is not None
            ]
            selected = ", ".join(["id", _quote(fk[3]), *(_quote(column) for column in metadata)])
            placeholders = ",".join("?" for _ in beneficiary_ids)
            rows = connection.execute(
                f"""
                SELECT {selected} FROM {_quote(table)}
                WHERE {_quote(fk[3])} IN ({placeholders})
                """,
                list(beneficiary_ids),
            )
            for row in rows:
                values = dict(zip(["id", fk[3], *metadata], row))
                is_seed = (
                    values.get(source_column) == "rule"
                    or bool(values.get(demo_column))
                    or str(values.get(origin_column, "")).lower() == "demo"
                )
                if table == "consent_records":
                    has_non_demo_notification = connection.execute(
                        """
                        SELECT 1 FROM sms_notifications
                        WHERE consent_id = ? AND COALESCE(is_demo, 0) = 0
                        LIMIT 1
                        """,
                        (values["id"],),
                    ).fetchone()
                    is_seed = is_seed or has_non_demo_notification is None
                timestamps = [values[column] for column in time_columns if values.get(column)]
                if not is_seed and timestamps:
                    parsed = []
                    for timestamp in timestamps:
                        try:
                            parsed.append(datetime.fromisoformat(str(timestamp)))
                        except ValueError:
                            parsed = []
                            break
                    is_seed = bool(parsed) and all(timestamp <= cutoff for timestamp in parsed)
                if is_seed:
                    seed_rows.setdefault(table, set()).add(int(values["id"]))
    return seed_rows


def _delete_closure(
    connection: sqlite3.Connection,
    roots: dict[str, set[int]],
    protected_beneficiaries: set[int],
) -> dict[str, set[int]]:
    edges: dict[str, list[tuple[str, str]]] = {}
    reachable = {table for table, ids in roots.items() if ids}
    inspected: set[str] = set()
    while reachable - inspected:
        parent = (reachable - inspected).pop()
        inspected.add(parent)
        for child in _tables(connection):
            for fk in connection.execute(f"PRAGMA foreign_key_list({_quote(child)})"):
                if fk[2] != parent:
                    continue
                child_column, parent_column = fk[3], fk[4]
                if parent_column != "id" or "id" not in _columns(connection, child):
                    raise RuntimeError(
                        f"Unsupported FK while inspecting {child}.{child_column} -> {parent}.{parent_column}; refusing cleanup."
                    )
                edges.setdefault(parent, []).append((child, child_column))
                reachable.add(child)

    rowids: dict[str, set[int]] = {}
    scheduled_ids: dict[str, set[int]] = {}
    queue: list[tuple[str, set[int]]] = []
    for table, ids in roots.items():
        if not ids:
            continue
        placeholders = ",".join("?" for _ in ids)
        found = connection.execute(
            f"SELECT rowid, id FROM {_quote(table)} WHERE id IN ({placeholders})",
            list(ids),
        ).fetchall()
        rowids.setdefault(table, set()).update(int(row[0]) for row in found)
        values = {int(row[1]) for row in found}
        scheduled_ids.setdefault(table, set()).update(values)
        queue.append((table, values))

    while queue:
        parent_table, parent_ids = queue.pop()
        if not parent_ids:
            continue
        for child_table, child_column in edges.get(parent_table, []):
            placeholders = ",".join("?" for _ in parent_ids)
            found = connection.execute(
                f"""
                SELECT rowid, id FROM {_quote(child_table)}
                WHERE {_quote(child_column)} IN ({placeholders})
                """,
                list(parent_ids),
            ).fetchall()
            new_ids: set[int] = set()
            for rowid, child_id in found:
                child_id = int(child_id)
                if child_table == "beneficiaries" and child_id in protected_beneficiaries:
                    raise RuntimeError(
                        f"A candidate household references protected beneficiary {child_id}; refusing cleanup."
                    )
                rowids.setdefault(child_table, set()).add(int(rowid))
                if child_id not in scheduled_ids.setdefault(child_table, set()):
                    scheduled_ids[child_table].add(child_id)
                    new_ids.add(child_id)
            if new_ids:
                queue.append((child_table, new_ids))
    return rowids


def _make_backup(database: Path, backup: Path) -> None:
    if backup.exists():
        raise RuntimeError(f"Backup destination already exists: {backup}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(database))
    target = sqlite3.connect(str(backup))
    try:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed: {result[0] if result else 'no result'}")
    finally:
        target.close()
        source.close()


def _run(database: Path, apply: bool, backup: Path | None) -> None:
    if not database.is_file():
        raise RuntimeError(f"Database file does not exist: {database}")
    connection = sqlite3.connect(str(database), timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        if "beneficiaries" not in _tables(connection) or "households" not in _tables(connection):
            raise RuntimeError("Expected beneficiaries and households tables; refusing cleanup.")
        beneficiary_ids, household_ids = _find_targets(connection)
        if not beneficiary_ids:
            print("No synthetic/demo beneficiary records found.")
            return
        cutoff = _seed_cutoff(connection, beneficiary_ids)
        protected = _protected_beneficiaries(connection, beneficiary_ids, cutoff)
        protected_households = _protected_households(connection, household_ids, cutoff)
        delete_beneficiaries = beneficiary_ids - protected
        delete_households = household_ids - protected_households
        seed_children = _seed_child_roots(connection, beneficiary_ids, cutoff)
        roots = {
            "beneficiaries": delete_beneficiaries,
            "households": delete_households,
        }
        for table, ids in seed_children.items():
            roots.setdefault(table, set()).update(ids)
        deletion_rows = _delete_closure(connection, roots, protected)
        print(f"Database: {database}")
        print(f"Seed cohort cutoff: {cutoff.isoformat(sep=' ')}")
        print(f"Synthetic/demo beneficiary candidates: {len(beneficiary_ids)}")
        print(f"Protected beneficiaries with later linked records: {sorted(protected)}")
        print(f"Protected households with later linked records: {sorted(protected_households)}")
        print(f"Beneficiaries selected for removal: {len(delete_beneficiaries)}")
        print(f"Synthetic households selected for removal: {len(delete_households)}")
        print("Seed-generated records linked to protected beneficiaries will also be removed.")
        for table, ids in sorted(deletion_rows.items()):
            if ids:
                print(f"  {table}: {len(ids)} rows")
        if not apply:
            print("Dry run only. Re-run with --apply --backup-path <new-backup-file> to proceed.")
            return
        if backup is None:
            raise RuntimeError("--backup-path is required with --apply.")
        _make_backup(database, backup)
        print(f"Verified backup created: {backup}")
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        current_beneficiaries, current_households = _find_targets(connection)
        current_cutoff = _seed_cutoff(connection, current_beneficiaries)
        current_protected = _protected_beneficiaries(
            connection, current_beneficiaries, current_cutoff
        )
        current_protected_households = _protected_households(
            connection, current_households, current_cutoff
        )
        current_seed_children = _seed_child_roots(
            connection, current_beneficiaries, current_cutoff
        )
        current_roots = {
            "beneficiaries": current_beneficiaries - current_protected,
            "households": current_households - current_protected_households,
        }
        for table, ids in current_seed_children.items():
            current_roots.setdefault(table, set()).update(ids)
        current_rows = _delete_closure(
            connection,
            current_roots,
            current_protected,
        )
        if (
            current_rows != deletion_rows
            or current_protected != protected
            or current_protected_households != protected_households
        ):
            connection.rollback()
            raise RuntimeError(
                "Database changed after preflight; cleanup rolled back. Re-run the dry-run."
            )
        for table, ids in sorted(deletion_rows.items(), reverse=True):
            if not ids:
                continue
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"DELETE FROM {_quote(table)} WHERE rowid IN ({placeholders})",
                list(ids),
            )
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            connection.rollback()
            raise RuntimeError(
                f"Foreign-key check found {len(violations)} violation(s); cleanup rolled back."
            )
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(
                f"Database integrity check failed after cleanup: {integrity[0] if integrity else 'no result'}"
            )
        remaining, _ = _find_targets(connection)
        print(f"Cleanup applied. Remaining synthetic/demo beneficiaries: {len(remaining)}")
        print(f"SQLite integrity check: {integrity[0]}")
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="SQLite database file (default: backend/asha_swar.db)")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup after backup; dry-run is default")
    parser.add_argument("--backup-path", help="New backup file path required with --apply")
    args = parser.parse_args()
    try:
        _run(
            _database_path(args.database),
            args.apply,
            Path(args.backup_path).resolve() if args.backup_path else None,
        )
    except (OSError, sqlite3.Error, RuntimeError) as error:
        print(f"Cleanup aborted: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
