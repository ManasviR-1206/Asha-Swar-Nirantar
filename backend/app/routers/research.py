"""Research & public dataset endpoints (separate from operational ASHA records).

Serves recovered NHANES/NFHS-5 dataset metadata, observations/indicators, and
population-level analytics. Never exposes or mutates operational beneficiary,
household, visit, or follow-up records.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import SessionLocal, get_db
from app.models import DatasetImport, PublicDatasetObservation

router = APIRouter(prefix="/api/research", tags=["research"], dependencies=[Depends(get_current_worker)])

RESEARCH_BADGE = "PUBLIC RESEARCH DATA – NOT AN ASHA BENEFICIARY RECORD"
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_BACKUP = os.path.join(BACKEND_DIR, "data", "backups", "asha_swar_pre_feature_removal_20261120_013059.db")
OPERATIONAL_RECOVERY_BACKUPS = [
    {
        "name": "pre_feature_removal",
        "path": os.path.join(BACKEND_DIR, "data", "backups", "asha_swar_pre_feature_removal_20261120_013059.db"),
    },
    {
        "name": "pre_synthetic_cleanup",
        "path": os.path.join(BACKEND_DIR, "data", "backups", "asha_swar_pre_synthetic_cleanup_20261120_193702.db"),
    },
]

# Expected original counts from verified backup investigation (for recovery/completeness reporting)
EXPECTED_ORIGINAL = {
    "dataset_imports": 2,
    "public_dataset_observations": 9266,
    "nhanes_observations": 9254,
    "nfhs5_indicators": 12,
    "synthetic_voice_analyses": 9,
}


def _safe_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {"value": obj}
    except Exception:
        return {"_raw": str(raw)}


def _import_to_dict(row: DatasetImport) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_key": row.dataset_key,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "source_documentation": row.source_documentation,
        "license_info": row.license_info,
        "classification": row.classification,
        "survey_year": row.survey_year,
        "survey_cycle": row.survey_cycle,
        "geographical_coverage": row.geographical_coverage,
        "country": row.country,
        "file_name": row.file_name,
        "file_format": row.file_format,
        "status": row.status,
        "record_count": row.record_count,
        "imported_count": row.imported_count,
        "duplicate_count": row.duplicate_count,
        "rejected_count": row.rejected_count,
        "mapping_info": _safe_json(row.mapping_info),
        "validation_errors": _safe_json(row.validation_errors) if (row.validation_errors or "").strip().startswith("{") else (json.loads(row.validation_errors) if row.validation_errors else []),
        "notes": row.notes or "",
        "imported_by": row.imported_by,
        "imported_at": row.imported_at,
        "badge": RESEARCH_BADGE,
    }


def _obs_to_dict(row: PublicDatasetObservation, include_values: bool = True) -> dict[str, Any]:
    item = {
        "id": row.id,
        "import_id": row.import_id,
        "dataset_key": row.dataset_key,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "survey_year": row.survey_year,
        "survey_cycle": row.survey_cycle,
        "geographical_coverage": row.geographical_coverage,
        "country": row.country,
        "indicator_group": row.indicator_group,
        "indicator_name": row.indicator_name,
        "indicator_code": row.indicator_code,
        "record_type": row.record_type,
        "source_record_id": row.source_record_id,
        "data_origin": row.data_origin,
        "verification_status": row.verification_status,
        "import_date": row.import_date,
        "dedup_hash": row.dedup_hash,
        "created_at": row.created_at,
        "badge": RESEARCH_BADGE,
    }
    if include_values:
        item["values"] = _safe_json(row.values_json)
        item["values_json"] = row.values_json
    return item


def _table_exists(db: Session, name: str) -> bool:
    try:
        row = db.execute(text("select name from sqlite_master where type='table' and name=:n"), {"n": name}).fetchone()
        return row is not None
    except Exception:
        return False


@router.get("/datasets")
def list_research_datasets(db: Session = Depends(get_db)):
    if not _table_exists(db, "dataset_imports"):
        return {"datasets": [], "badge": RESEARCH_BADGE, "total": 0}
    rows = db.query(DatasetImport).order_by(DatasetImport.id.asc()).all()
    # attach recovered observation counts
    obs_counts = {}
    if _table_exists(db, "public_dataset_observations"):
        for import_id, c in db.query(PublicDatasetObservation.import_id, func.count(PublicDatasetObservation.id)).group_by(PublicDatasetObservation.import_id).all():
            obs_counts[int(import_id)] = int(c)
    datasets = []
    for r in rows:
        d = _import_to_dict(r)
        d["recovered_observation_count"] = obs_counts.get(r.id, 0)
        datasets.append(d)
    return {"datasets": datasets, "total": len(datasets), "badge": RESEARCH_BADGE}


@router.get("/datasets/{import_id}")
def get_research_dataset(import_id: int, db: Session = Depends(get_db)):
    if not _table_exists(db, "dataset_imports"):
        raise HTTPException(status_code=404, detail="Research datasets not available")
    row = db.query(DatasetImport).filter(DatasetImport.id == import_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Dataset import not found")
    data = _import_to_dict(row)
    if _table_exists(db, "public_dataset_observations"):
        data["recovered_observation_count"] = db.query(PublicDatasetObservation).filter(PublicDatasetObservation.import_id == import_id).count()
        # variable/field inventory for NHANES-like observations
        sample_vals = []
        q = db.query(PublicDatasetObservation.values_json).filter(PublicDatasetObservation.import_id == import_id).limit(50).all()
        keys = set()
        for (vj,) in q:
            try:
                obj = json.loads(vj or "{}")
                if isinstance(obj, dict):
                    keys.update([str(k) for k in obj.keys()])
            except Exception:
                pass
        data["available_value_fields_sample"] = sorted(list(keys))[:200]
    return {"dataset": data, "badge": RESEARCH_BADGE}


@router.get("/observations")
def list_research_observations(
    dataset_key: Optional[str] = None,
    import_id: Optional[int] = None,
    record_type: Optional[str] = None,
    indicator_group: Optional[str] = None,
    indicator_code: Optional[str] = None,
    source_record_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_values: bool = True,
    db: Session = Depends(get_db),
):
    if not _table_exists(db, "public_dataset_observations"):
        return {"observations": [], "total": 0, "limit": limit, "offset": offset, "badge": RESEARCH_BADGE}
    q = db.query(PublicDatasetObservation)
    if dataset_key:
        q = q.filter(PublicDatasetObservation.dataset_key == dataset_key.strip())
    if import_id is not None:
        q = q.filter(PublicDatasetObservation.import_id == import_id)
    if record_type:
        q = q.filter(PublicDatasetObservation.record_type == record_type.strip())
    if indicator_group:
        q = q.filter(PublicDatasetObservation.indicator_group == indicator_group.strip())
    if indicator_code:
        q = q.filter(PublicDatasetObservation.indicator_code == indicator_code.strip())
    if source_record_id:
        q = q.filter(PublicDatasetObservation.source_record_id == source_record_id.strip())
    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(or_(
            PublicDatasetObservation.source_record_id.ilike(term),
            PublicDatasetObservation.indicator_name.ilike(term),
            PublicDatasetObservation.indicator_code.ilike(term),
            PublicDatasetObservation.values_json.ilike(term),
        ))
    total = q.count()
    rows = q.order_by(PublicDatasetObservation.id.asc()).offset(offset).limit(limit).all()
    return {
        "observations": [_obs_to_dict(r, include_values=include_values) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "badge": RESEARCH_BADGE,
    }


@router.get("/indicators")
def list_research_indicators(
    dataset_key: Optional[str] = "nfhs5",
    import_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Aggregate indicators (e.g. NFHS-5). Does not convert to individual patient records."""
    if not _table_exists(db, "public_dataset_observations"):
        return {"indicators": [], "total": 0, "badge": RESEARCH_BADGE}
    q = db.query(PublicDatasetObservation).filter(PublicDatasetObservation.record_type == "aggregate")
    if dataset_key:
        q = q.filter(PublicDatasetObservation.dataset_key == dataset_key)
    if import_id is not None:
        q = q.filter(PublicDatasetObservation.import_id == import_id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(or_(PublicDatasetObservation.indicator_name.ilike(term), PublicDatasetObservation.indicator_code.ilike(term), PublicDatasetObservation.values_json.ilike(term)))
    total = q.count()
    rows = q.order_by(PublicDatasetObservation.id.asc()).offset(offset).limit(limit).all()
    return {"indicators": [_obs_to_dict(r, include_values=True) for r in rows], "total": total, "limit": limit, "offset": offset, "badge": RESEARCH_BADGE}


def _num(v):
    try:
        if v is None or v == "":
            return None
        n = float(v)
        if math.isnan(n) or math.isinf(n):
            return None
        return n
    except Exception:
        return None


def _distribution(counter: Counter, top_n: int | None = None) -> list[dict[str, Any]]:
    items = list(counter.items())
    def _key(x):
        n = _num(x[0])
        return (0, n) if n is not None else (1, str(x[0]))
    items.sort(key=_key)
    if top_n is not None:
        items = items[:top_n]
    return [{"value": k, "count": int(v)} for k, v in items]


def _histogram(values: list[float], bins: list[tuple[str, float | None, float | None]]) -> list[dict[str, Any]]:
    counts = {label: 0 for label, _, _ in bins}
    for v in values:
        placed = False
        for label, lo, hi in bins:
            if (lo is None or v >= lo) and (hi is None or v < hi):
                counts[label] += 1
                placed = True
                break
        if not placed:
            last_label, last_lo, last_hi = bins[-1]
            if last_hi is None and last_lo is not None and v >= last_lo:
                counts[last_label] += 1
    return [{"bin": label, "count": int(counts[label])} for label, _, _ in bins]


@router.get("/statistics")
def research_statistics(db: Session = Depends(get_db)):
    has_imports = _table_exists(db, "dataset_imports")
    has_obs = _table_exists(db, "public_dataset_observations")
    has_sva = _table_exists(db, "synthetic_voice_analyses")
    imports = db.query(DatasetImport).all() if has_imports else []
    obs_count = db.query(PublicDatasetObservation).count() if has_obs else 0
    by_key = {}
    by_type = {}
    by_geo = {}
    by_cycle = {}
    if has_obs:
        for k, c in db.query(PublicDatasetObservation.dataset_key, func.count(PublicDatasetObservation.id)).group_by(PublicDatasetObservation.dataset_key).all():
            by_key[k] = int(c)
        for k, c in db.query(PublicDatasetObservation.record_type, func.count(PublicDatasetObservation.id)).group_by(PublicDatasetObservation.record_type).all():
            by_type[k or "unknown"] = int(c)
        for k, c in db.query(PublicDatasetObservation.geographical_coverage, func.count(PublicDatasetObservation.id)).group_by(PublicDatasetObservation.geographical_coverage).all():
            by_geo[k or "unknown"] = int(c)
        for k, c in db.query(PublicDatasetObservation.survey_cycle, func.count(PublicDatasetObservation.id)).group_by(PublicDatasetObservation.survey_cycle).all():
            by_cycle[k or "unknown"] = int(c)

    sva_count = 0
    if has_sva:
        try:
            sva_count = db.execute(text("select count(*) c from synthetic_voice_analyses")).scalar() or 0
        except Exception:
            sva_count = 0

    # completeness vs expected verified backup counts
    completeness = {
        "expected_original": EXPECTED_ORIGINAL,
        "recovered": {
            "dataset_imports": len(imports),
            "public_dataset_observations": obs_count,
            "nhanes_observations": by_key.get("nhanes", 0),
            "nfhs5_indicators": by_key.get("nfhs5", 0),
            "synthetic_voice_analyses": int(sva_count or 0),
        },
    }
    completeness["match"] = {
        "dataset_imports": len(imports) == EXPECTED_ORIGINAL["dataset_imports"],
        "public_dataset_observations": obs_count == EXPECTED_ORIGINAL["public_dataset_observations"],
        "nhanes_observations": by_key.get("nhanes", 0) == EXPECTED_ORIGINAL["nhanes_observations"],
        "nfhs5_indicators": by_key.get("nfhs5", 0) == EXPECTED_ORIGINAL["nfhs5_indicators"],
        "synthetic_voice_analyses": int(sva_count or 0) == EXPECTED_ORIGINAL["synthetic_voice_analyses"],
    }

    return {
        "badge": RESEARCH_BADGE,
        "datasets": [_import_to_dict(r) for r in imports],
        "counts": {
            "imports": len(imports),
            "observations": obs_count,
            "aggregate_indicators": by_type.get("aggregate", 0),
            "observation_records": by_type.get("observation", 0),
            "by_dataset_key": by_key,
            "by_record_type": by_type,
            "by_geographical_coverage": by_geo,
            "by_survey_cycle": by_cycle,
            "synthetic_voice_analyses_preserved": int(sva_count or 0),
        },
        "completeness": completeness,
        "source_files_present_in_repo": False,
        "notes": [
            "Research observations/indicators are stored separately from operational ASHA beneficiary, household, visit, and follow-up records.",
            "NFHS-5 records recovered here are aggregate indicators only (no microdata imported).",
            "NHANES records are public-use microdata observations (US research data, 2017–2018) and are not representative of local ASHA beneficiaries.",
            "Synthetic voice analysis records (if preserved) are non-clinical/decommissioned analysis artifacts and are not clinical records.",
        ],
    }


@router.get("/analytics/population")
def research_population_analytics(db: Session = Depends(get_db)):
    """Population-level analytics from recovered research values only.

    Computes summaries/distributions/missing-data from actual imported NHANES
    columns and returns NFHS-5 aggregate indicators as-is. No individual ASHA
    timelines and no conversion to beneficiary/household/visit records.
    """
    if not _table_exists(db, "public_dataset_observations"):
        return {"badge": RESEARCH_BADGE, "nhanes": None, "nfhs5": None}

    # NFHS-5 aggregate indicators (as-is, population-level)
    nfhs_rows = db.query(PublicDatasetObservation).filter(PublicDatasetObservation.dataset_key == "nfhs5").order_by(PublicDatasetObservation.id.asc()).all()
    nfhs_indicators = []
    for r in nfhs_rows:
        vals = _safe_json(r.values_json)
        nfhs_indicators.append({
            "indicator_name": r.indicator_name,
            "indicator_code": r.indicator_code,
            "indicator_group": r.indicator_group,
            "survey_year": r.survey_year,
            "survey_cycle": r.survey_cycle,
            "geographical_coverage": r.geographical_coverage,
            "country": r.country,
            "record_type": r.record_type,
            "values": vals,
            "source_name": r.source_name,
            "source_url": r.source_url,
        })

    # NHANES: inspect/compute from actual recovered observation values
    nhanes_q = db.query(PublicDatasetObservation.values_json).filter(PublicDatasetObservation.dataset_key == "nhanes")
    total_nhanes = nhanes_q.count()

    all_keys: set[str] = set()
    key_non_missing = Counter()   # key present with a non-null/non-empty value
    numeric_values: dict[str, list[float]] = defaultdict(list)
    categorical_counts: dict[str, Counter] = defaultdict(Counter)
    age_bins = Counter()

    demo_numeric = ["RIDAGEYR", "INDFMPIR"]
    demo_categorical = ["RIAGENDR", "RIDRETH1", "RIDRETH3", "DMDEDUC2", "DMDMARTL"]
    body_numeric = ["BMXWT", "BMXHT", "BMXBMI", "BMXWAIST"]
    bp_numeric = ["BPXSY1", "BPXDI1", "BPXSY2", "BPXDI2", "BPXSY3", "BPXDI3"]

    for (vj,) in nhanes_q.yield_per(1000):
        vals = _safe_json(vj)
        if not isinstance(vals, dict):
            vals = {}
        row_keys = set(str(k) for k in vals.keys())
        all_keys.update(row_keys)
        for k in row_keys:
            v = vals.get(k)
            if v is not None and v != "":
                key_non_missing[k] += 1
                n = _num(v)
                if n is not None:
                    numeric_values[k].append(n)
                if k in demo_categorical:
                    if n is not None and abs(n - round(n)) < 1e-9:
                        categorical_counts[k][str(int(round(n)))] += 1
                    else:
                        categorical_counts[k][str(v)] += 1
        age = _num(vals.get("RIDAGEYR"))
        if age is not None:
            if age < 5: age_bins["0-4"] += 1
            elif age < 12: age_bins["5-11"] += 1
            elif age < 18: age_bins["12-17"] += 1
            elif age < 40: age_bins["18-39"] += 1
            elif age < 60: age_bins["40-59"] += 1
            else: age_bins["60+"] += 1

    def stats(arr: list[float]):
        if not arr:
            return None
        arr_sorted = sorted(arr)
        n = len(arr_sorted)
        mean = sum(arr_sorted) / n
        def pct(p):
            if n == 1: return arr_sorted[0]
            k = (n - 1) * p
            f = int(math.floor(k)); c = int(math.ceil(k))
            if f == c: return arr_sorted[f]
            return arr_sorted[f] * (c - k) + arr_sorted[c] * (k - f)
        var = sum((x - mean) ** 2 for x in arr_sorted) / n
        return {
            "count": n,
            "mean": round(mean, 3),
            "stddev": round(math.sqrt(var), 3),
            "min": round(arr_sorted[0], 3),
            "p25": round(pct(0.25), 3),
            "median": round(pct(0.5), 3),
            "p75": round(pct(0.75), 3),
            "max": round(arr_sorted[-1], 3),
        }

    missing_data = []
    for k in sorted(all_keys):
        present_count = int(key_non_missing.get(k, 0))
        missing_count = max(0, int(total_nhanes) - present_count)
        missing_data.append({
            "variable": k,
            "present_count": present_count,
            "missing_or_absent_count": missing_count,
            "missing_percent": round((100.0 * missing_count / total_nhanes), 3) if total_nhanes else 0.0,
            "present_percent": round((100.0 * present_count / total_nhanes), 3) if total_nhanes else 0.0,
        })

    def section_summaries(fields: list[str]):
        out = {}
        for f in fields:
            if f in numeric_values:
                s = stats(numeric_values.get(f, []))
                if s:
                    out[f] = s
        return out

    age_groups = ["0-4", "5-11", "12-17", "18-39", "40-59", "60+"]
    demographics = {
        "age_years_RIDAGEYR": stats(numeric_values.get("RIDAGEYR", [])),
        "age_group_distribution": [{"group": k, "count": int(age_bins.get(k, 0))} for k in age_groups],
        "sex_RIAGENDR_distribution": _distribution(categorical_counts.get("RIAGENDR", Counter())),
        "race_ethnicity_RIDRETH1_distribution": _distribution(categorical_counts.get("RIDRETH1", Counter())),
        "race_ethnicity_RIDRETH3_distribution": _distribution(categorical_counts.get("RIDRETH3", Counter())),
        "education_DMDEDUC2_distribution": _distribution(categorical_counts.get("DMDEDUC2", Counter())),
        "marital_status_DMDMARTL_distribution": _distribution(categorical_counts.get("DMDMARTL", Counter())),
        "income_poverty_ratio_INDFMPIR": stats(numeric_values.get("INDFMPIR", [])),
        "categorical_distributions": {k: _distribution(v) for k, v in sorted(categorical_counts.items()) if k in demo_categorical},
        "numeric_summaries": section_summaries(demo_numeric),
    }

    body_measurements = {
        "numeric_summaries": section_summaries(body_numeric),
        "bmi_distribution_BMXBMI": _histogram(numeric_values.get("BMXBMI", []), [("<18.5", 0.0, 18.5), ("18.5-24.9", 18.5, 25.0), ("25-29.9", 25.0, 30.0), ("30+", 30.0, None)]),
        "weight_kg_distribution_BMXWT": _histogram(numeric_values.get("BMXWT", []), [("<20", 0.0, 20.0), ("20-39.9", 20.0, 40.0), ("40-59.9", 40.0, 60.0), ("60-79.9", 60.0, 80.0), ("80-99.9", 80.0, 100.0), ("100+", 100.0, None)]),
        "height_cm_distribution_BMXHT": _histogram(numeric_values.get("BMXHT", []), [("<100", 0.0, 100.0), ("100-139.9", 100.0, 140.0), ("140-159.9", 140.0, 160.0), ("160-179.9", 160.0, 180.0), ("180+", 180.0, None)]),
        "waist_cm_distribution_BMXWAIST": _histogram(numeric_values.get("BMXWAIST", []), [("<60", 0.0, 60.0), ("60-79.9", 60.0, 80.0), ("80-99.9", 80.0, 100.0), ("100-119.9", 100.0, 120.0), ("120+", 120.0, None)]),
    }

    def bp_bucket_sys(v):
        if v < 120: return "normal (<120)"
        if v < 130: return "elevated (120-129)"
        if v < 140: return "stage 1 (130-139)"
        return "stage 2 (>=140)"

    def bp_bucket_dia(v):
        if v < 80: return "normal (<80)"
        if v < 90: return "stage 1/2 (80-89)"
        return "stage 2 (>=90)"

    blood_pressure = {
        "numeric_summaries": section_summaries(bp_numeric),
        "systolic_reading_distributions": {f: _distribution(Counter(bp_bucket_sys(v) for v in numeric_values.get(f, []))) for f in ["BPXSY1", "BPXSY2", "BPXSY3"] if f in numeric_values},
        "diastolic_reading_distributions": {f: _distribution(Counter(bp_bucket_dia(v) for v in numeric_values.get(f, []))) for f in ["BPXDI1", "BPXDI2", "BPXDI3"] if f in numeric_values},
    }

    summaries = {f: stats(v) for f, v in numeric_values.items() if stats(v)}
    nhanes = {
        "dataset_key": "nhanes",
        "survey_year": "2017-2018",
        "survey_cycle": "2017-2018",
        "geographical_coverage": "United States (national sample)",
        "country": "United States",
        "total_observations": total_nhanes,
        "population_level_note": "Aggregated summaries/distributions computed from recovered public-use NHANES 2017–2018 observations (United States national sample). This is US survey research data and is not representative of local ASHA beneficiaries; it must not be treated as ASHA patient/household records.",
        "gender_code_distribution_RIAGENDR": {k: int(v) for k, v in sorted(categorical_counts.get("RIAGENDR", Counter()).items())},
        "age_group_distribution_approx": {k: int(age_bins.get(k, 0)) for k in age_groups},
        "variable_summaries": summaries,
        "available_value_counts": {k: int(key_non_missing.get(k, 0)) for k in sorted(all_keys)},
        "available_variables": sorted(all_keys),
        "demographics": demographics,
        "body_measurements": body_measurements,
        "blood_pressure": blood_pressure,
        "missing_data_analysis": {
            "total_observations": total_nhanes,
            "note": "Missing/absent means the variable key was not present or had a null/empty value in the recovered observation record. Availability varies by participant age/exam component in NHANES.",
            "variables": missing_data,
        },
    }

    return {
        "badge": RESEARCH_BADGE,
        "nhanes": nhanes,
        "nfhs5": {
            "dataset_key": "nfhs5",
            "survey_year": "2019-21",
            "survey_cycle": "NFHS-5",
            "geographical_coverage": "India (national, total)",
            "country": "India",
            "total_indicators": len(nfhs_indicators),
            "indicators": nfhs_indicators,
            "population_level_note": "India national aggregate statistics from DHS STATcompiler/API (NFHS-5 2019–21). Public aggregate indicators only — no individual microdata — and not household or individual observations; never converted to ASHA patient/beneficiary records.",
        },
    }


@router.get("/recovery-history")
def research_recovery_history(db: Session = Depends(get_db)):
    # Import/recovery history from recovered metadata and known backup context
    stats = research_statistics(db)
    backup_exists = os.path.exists(DEFAULT_BACKUP)
    backup_info = {"path": DEFAULT_BACKUP, "exists": backup_exists}
    if backup_exists:
        try:
            st = os.stat(DEFAULT_BACKUP)
            backup_info.update({"size_bytes": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime)})
            conn = sqlite3.connect(DEFAULT_BACKUP)
            cur = conn.cursor()
            cur.execute("select name from sqlite_master where type='table' and name in ('dataset_imports','public_dataset_observations','synthetic_voice_analyses')")
            backup_info["dataset_tables_present"] = [r[0] for r in cur.fetchall()]
            for t in ['dataset_imports','public_dataset_observations','synthetic_voice_analyses']:
                try:
                    cur.execute(f"select count(*) c from {t}")
                    backup_info[f"{t}_count"] = cur.fetchone()[0]
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            backup_info["inspect_error"] = str(e)

    return {
        "badge": RESEARCH_BADGE,
        "identified_backup": backup_info,
        "expected_original_counts": EXPECTED_ORIGINAL,
        "recovered_counts": stats.get("counts", {}),
        "completeness": stats.get("completeness", {}),
        "imports": stats.get("datasets", []),
        "source_files_present_in_repo": False,
        "recovery_notes": [
            "Recovery performed additively from verified backup records into current DB (no active DB overwrite).",
            "Original NHANES XPT source files (DEMO_J/BMX_J/BPX_J) and NFHS-5 STATcompiler CSV file named in import metadata are not present in the repository.",
            "Synthetic voice analysis records are preserved as decommissioned/non-clinical analysis artifacts only (not clinical records and not part of operational workflows).",
        ],
    }


