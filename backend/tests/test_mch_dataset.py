"""MCH sample dataset extraction benchmark (48 rows).

Uses spoken_note as input and labelled columns as expected output.
External LLM providers are mocked/unavailable so the test is deterministic.
This is a TEXT extraction benchmark - not acoustic STT accuracy.

Does NOT insert any rows into the application database.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

CSV_PATH = Path(r"C:\Users\Manasvi R\OneDrive\Desktop\mch_sample_dataset.csv")
REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "mch_dataset_eval_report.json"


def _load_rows():
    if not CSV_PATH.exists():
        pytest.skip(f"MCH dataset not found at {CSV_PATH}")
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _norm_bool(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"true", "1", "yes", "y", "given"}:
        return True
    if s in {"false", "0", "no", "n", "not given"}:
        return False
    if s in {"", "none", "null", "not mentioned", "unknown"}:
        return None
    return None


def _norm_num(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in {"none", "null", "unknown"}:
        return None
    try:
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        try:
            return float(s)
        except Exception:
            return None


def _norm_str(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in {"none", "null"}:
        return None
    return s


def _norm_vaccine(v):
    s = _norm_str(v)
    if not s:
        return None
    s = s.lower().replace("_", "-").replace("  ", " ").strip()
    aliases = {
        "hep-b birth dose": "hep-b birth dose",
        "hepb birth dose": "hep-b birth dose",
        "hepatitis-b birth dose": "hep-b birth dose",
        "measles-rubella-1": "measles-rubella-1",
        "mr-1": "measles-rubella-1",
        "pentavalent-1": "pentavalent-1",
        "penta-1": "pentavalent-1",
        "bcg": "bcg",
        "opv-0": "opv-0",
    }
    return aliases.get(s, s)


def _norm_danger(v):
    if v is None:
        return None
    if isinstance(v, list):
        items = [str(x).strip().lower().replace(" ", "_") for x in v if str(x).strip()]
        return ",".join(sorted(set(items))) or None
    s = str(v).strip().lower().replace(" ", "_")
    if s in {"", "none", "null"}:
        return None
    # normalize common synonyms
    syn = {
        "reduced_fetal_movement": "reduced_fetal_movement",
        "decreased_fetal_movement": "reduced_fetal_movement",
        "bleeding": "bleeding",
        "high_fever": "high_fever",
        "fever": "fever",
    }
    parts = [syn.get(p.strip(), p.strip()) for p in s.split(",") if p.strip()]
    return ",".join(sorted(set(parts))) or None


def _extract(spoken_note, language, monkeypatch):
    # Force deterministic/no-external-LLM path for reproducibility.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GNANI_MODE", "demo")
    from app.services import gnani

    for a in ["_gemini_client", "_gemini_model"]:
        if hasattr(gnani, a):
            try:
                setattr(gnani, a, None)
            except Exception:
                pass

    # Pass the full language tag; service handles code-mixed kn-en/hi-en.
    result, mode = gnani.extract_fields_multi(spoken_note, language)
    visits = result.get("visits") or []
    v = visits[0] if visits else {}
    rs = v.get("raw_structured") or {}
    pd = v.get("personal_details") or {}
    meas = v.get("measurements") or {}
    mat = v.get("maternal_health") or {}
    child = v.get("child_health") or {}
    imm = v.get("immunisation") or {}

    flat = {}
    for src in (rs, pd, meas, mat, child, imm, v):
        if isinstance(src, dict):
            for k, val in src.items():
                if val is not None and k not in flat:
                    flat[k] = val
    # common aliases
    if flat.get("beneficiary_name") is None:
        flat["beneficiary_name"] = rs.get("woman") or pd.get("name") or v.get("beneficiary_name")
    if flat.get("hemoglobin") is None:
        flat["hemoglobin"] = rs.get("hb") or meas.get("hemoglobin")
    if flat.get("weight_kg") is None:
        flat["weight_kg"] = rs.get("weight") or meas.get("weight_kg")
    if flat.get("temperature") is None:
        flat["temperature"] = rs.get("temp_c") or rs.get("temperature") or meas.get("temperature")
    if flat.get("bp_systolic") is None and rs.get("bp"):
        try:
            bp = str(rs["bp"]).replace(" ", "")
            if "/" in bp:
                flat["bp_systolic"], flat["bp_diastolic"] = [int(x) for x in bp.split("/", 1)]
        except Exception:
            pass
    return flat, mode, result


def _get_bp(flat):
    sys = flat.get("bp_systolic") or flat.get("bp_sys")
    dia = flat.get("bp_diastolic") or flat.get("bp_dia")
    if sys is None or dia is None:
        bp = flat.get("bp")
        if bp and "/" in str(bp):
            try:
                s, d = str(bp).split("/", 1)
                return f"{int(float(s))}/{int(float(d))}"
            except Exception:
                return None
        return None
    try:
        return f"{int(float(sys))}/{int(float(dia))}"
    except Exception:
        return None


def _expected_actual(row, flat):
    expected_type = row.get("type")
    type_map = {
        "anc_visit": "pregnancy",
        "newborn_visit": "newborn",
        "immunisation": "immunisation",
        "immunization": "immunisation",
    }
    return {
        "woman_name": (_norm_str(row.get("woman")), _norm_str(flat.get("beneficiary_name") or flat.get("name") or flat.get("woman"))),
        "visit_type": (type_map.get(expected_type, expected_type), (flat.get("category") or "").lower() or None),
        "gestation_months": (_norm_num(row.get("gestation_months")), _norm_num(flat.get("gestation_months") or flat.get("weeks_pregnant_months"))),
        "hb": (_norm_num(row.get("hb")), _norm_num(flat.get("hemoglobin") or flat.get("hb"))),
        "weight_kg": (_norm_num(row.get("weight_kg")), _norm_num(flat.get("weight_kg") or flat.get("weight"))),
        "bp": (_norm_str(row.get("bp")), _get_bp(flat)),
        "ifa_given": (_norm_bool(row.get("ifa_given")), _norm_bool(flat.get("ifa_given") if flat.get("ifa_given") is not None else flat.get("ifa_tablets"))),
        "td_dose": (_norm_num(row.get("td_dose")), _norm_num(flat.get("td_dose") or flat.get("td_vaccine"))),
        "newborn_day": (_norm_num(row.get("newborn_day")), _norm_num(flat.get("newborn_day") or flat.get("baby_day"))),
        "temp_c": (_norm_num(row.get("temp_c")), _norm_num(flat.get("temperature") or flat.get("temp_c"))),
        "vaccine": (_norm_vaccine(row.get("vaccine")), _norm_vaccine(flat.get("vaccine_name") or flat.get("vaccine"))),
        "next_visit_days": (_norm_num(row.get("next_visit_days")), _norm_num(flat.get("next_visit_days") or flat.get("follow_up_days"))),
        "danger_signs": (_norm_danger(row.get("danger_signs")), _norm_danger(flat.get("danger_signs") or flat.get("symptoms"))),
    }


def _mismatch_reason(field, expected, actual, note):
    if expected is None:
        return "no expected value"
    if actual is None or actual == "":
        n = (note or "").lower()
        if field == "next_visit_days" and ("due date" in n or "pending" in n) and not any(ch.isdigit() for ch in n):
            return "not explicitly stated in text; extracting would invent value"
        if field == "danger_signs":
            return "danger sign cue not mapped by deterministic extractor"
        return "field not extracted by deterministic extractor"
    if str(expected).strip().lower() != str(actual).strip().lower():
        return "extracted value differs from expected label/mapping"
    return "ok"


@pytest.mark.parametrize("row", _load_rows(), ids=lambda r: r["id"])
def test_mch_row_extraction(row, monkeypatch):
    flat, mode, raw = _extract(row["spoken_note"], row["language"], monkeypatch)
    # Benchmark/reporting test; report aggregates actual accuracy.
    assert isinstance(flat, dict)
    assert raw is not None
    assert mode in {"demo", "live"}


def test_mch_dataset_report(monkeypatch):
    rows = _load_rows()
    report = {
        "total": len(rows),
        "by_language": {},
        "by_type": {},
        "fields": {},
        "rows": [],
        "mismatches": [],
    }
    field_stats = defaultdict(lambda: {"total": 0, "correct": 0, "missing": 0, "incorrect": 0})
    lang_stats = defaultdict(lambda: defaultdict(lambda: {"total": 0, "correct": 0, "missing": 0, "incorrect": 0}))

    def rec(field, lang, expected, actual, row_id, note):
        field_stats[field]["total"] += 1
        lang_stats[lang][field]["total"] += 1
        if expected is None:
            field_stats[field]["total"] -= 1
            lang_stats[lang][field]["total"] -= 1
            return None
        if actual is None or actual == "":
            field_stats[field]["missing"] += 1
            lang_stats[lang][field]["missing"] += 1
            reason = _mismatch_reason(field, expected, actual, note)
            report["mismatches"].append({"id": row_id, "field": field, "expected": expected, "actual": actual, "type": "missing", "reason": reason})
            return {"field": field, "expected": expected, "actual": actual, "status": "missing", "reason": reason}
        # Fair numeric comparison: 46 == 46.0
        exp_num = _norm_num(expected)
        act_num = _norm_num(actual)
        is_num_compare = exp_num is not None and act_num is not None and field in {"gestation_months","hb","weight_kg","td_dose","newborn_day","temp_c","next_visit_days"}
        matched = (float(exp_num) == float(act_num)) if is_num_compare else (str(expected).strip().lower() == str(actual).strip().lower())
        if matched:
            field_stats[field]["correct"] += 1
            lang_stats[lang][field]["correct"] += 1
            return {"field": field, "expected": expected, "actual": actual, "status": "correct"}
        field_stats[field]["incorrect"] += 1
        lang_stats[lang][field]["incorrect"] += 1
        reason = _mismatch_reason(field, expected, actual, note)
        report["mismatches"].append({"id": row_id, "field": field, "expected": expected, "actual": actual, "type": "incorrect", "reason": reason})
        return {"field": field, "expected": expected, "actual": actual, "status": "incorrect", "reason": reason}

    for row in rows:
        flat, mode, _ = _extract(row["spoken_note"], row["language"], monkeypatch)
        lang = row["language"]
        rid = row["id"]
        ea = _expected_actual(row, flat)
        field_results = []
        for field, (expected, actual) in ea.items():
            fr = rec(field, lang, expected, actual, rid, row.get("spoken_note", ""))
            if fr:
                field_results.append(fr)
        report["rows"].append({
            "id": rid,
            "language": lang,
            "type": row.get("type"),
            "spoken_note": row.get("spoken_note"),
            "mode": mode,
            "expected": {k: v[0] for k, v in ea.items() if v[0] is not None},
            "actual": {k: v[1] for k, v in ea.items() if v[0] is not None},
            "field_results": field_results,
        })

    def summarize(stats):
        out = {}
        for f, s in stats.items():
            total = s["total"] or 1
            out[f] = {**s, "accuracy_pct": round(100 * s["correct"] / total, 2)}
        return out

    report["fields"] = summarize(field_stats)
    report["by_language"] = {lang: summarize(fstats) for lang, fstats in lang_stats.items()}
    report["by_type"] = dict(Counter(r["type"] for r in rows))
    report["mode"] = "deterministic_mocked_external_llm"
    report["note"] = "Text extraction benchmark only; not acoustic STT accuracy. External LLM providers mocked/unavailable. No DB rows inserted."

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"summary": {k: v["accuracy_pct"] for k, v in report["fields"].items()}, "report": str(REPORT_PATH)}, indent=2))
    assert report["total"] == 48
