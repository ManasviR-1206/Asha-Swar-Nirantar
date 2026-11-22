"""Health measurement history endpoints.

Measurements are append-only in practice: new values create new records.
Edits update the existing record's fields but always write an audit entry so
history is preserved (no silent overwrite without trace). Records are never
hard-deleted through this API.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import AshaWorker, Beneficiary, HealthMeasurement, MeasurementAudit, VisitRecord

router = APIRouter(prefix="/api/measurements", tags=["measurements"], dependencies=[Depends(get_current_worker)])

# Supported measurement definitions: (default_unit, min, max, kind)
# Ranges are broad data-quality bounds (not diagnostic thresholds).
MEASUREMENT_DEFS: dict[str, dict[str, Any]] = {
    "height_cm": {"unit": "cm", "min": 20.0, "max": 250.0, "kind": "numeric"},
    "weight_kg": {"unit": "kg", "min": 0.5, "max": 300.0, "kind": "numeric"},
    "bmi": {"unit": "kg/m2", "min": 5.0, "max": 80.0, "kind": "numeric"},
    "bp_sys": {"unit": "mmHg", "min": 50.0, "max": 300.0, "kind": "numeric"},
    "bp_dia": {"unit": "mmHg", "min": 30.0, "max": 200.0, "kind": "numeric"},
    "pulse_bpm": {"unit": "bpm", "min": 20.0, "max": 250.0, "kind": "numeric"},
    "temperature_c": {"unit": "°C", "min": 30.0, "max": 45.0, "kind": "numeric"},
    "blood_glucose_mgdl": {"unit": "mg/dL", "min": 20.0, "max": 700.0, "kind": "numeric"},
    "spo2": {"unit": "%", "min": 50.0, "max": 100.0, "kind": "numeric"},
    "haemoglobin_gdl": {"unit": "g/dL", "min": 2.0, "max": 25.0, "kind": "numeric"},
    "muac_cm": {"unit": "cm", "min": 5.0, "max": 40.0, "kind": "numeric"},
    "head_circumference_cm": {"unit": "cm", "min": 20.0, "max": 70.0, "kind": "numeric"},
}

PREGNANCY_OBS_TYPES = {"fundal_height_cm", "fetal_heart_rate_bpm", "gestational_weeks"}
CHILD_OBS_TYPES = {"birth_weight_kg", "immunization_status_note"}

ALLOWED_SOURCES = {"manual", "voice", "device", "ocr", "import", "estimated"}
ALLOWED_VERIFICATION = {"recorded", "pending_verification", "verified", "entered_in_error"}


class MeasurementCreate(BaseModel):
    beneficiary_id: int
    measurement_type: str
    value: float | None = None
    value_text: str = ""
    unit: str = ""
    recorded_at: str | None = None  # ISO datetime/date
    visit_id: int | None = None
    source: str = "manual"
    verification_status: str = "recorded"
    notes: str = ""


class MeasurementBatchCreate(BaseModel):
    beneficiary_id: int
    visit_id: int | None = None
    recorded_at: str | None = None
    source: str = "manual"
    verification_status: str = "recorded"
    notes: str = ""
    # map of measurement_type -> numeric value (or dict with value/unit/value_text)
    measurements: dict[str, Any] = Field(default_factory=dict)


class MeasurementUpdate(BaseModel):
    value: float | None = None
    value_text: str | None = None
    unit: str | None = None
    recorded_at: str | None = None
    source: str | None = None
    verification_status: str | None = None
    notes: str | None = None
    reason: str = ""


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            return dt
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        raise HTTPException(status_code=400, detail="recorded_at must be a valid ISO date/time")


def _is_known_type(mtype: str) -> bool:
    if mtype in MEASUREMENT_DEFS or mtype in PREGNANCY_OBS_TYPES or mtype in CHILD_OBS_TYPES:
        return True
    # allow other clearly named clinical observation types without fabricated validation
    return bool(mtype) and len(mtype) <= 48 and all(c.isalnum() or c in "_-" for c in mtype)


def _validate_measurement(mtype: str, value: float | None, unit: str, value_text: str) -> tuple[float | None, str, str]:
    mtype = (mtype or "").strip().lower()
    if not _is_known_type(mtype):
        raise HTTPException(status_code=400, detail=f"Unsupported or invalid measurement_type: {mtype}")

    unit = (unit or "").strip()
    value_text = (value_text or "").strip()
    definition = MEASUREMENT_DEFS.get(mtype)

    if definition and definition.get("kind") == "numeric":
        if value is None:
            # allow text-only if explicitly provided (e.g. not recorded) but prefer numeric
            if not value_text:
                raise HTTPException(status_code=400, detail=f"{mtype} requires a numeric value")
        else:
            try:
                value = float(value)
            except Exception:
                raise HTTPException(status_code=400, detail=f"{mtype} value must be numeric")
            if value != value:  # NaN
                raise HTTPException(status_code=400, detail=f"{mtype} value is invalid")
            lo, hi = definition["min"], definition["max"]
            if value < lo or value > hi:
                raise HTTPException(status_code=400, detail=f"{mtype} value out of allowed range ({lo}-{hi} {definition['unit']})")
            if not unit:
                unit = definition["unit"]
            # basic unit sanity for known types
            expected = definition["unit"].replace(" ", "").lower()
            got = unit.replace(" ", "").lower()
            aliases = {
                "kg/m2": {"kg/m2", "kg/m²", "bmi"},
                "°c": {"°c", "c", "celsius"},
                "%": {"%", "percent", "spo2"},
            }
            ok_units = aliases.get(expected, {expected})
            if got and got not in ok_units:
                raise HTTPException(status_code=400, detail=f"{mtype} unit must be {definition['unit']}")
    else:
        # non-numeric/observation types: require some value
        if value is None and not value_text:
            raise HTTPException(status_code=400, detail=f"{mtype} requires a value or value_text")

    return value, unit, value_text


def _calc_bmi(height_cm: float | None, weight_kg: float | None) -> float | None:
    if height_cm is None or weight_kg is None:
        return None
    if height_cm <= 0 or weight_kg <= 0:
        return None
    h_m = height_cm / 100.0
    bmi = weight_kg / (h_m * h_m)
    if bmi < 5 or bmi > 80:
        return None
    return round(bmi, 1)


def _snapshot(m: HealthMeasurement) -> str:
    return json.dumps(
        {
            "measurement_type": m.measurement_type,
            "value": m.value,
            "value_text": m.value_text,
            "unit": m.unit,
            "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None,
            "source": m.source,
            "verification_status": getattr(m, "verification_status", "recorded"),
            "notes": m.notes,
            "visit_id": m.visit_id,
            "is_deleted": getattr(m, "is_deleted", False),
        },
        ensure_ascii=False,
        default=str,
    )


def _out(m: HealthMeasurement) -> dict:
    return {
        "id": m.id,
        "beneficiary_id": m.beneficiary_id,
        "visit_id": m.visit_id,
        "measurement_type": m.measurement_type,
        "value": m.value,
        "value_text": m.value_text,
        "unit": m.unit,
        "recorded_at": m.recorded_at,
        "source": m.source,
        "verification_status": getattr(m, "verification_status", "recorded"),
        "recorded_by_worker_id": m.recorded_by_worker_id,
        "notes": m.notes,
        "is_active": m.is_active,
        "is_deleted": getattr(m, "is_deleted", False),
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


@router.get("/beneficiary/{beneficiary_id}")
def list_measurements(
    beneficiary_id: int,
    measurement_type: str = Query("", alias="type"),
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    include_deleted: bool = False,
    db: Session = Depends(get_db),
):
    if db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first() is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    q = db.query(HealthMeasurement).filter(HealthMeasurement.beneficiary_id == beneficiary_id)
    if measurement_type:
        q = q.filter(HealthMeasurement.measurement_type == measurement_type.strip().lower())
    if from_date:
        try:
            q = q.filter(HealthMeasurement.recorded_at >= _parse_dt(from_date))
        except Exception:
            pass
    if to_date:
        try:
            q = q.filter(HealthMeasurement.recorded_at <= _parse_dt(to_date + "T23:59:59"))
        except Exception:
            pass
    if not include_deleted:
        q = q.filter(getattr(HealthMeasurement, "is_deleted", False) == False)  # noqa: E712
    rows = q.order_by(HealthMeasurement.recorded_at.desc(), HealthMeasurement.id.desc()).all()
    return {"measurements": [_out(r) for r in rows]}


@router.post("")
def create_measurement(payload: MeasurementCreate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    b = db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    if payload.visit_id and db.query(VisitRecord).filter(VisitRecord.id == payload.visit_id, VisitRecord.beneficiary_id == b.id).first() is None:
        raise HTTPException(status_code=400, detail="visit_id does not belong to beneficiary")

    mtype = (payload.measurement_type or "").strip().lower()
    source = (payload.source or "manual").strip().lower()
    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    vstatus = (payload.verification_status or "recorded").strip().lower()
    if vstatus not in ALLOWED_VERIFICATION:
        raise HTTPException(status_code=400, detail="Invalid verification_status")

    value, unit, value_text = _validate_measurement(mtype, payload.value, payload.unit, payload.value_text)
    recorded_at = _parse_dt(payload.recorded_at)

    m = HealthMeasurement(
        beneficiary_id=b.id,
        visit_id=payload.visit_id,
        measurement_type=mtype,
        value=value,
        value_text=value_text,
        unit=unit,
        recorded_at=recorded_at,
        source=source,
        recorded_by_worker_id=worker.id,
        notes=(payload.notes or "").strip(),
        verification_status=vstatus,
        is_active=True,
        is_deleted=False,
        created_at=datetime.utcnow(),
    )
    db.add(m)
    db.flush()
    db.add(MeasurementAudit(measurement_id=m.id, action="create", old_value="", new_value=_snapshot(m), changed_by=worker.id, reason="recorded"))
    db.commit()
    db.refresh(m)
    return {"measurement": _out(m)}


@router.post("/batch")
def create_measurements_batch(payload: MeasurementBatchCreate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    b = db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    source = (payload.source or "manual").strip().lower()
    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    vstatus = (payload.verification_status or "recorded").strip().lower()
    if vstatus not in ALLOWED_VERIFICATION:
        raise HTTPException(status_code=400, detail="Invalid verification_status")
    recorded_at = _parse_dt(payload.recorded_at)

    items = payload.measurements or {}
    if not items:
        raise HTTPException(status_code=400, detail="No measurements provided")

    # auto-calc BMI if valid height+weight provided and bmi not explicitly set
    normalized: dict[str, dict[str, Any]] = {}
    for k, v in items.items():
        mtype = (k or "").strip().lower()
        if isinstance(v, dict):
            normalized[mtype] = {"value": v.get("value"), "unit": v.get("unit", ""), "value_text": v.get("value_text", "")}
        else:
            normalized[mtype] = {"value": v, "unit": "", "value_text": ""}
    if "bmi" not in normalized:
        bmi = _calc_bmi(normalized.get("height_cm", {}).get("value"), normalized.get("weight_kg", {}).get("value"))
        if bmi is not None:
            normalized["bmi"] = {"value": bmi, "unit": "kg/m2", "value_text": ""}

    created = []
    for mtype, spec in normalized.items():
        value, unit, value_text = _validate_measurement(mtype, spec.get("value"), spec.get("unit", ""), spec.get("value_text", ""))
        m = HealthMeasurement(
            beneficiary_id=b.id,
            visit_id=payload.visit_id,
            measurement_type=mtype,
            value=value,
            value_text=value_text,
            unit=unit,
            recorded_at=recorded_at,
            source=source,
            recorded_by_worker_id=worker.id,
            notes=(payload.notes or "").strip(),
            verification_status=vstatus,
            is_active=True,
            is_deleted=False,
            created_at=datetime.utcnow(),
        )
        db.add(m)
        db.flush()
        db.add(MeasurementAudit(measurement_id=m.id, action="create", old_value="", new_value=_snapshot(m), changed_by=worker.id, reason="recorded (batch)"))
        created.append(m)

    db.commit()
    for m in created:
        db.refresh(m)
    return {"measurements": [_out(m) for m in created], "count": len(created)}


@router.patch("/{measurement_id}")
def update_measurement(measurement_id: int, payload: MeasurementUpdate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    m = db.query(HealthMeasurement).filter(HealthMeasurement.id == measurement_id).first()
    if m is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if getattr(m, "is_deleted", False):
        raise HTTPException(status_code=400, detail="Cannot edit a deleted measurement record")

    old = _snapshot(m)
    mtype = m.measurement_type

    new_value = m.value if payload.value is None else payload.value
    new_unit = m.unit if payload.unit is None else payload.unit
    new_text = m.value_text if payload.value_text is None else payload.value_text
    new_value, new_unit, new_text = _validate_measurement(mtype, new_value, new_unit, new_text)
    m.value = new_value
    m.unit = new_unit
    m.value_text = new_text

    if payload.recorded_at is not None:
        m.recorded_at = _parse_dt(payload.recorded_at)
    if payload.source is not None:
        src = payload.source.strip().lower()
        if src not in ALLOWED_SOURCES:
            raise HTTPException(status_code=400, detail="Invalid source")
        m.source = src
    if payload.verification_status is not None:
        vs = payload.verification_status.strip().lower()
        if vs not in ALLOWED_VERIFICATION:
            raise HTTPException(status_code=400, detail="Invalid verification_status")
        m.verification_status = vs
    if payload.notes is not None:
        m.notes = payload.notes.strip()

    m.updated_at = datetime.utcnow()
    db.add(MeasurementAudit(
        measurement_id=m.id,
        action="update",
        old_value=old,
        new_value=_snapshot(m),
        changed_by=worker.id,
        reason=(payload.reason or "").strip()[:256],
    ))
    db.commit()
    db.refresh(m)
    return {"measurement": _out(m)}