def _inspect_operational_backup(backup_name: str, backup_path: str, active_path: str) -> dict[str, Any]:
    """Read-only inspection of an earlier operational backup for provenance/authenticity assessment.

    Never restores or merges records. Used to produce a cautious validation report.
    """
    result: dict[str, Any] = {
        "backup_name": backup_name,
        "path": backup_path,
        "exists": os.path.exists(backup_path),
    }
    if not os.path.exists(backup_path):
        result["status"] = "missing"
        return result

    try:
        st = os.stat(backup_path)
        result.update({"size_bytes": st.st_size, "mtime": datetime.fromtimestamp(st.mtime)})
    except Exception:
        pass

    def _q(conn, sql, args=()):
        cur = conn.cursor()
        cur.execute(sql, args)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    try:
        bcon = sqlite3.connect(backup_path)
        bcon.row_factory = sqlite3.Row
        # table presence
        tables = {r["name"] for r in _q(bcon, "select name from sqlite_master where type='table'")}
        result["tables_present"] = sorted(list(tables))

        counts = {}
        for t in ["beneficiaries", "households", "visit_records", "follow_ups", "household_visits", "danger_alerts", "sms_reminders", "newborn_records", "immunisation_records", "pregnancy_records", "sms_notifications"]:
            if t in tables:
                rows = _q(bcon, f'select count(*) c from "{t}"')
                counts[t] = rows[0]["c"] if rows else 0
        result["counts"] = counts

        markers = {"beneficiaries_with_example_invalid_email_or_field": 0, "beneficiaries_with_synthetic_demo_marker": 0, "households_with_synthetic_demo_marker": 0}
        data_origin_dist: dict[str, int] = {}
        sample_names = []
        sample_villages = []
        ben_ids = []
        ben_qr = set()
        hh_ids = []
        hh_qr = set()
        if "beneficiaries" in tables:
            bens = _q(bcon, "select * from beneficiaries")
            for b in bens:
                ben_ids.append(b.get("id"))
                if b.get("qr_id"): ben_qr.add(b.get("qr_id"))
                blob = json.dumps(b, default=str)
                if "@example.invalid" in blob.lower():
                    markers["beneficiaries_with_example_invalid_email_or_field"] += 1
                if "SYNTHETIC_DEMO" in blob:
                    markers["beneficiaries_with_synthetic_demo_marker"] += 1
                do = b.get("data_origin")
                data_origin_dist[do if do is not None else "null"] = data_origin_dist.get(do if do is not None else "null", 0) + 1
            sample_names = [b.get("name") for b in bens[:10]]
            sample_villages = sorted(list({b.get("village") for b in bens if b.get("village")}))[:12]
        hh_origin_dist: dict[str, int] = {}
        if "households" in tables:
            hhs = _q(bcon, "select * from households")
            for h in hhs:
                hh_ids.append(h.get("id"))
                if h.get("qr_id"): hh_qr.add(h.get("qr_id"))
                blob = json.dumps(h, default=str)
                if "SYNTHETIC_DEMO" in blob:
                    markers["households_with_synthetic_demo_marker"] += 1
                do = h.get("data_origin")
                hh_origin_dist[do if do is not None else "null"] = hh_origin_dist.get(do if do is not None else "null", 0) + 1

        # relationship integrity within backup
        integrity = {}
        if "visit_records" in tables and "beneficiaries" in tables:
            integrity["visit_records_orphan_beneficiary_refs"] = _q(bcon, "select count(*) c from visit_records where beneficiary_id not in (select id from beneficiaries)")[0]["c"]
        if "follow_ups" in tables and "beneficiaries" in tables:
            integrity["follow_ups_orphan_beneficiary_refs"] = _q(bcon, "select count(*) c from follow_ups where beneficiary_id is not null and beneficiary_id not in (select id from beneficiaries)")[0]["c"]
        if "household_visits" in tables and "households" in tables:
            integrity["household_visits_orphan_household_refs"] = _q(bcon, "select count(*) c from household_visits where household_id not in (select id from households)")[0]["c"]

        # conflicts with active DB
        conflicts = {}
        if os.path.exists(active_path):
            acon = sqlite3.connect(active_path)
            acon.row_factory = sqlite3.Row
            try:
                a_ben_ids = {r["id"] for r in _q(acon, "select id from beneficiaries")} if "beneficiaries" in tables else set()
                a_hh_ids = {r["id"] for r in _q(acon, "select id from households")} if "households" in tables else set()
                a_ben_qr = {r["qr_id"] for r in _q(acon, "select qr_id from beneficiaries")}
                a_hh_qr = {r["qr_id"] for r in _q(acon, "select qr_id from households")}
                conflicts["beneficiary_id_overlap_count"] = len(set([i for i in ben_ids if i is not None]) & a_ben_ids)
                conflicts["household_id_overlap_count"] = len(set([i for i in hh_ids if i is not None]) & a_hh_ids)
                conflicts["beneficiary_qr_overlap_count"] = len(ben_qr & a_ben_qr)
                conflicts["household_qr_overlap_count"] = len(hh_qr & a_hh_qr)
            finally:
                acon.close()

        result.update({
            "status": "inspected",
            "markers": markers,
            "beneficiary_data_origin_distribution": data_origin_dist,
            "household_data_origin_distribution": hh_origin_dist,
            "relationship_integrity_within_backup": integrity,
            "conflicts_with_active_db": conflicts,
            "samples": {"beneficiary_names": sample_names, "villages": sample_villages},
        })

        # cautious authenticity assessment (no automatic restoration)
        syn_b = markers.get("beneficiaries_with_synthetic_demo_marker", 0)
        ex_b = markers.get("beneficiaries_with_example_invalid_email_or_field", 0)
        total_b = counts.get("beneficiaries", 0)
        total_h = counts.get("households", 0)
        authenticity_flags = []
        if ex_b:
            authenticity_flags.append(f"{ex_b}/{total_b} beneficiaries contain '@example.invalid' placeholder contact markers.")
        if syn_b:
            authenticity_flags.append(f"{syn_b}/{total_b} beneficiaries contain '[SYNTHETIC_DEMO]' markers in stored fields (e.g. village).")
        if markers.get("households_with_synthetic_demo_marker", 0):
            authenticity_flags.append(f"{markers['households_with_synthetic_demo_marker']}/{total_h} households contain '[SYNTHETIC_DEMO]' markers.")
        if data_origin_dist.get("registered") == total_b and total_b:
            authenticity_flags.append("All backup beneficiary records are labeled data_origin='registered' in backup metadata despite synthetic/demo markers; origin labeling is not reliable evidence of genuine registration.")
        if conflicts.get("beneficiary_id_overlap_count") or conflicts.get("household_id_overlap_count") or conflicts.get("beneficiary_qr_overlap_count") or conflicts.get("household_qr_overlap_count"):
            authenticity_flags.append("ID/QR overlaps with the active database were detected; direct restore/merge would risk conflicts or corruption.")

        result["authenticity_assessment"] = {
            "classification": "unverified_demo_or_synthetic_snapshot",
            "verified_genuine_operational_records": False,
            "reason": "Records include placeholder/synthetic markers and cannot be verified as genuine operational ASHA records from available evidence. Automatic restoration is unsafe and not approved.",
            "evidence_flags": authenticity_flags,
        }
        result["proposed_recovery"] = {
            "automatic_restore_or_merge": "not_permitted",
            "records_proposed_for_automatic_recovery": [],
            "requires_explicit_approval": True,
            "if_explicitly_approved_future_recovery_must": [
                "Be additive and non-destructive (never overwrite active DB).",
                "Exclude or separately relabel records with synthetic/demo markers (e.g. synthetic_demo) and never treat them as verified registered records.",
                "Preserve provenance/source backup references and original IDs/relationships only via a conflict-safe mapping strategy (no ID/QR collisions).",
                "Exclude records not verified as genuine operational data; do not invent missing details.",
                "Undergo human review before any import into operational workflows.",
            ],
            "recommendation": "Do not restore this snapshot into the active operational database. Treat as provenance/reference only unless explicit, reviewed, and conflict-safe recovery is approved.",
        }
        bcon.close()
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result


