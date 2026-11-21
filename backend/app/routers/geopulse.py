"""ASHA GeoPulse - Village Health Intelligence Map (backend).

Returns ONLY actual stored household coordinates and actual DB-derived status.
No fake coordinates/statistics. Synthetic/demo locations must be clearly labeled.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.models import AshaWorker
from app.data_scope import visible_beneficiaries, visible_followups, visible_households
from app.database import get_db
from app.models import Beneficiary, DangerAlert, FollowUp, HealthFacility, Household, HouseholdMember, VisitRecord
from app.services.followups import refresh_followup_statuses

router = APIRouter(prefix="/api/geopulse", tags=["geopulse"], dependencies=[Depends(get_current_worker)])


def _iso(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return str(dt)


@router.get("/households")
def geopulse_households(
    db: Session = Depends(get_db),
    filter: str = Query("all"),
):
    """Return map-ready household points from actual stored coordinates only."""
    refresh_followup_statuses(db)
    today = date.today()

    households = visible_households(db.query(Household)).all()
    hh_ids = [h.id for h in households]
    if not hh_ids:
        return {"items": [], "total_households": 0, "mapped_households": 0, "filters_applied": filter, "synthetic_labeled": True}

    members = db.query(HouseholdMember).filter(HouseholdMember.household_id.in_(hh_ids)).all()
    members_by_hh: dict[int, list[HouseholdMember]] = {}
    ben_ids: list[int] = []
    for m in members:
        members_by_hh.setdefault(m.household_id, []).append(m)
        if m.beneficiary_id:
            ben_ids.append(m.beneficiary_id)

    ben_rows = []
    if ben_ids:
        ben_rows = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.id.in_(set(ben_ids))).all()
    ben_by_id = {b.id: b for b in ben_rows}

    # Visits by beneficiary
    latest_visit_by_ben: dict[int, date] = {}
    if ben_by_id:
        visit_rows = (
            db.query(VisitRecord.beneficiary_id, func.max(VisitRecord.visit_date))
            .filter(VisitRecord.beneficiary_id.in_(list(ben_by_id.keys())))
            .group_by(VisitRecord.beneficiary_id)
            .all()
        )
        for bid, d in visit_rows:
            if bid and d:
                latest_visit_by_ben[int(bid)] = d

    # Active follow-ups by beneficiary/household
    fu_rows = visible_followups(db.query(FollowUp), db).filter(
        FollowUp.status.in_(["upcoming", "due", "overdue"])
    ).all()
    fu_by_ben: dict[int, list[FollowUp]] = {}
    fu_by_hh: dict[int, list[FollowUp]] = {}
    for fu in fu_rows:
        if fu.beneficiary_id:
            fu_by_ben.setdefault(fu.beneficiary_id, []).append(fu)
        if fu.household_id:
            fu_by_hh.setdefault(fu.household_id, []).append(fu)

    # Active danger alerts
    alert_rows = db.query(DangerAlert).filter(DangerAlert.status.in_(["new", "acknowledged", "escalated"])).all()
    alerts_by_ben: dict[int, list[DangerAlert]] = {}
    for a in alert_rows:
        if a.beneficiary_id:
            alerts_by_ben.setdefault(a.beneficiary_id, []).append(a)

    items = []
    for hh in households:
        hh_members = members_by_hh.get(hh.id, [])
        hh_bens = [ben_by_id[m.beneficiary_id] for m in hh_members if m.beneficiary_id in ben_by_id]
        hh_ben_ids = [b.id for b in hh_bens]

        pending_followups = [fu for fu in fu_by_hh.get(hh.id, []) if fu.status in ("due", "overdue")]
        upcoming_followups = [fu for fu in fu_by_hh.get(hh.id, []) if fu.status == "upcoming"]
        for bid in hh_ben_ids:
            for fu in fu_by_ben.get(bid, []):
                if fu.status in ("due", "overdue"):
                    pending_followups.append(fu)
                elif fu.status == "upcoming":
                    upcoming_followups.append(fu)
        # de-dup by id
        pending_followups = list({f.id: f for f in pending_followups}.values())
        upcoming_followups = list({f.id: f for f in upcoming_followups}.values())

        active_alerts = []
        for bid in hh_ben_ids:
            active_alerts.extend(alerts_by_ben.get(bid, []))
        active_alerts = list({a.id: a for a in active_alerts}.values())

        maternal = any((b.category or "") == "pregnancy" for b in hh_bens)
        newborn = any((b.category or "") in {"newborn", "child"} for b in hh_bens)
        referrals = [a for a in active_alerts if "refer" in (a.message or "").lower() or a.status in ("new", "acknowledged", "escalated")]

        last_visit = None
        for bid in hh_ben_ids:
            d = latest_visit_by_ben.get(bid)
            if d and (last_visit is None or d > last_visit):
                last_visit = d

        has_coords = hh.latitude is not None and hh.longitude is not None
        is_synthetic = (hh.data_origin or "") != "registered"
        status = "normal"
        if referrals:
            status = "referral"
        elif pending_followups:
            status = "pending"
        elif upcoming_followups:
            status = "upcoming"
        elif maternal:
            status = "maternal"
        elif newborn:
            status = "newborn"

        item = {
            "household_id": hh.id,
            "qr_id": hh.qr_id,
            "village": hh.village or "",
            "address": hh.address or "",
            "member_count": hh.member_count or len(hh_members),
            "beneficiary_count": len(hh_bens),
            "data_origin": hh.data_origin or "registered",
            "is_synthetic_demo": is_synthetic,
            "latitude": hh.latitude,
            "longitude": hh.longitude,
            "location_source": hh.location_source or "",
            "location_updated_at": _iso(hh.location_updated_at),
            "has_coordinates": has_coords,
            "status": status,
            "last_visit_date": _iso(last_visit),
            "pending_followups_count": len(pending_followups),
            "upcoming_followups_count": len(upcoming_followups),
            "active_alerts_count": len(active_alerts),
            "maternal_count": sum(1 for b in hh_bens if (b.category or "") == "pregnancy"),
            "newborn_count": sum(1 for b in hh_bens if (b.category or "") in {"newborn", "child"}),
            "referral_count": len(referrals),
            "beneficiaries": [
                {
                    "id": b.id,
                    "name": b.name,
                    "category": b.category,
                    "data_origin": b.data_origin or "registered",
                }
                for b in hh_bens[:20]
            ],
        }

        f = (filter or "all").lower()
        include = True
        if f == "pending_visits":
            include = len(pending_followups) > 0
        elif f == "upcoming_followups":
            include = len(upcoming_followups) > 0
        elif f == "maternal_care":
            include = maternal
        elif f == "newborn_care":
            include = newborn
        elif f == "immunisation":
            include = any((b.category or "") in {"immunisation", "child"} for b in hh_bens)
        elif f == "referrals":
            include = len(referrals) > 0 or len(active_alerts) > 0
        if include:
            items.append(item)

    mapped = [i for i in items if i["has_coordinates"]]
    return {
        "items": items,
        "mapped_items": mapped,
        "total_households": len(households),
        "mapped_households": len([h for h in households if h.latitude is not None and h.longitude is not None]),
        "filters_applied": filter,
        "synthetic_labeled": True,
        "note": "Only actual stored coordinates are shown on the map. Households without coordinates appear in the list fallback.",
    }


class FacilityCreate(BaseModel):
    name: str
    facility_type: str = "PHC"
    address: str = ""
    village: str = ""
    latitude: float
    longitude: float
    location_source: str = "manual_verified"
    verification_status: str = "verified"


class FacilityImportRequest(BaseModel):
    facilities: list[FacilityCreate] = Field(default_factory=list)


@router.get("/facilities")
def geopulse_facilities(db: Session = Depends(get_db)):
    """Verified nearby PHC/health facilities. Returns only reliable stored data."""
    rows = (
        db.query(HealthFacility)
        .filter(HealthFacility.is_active == True)  # noqa: E712
        .filter(HealthFacility.verification_status == "verified")
        .filter(HealthFacility.latitude.isnot(None), HealthFacility.longitude.isnot(None))
        .order_by(HealthFacility.name.asc())
        .all()
    )
    items = [
        {
            "id": f.id,
            "name": f.name,
            "facility_type": f.facility_type,
            "address": f.address or "",
            "village": f.village or "",
            "latitude": f.latitude,
            "longitude": f.longitude,
            "location_source": f.location_source or "",
            "verification_status": f.verification_status,
            "verified_at": _iso(f.verified_at),
        }
        for f in rows
    ]
    return {
        "items": items,
        "available": len(items) > 0,
        "note": "Only verified facility records with stored coordinates are shown." if items else "No verified facility location data is configured. Add verified PHC/facility coordinates to enable this layer.",
    }


def _create_facility_record(db: Session, worker: AshaWorker, payload: FacilityCreate) -> dict:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Facility name is required")
    lat, lng = float(payload.latitude), float(payload.longitude)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise HTTPException(status_code=400, detail="Invalid coordinates")
    source = (payload.location_source or "manual_verified").strip()[:64]
    if source not in {"manual_verified", "verified_import", "gps"}:
        raise HTTPException(status_code=400, detail="Invalid location source")
    status = (payload.verification_status or "verified").strip().lower()
    if status not in {"pending", "verified", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid verification status")
    f = HealthFacility(
        name=name[:256],
        facility_type=(payload.facility_type or "PHC").strip()[:64],
        address=(payload.address or "").strip()[:256],
        village=(payload.village or "").strip()[:128],
        latitude=lat,
        longitude=lng,
        location_source=source,
        verification_status=status,
        verified_by=worker.id if status == "verified" else None,
        verified_at=datetime.utcnow() if status == "verified" else None,
        is_active=True,
    )
    db.add(f)
    db.flush()
    return {"id": f.id, "name": f.name, "verification_status": f.verification_status, "latitude": f.latitude, "longitude": f.longitude}


@router.post("/facilities")
def create_facility(payload: FacilityCreate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    """Register a verified facility location. Only verified records with coordinates are shown on map."""
    out = _create_facility_record(db, worker, payload)
    db.commit()
    return out


@router.post("/facilities/import")
def import_facilities(payload: FacilityImportRequest, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    """Authorised bulk import of verified facility records. No coordinates are fabricated."""
    if not payload.facilities:
        raise HTTPException(status_code=400, detail="No facilities provided")
    if len(payload.facilities) > 200:
        raise HTTPException(status_code=400, detail="Import limit is 200 facilities per request")
    created = []
    errors = []
    for idx, fac in enumerate(payload.facilities):
        try:
            created.append(_create_facility_record(db, worker, fac))
        except HTTPException as e:
            errors.append({"index": idx, "name": getattr(fac, "name", ""), "error": e.detail})
    db.commit()
    return {"created": created, "errors": errors, "created_count": len(created), "error_count": len(errors)}
