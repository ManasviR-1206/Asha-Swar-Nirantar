"""Database-grounded beneficiary history retrieval for Tara.

Returns factual, dated records only. Never invents missing data.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy.orm import Session

from app.models import Beneficiary, FollowUp, HealthMeasurement, ImmunisationRecord, VisitRecord


def _iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def beneficiary_history_summary(db: Session, beneficiary_id: int) -> dict:
    b = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    if not b:
        return {"found": False, "message": "I couldn't find that beneficiary in the recorded history."}

    visits = (
        db.query(VisitRecord)
        .filter(VisitRecord.beneficiary_id == beneficiary_id)
        .order_by(VisitRecord.visit_date.desc(), VisitRecord.id.desc())
        .limit(20)
        .all()
    )
    measurements = (
        db.query(HealthMeasurement)
        .filter(HealthMeasurement.beneficiary_id == beneficiary_id, HealthMeasurement.is_deleted == False)  # noqa: E712
        .order_by(HealthMeasurement.recorded_at.desc(), HealthMeasurement.id.desc())
        .limit(50)
        .all()
    )
    immunisations = (
        db.query(ImmunisationRecord)
        .filter(ImmunisationRecord.beneficiary_id == beneficiary_id)
        .order_by(ImmunisationRecord.date_given.desc().nullslast(), ImmunisationRecord.id.desc())
        .limit(20)
        .all()
    )
    followups = (
        db.query(FollowUp)
        .filter(FollowUp.beneficiary_id == beneficiary_id)
        .order_by(FollowUp.due_date.desc().nullslast(), FollowUp.id.desc())
        .limit(20)
        .all()
    )

    def meas(mtype):
        rows = [m for m in measurements if (m.measurement_type or "").lower() == mtype]
        return [
            {"value": m.value if m.value is not None else m.value_text, "unit": m.unit or "", "recorded_at": _iso(m.recorded_at), "source": m.source or "", "visit_id": m.visit_id}
            for m in rows[:10]
        ]

    latest_bp = None
    bp_sys = [m for m in measurements if m.measurement_type == "bp_sys"]
    bp_dia = [m for m in measurements if m.measurement_type == "bp_dia"]
    if bp_sys or bp_dia:
        # best-effort pairing by visit_id then recent
        by_visit = {}
        for m in bp_sys:
            by_visit.setdefault(m.visit_id, {})["sys"] = m
        for m in bp_dia:
            by_visit.setdefault(m.visit_id, {})["dia"] = m
        pairs = []
        for vid, p in by_visit.items():
            if "sys" in p and "dia" in p:
                pairs.append((p["sys"].recorded_at, p["sys"].value, p["dia"].value, p["sys"].visit_id))
        pairs.sort(key=lambda x: x[0] or date.min, reverse=True)
        if pairs:
            dt, s, d, vid = pairs[0]
            latest_bp = {"systolic": s, "diastolic": d, "recorded_at": _iso(dt), "visit_id": vid}
            if len(pairs) > 1:
                dt2, s2, d2, vid2 = pairs[1]
                latest_bp["previous"] = {"systolic": s2, "diastolic": d2, "recorded_at": _iso(dt2), "visit_id": vid2}

    summary = {
        "found": True,
        "beneficiary": {"id": b.id, "name": b.name, "age": b.age, "category": b.category, "village": b.village or "", "data_origin": b.data_origin or "registered"},
        "latest_visit": {"visit_date": _iso(visits[0].visit_date), "category": visits[0].category, "source": visits[0].source} if visits else None,
        "previous_visits": [{"visit_date": _iso(v.visit_date), "category": v.category, "source": v.source, "visit_id": v.id} for v in visits[:5]],
        "latest_bp": latest_bp,
        "weight_history": meas("weight_kg"),
        "immunisations": [{"vaccine_name": i.vaccine_name, "dose_number": i.dose_number, "date_given": _iso(i.date_given), "next_due_date": _iso(i.next_due_date)} for i in immunisations],
        "followups": [{"type": f.type, "status": f.status, "due_date": _iso(f.due_date), "reason": f.reason or ""} for f in followups],
    }
    return summary


def answer_history_question(db: Session, beneficiary_id: int, question: str) -> dict:
    q = (question or "").lower()
    summary = beneficiary_history_summary(db, beneficiary_id)
    if not summary.get("found"):
        return {"answer": summary.get("message"), "grounded": True, "facts": summary}

    b = summary["beneficiary"]
    name = b.get("name") or "This beneficiary"

    if "bp" in q or "blood pressure" in q:
        bp = summary.get("latest_bp")
        if not bp:
            return {"answer": f"I couldn't find a recorded blood pressure reading for {name}.", "grounded": True, "facts": summary}
        ans = f"{name}'s latest recorded blood pressure is {int(bp['systolic'])}/{int(bp['diastolic'])} on {bp['recorded_at'] or 'an unknown date'}."
        prev = bp.get("previous")
        if prev:
            ans += f" Previous recorded BP was {int(prev['systolic'])}/{int(prev['diastolic'])} on {prev['recorded_at'] or 'an unknown date'}."
        return {"answer": ans, "grounded": True, "facts": summary}

    if "weight" in q:
        wh = summary.get("weight_history") or []
        if not wh:
            return {"answer": f"I couldn't find a recorded weight for {name}.", "grounded": True, "facts": summary}
        latest = wh[0]
        ans = f"{name}'s latest recorded weight is {latest['value']} {latest['unit'] or 'kg'} on {latest['recorded_at'] or 'an unknown date'}."
        if len(wh) > 1:
            prev = wh[1]
            ans += f" Previous recorded weight was {prev['value']} {prev['unit'] or 'kg'} on {prev['recorded_at'] or 'an unknown date'}."
        return {"answer": ans, "grounded": True, "facts": summary}

    if "last visit" in q or "previous visit" in q or "when was" in q and "visit" in q:
        lv = summary.get("latest_visit")
        if not lv:
            return {"answer": f"I couldn't find a recorded visit for {name}.", "grounded": True, "facts": summary}
        return {"answer": f"{name}'s latest recorded visit was on {lv['visit_date']} ({lv.get('category','visit')}, source: {lv.get('source','recorded')}).", "grounded": True, "facts": summary}

    if "immunis" in q or "vaccin" in q:
        imms = summary.get("immunisations") or []
        if not imms:
            return {"answer": f"I couldn't find recorded immunisations for {name}.", "grounded": True, "facts": summary}
        parts = [f"{i['vaccine_name']} dose {i.get('dose_number') or ''} on {i.get('date_given') or 'unknown date'}" for i in imms[:5]]
        return {"answer": f"Recorded immunisations for {name}: " + "; ".join(parts) + ".", "grounded": True, "facts": summary}

    if "follow" in q or "pending" in q or "overdue" in q:
        fus = summary.get("followups") or []
        pending = [f for f in fus if f.get("status") in ("upcoming", "due", "overdue")]
        if not pending:
            return {"answer": f"I couldn't find pending follow-ups for {name}.", "grounded": True, "facts": summary}
        parts = [f"{f.get('type','follow-up')} ({f.get('status')}) due {f.get('due_date') or 'unknown date'}" for f in pending[:5]]
        return {"answer": f"Pending follow-ups for {name}: " + "; ".join(parts) + ".", "grounded": True, "facts": summary}

    return {"answer": f"I can answer from recorded history for {name}. Latest visit: {summary.get('latest_visit',{}).get('visit_date','not recorded') if summary.get('latest_visit') else 'not recorded'}. Ask about BP, weight, last visit, immunisations, or follow-ups for a dated answer.", "grounded": True, "facts": summary}