@router.get("/operational-recovery-assessment")
def operational_recovery_assessment(db: Session = Depends(get_db)):
    """Cautious provenance/authenticity assessment of earlier operational backups.

    Read-only inspection only. Never restores/merges records and never treats
    backup records as verified genuine operational data without evidence/approval.
    """
    active_path = os.path.abspath(os.path.join(BACKEND_DIR, "asha_swar.db"))
    # also consider configured DB if sqlite file path can be inferred; fall back to default
    try:
        db_url = str(get_db.__self__)  # not reliable; ignore
    except Exception:
        pass

    backups = []
    for b in OPERATIONAL_RECOVERY_BACKUPS:
        backups.append(_inspect_operational_backup(b["name"], b["path"], active_path))

    return {
        "badge": "OPERATIONAL BACKUP PROVENANCE REPORT – NOT A RESTORE",
        "generated_at": datetime.utcnow(),
        "scope": "Read-only inspection of earlier backup snapshots containing beneficiary/household/linked operational-style records. No records restored, merged, modified, or deleted.",
        "backups": backups,
        "overall_findings": [
            "Earlier backups contain 161 beneficiary and 53 household records with linked operational records in snapshots inspected.",
            "Inspected snapshots include placeholder/synthetic markers (e.g. '@example.invalid' contacts and '[SYNTHETIC_DEMO]' labels) and therefore cannot be verified as genuine operational ASHA records from available evidence.",
            "ID/QR overlaps with the active database exist in inspected snapshots; automatic restoration/merge is unsafe.",
            "No records are proposed for automatic recovery. Any future recovery requires explicit approval, conflict-safe additive handling, provenance/origin labeling, and human verification.",
        ],
        "separation_policy": [
            "registered, synthetic_demo, public_microdata, public_aggregate, imported_research, and authorized_local_import data must remain separated and clearly labeled.",
            "Research observations/indicators must never enter beneficiary, household, visit, follow-up, danger-alert, or reminder workflows.",
        ],
    }
