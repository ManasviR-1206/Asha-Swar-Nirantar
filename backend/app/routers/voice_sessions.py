"""Voice recording sessions and extracted visits.

One continuous recording can describe several beneficiaries. This router owns
the whole review workflow:

    POST /api/voice/sessions                      open / re-attach to a session
    POST /api/voice/sessions/{id}/extract         segment + extract + resolve identity
    GET  /api/voice/sessions/{id}                 session with its extracted visits
    PATCH /api/voice/sessions/{id}/visits/{temp}  the worker edits / rejects a visit
    POST /api/voice/sessions/{id}/save            persist the confirmed visits atomically

The identity rule enforced here: **an observation is never attached to a
beneficiary that was not identified.** Ambiguous or unnamed visits stay
pending until the worker decides.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.data_scope import visible_beneficiaries, visible_households
from app.database import get_db
from app.models import (
    AshaWorker,
    Beneficiary,
    ExtractedVisit,
    Household,
    VisitRecord,
    VoiceRecordingSession,
)
from app.routers.dashboard import broadcast_dashboard_event
from app.routers.visits import _process_single_visit
from app.schemas import (
    ExtractedVisitOut,
    SessionCreate,
    SessionExtractResponse,
    SessionOut,
    SessionSaveRequest,
    SessionSaveResponse,
    VisitPatch,
)
from app.services import gnani
from app.services import identity as identity_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice/sessions", tags=["voice-sessions"], dependencies=[Depends(get_current_worker)])


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _get_session(db: Session, session_id: int) -> VoiceRecordingSession:
    session = db.query(VoiceRecordingSession).filter(VoiceRecordingSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Recording session not found")
    return session


def _household_label(db: Session, household_id: Optional[int]) -> Optional[str]:
    if household_id is None:
        return None
    hh = visible_households(db.query(Household)).filter(Household.id == household_id).first()
    if hh is None:
        return None
    return f"{hh.village} household ({hh.qr_id})" if hh.village else hh.qr_id


def _visit_out(db: Session, visit: ExtractedVisit) -> ExtractedVisitOut:
    try:
        structured = json.loads(visit.structured or "{}")
    except (ValueError, TypeError):
        structured = {}
    try:
        candidates = json.loads(visit.candidates or "[]")
    except (ValueError, TypeError):
        candidates = []
    personal = dict(structured.get("personal_details") or {})
    beneficiary = None
    if visit.beneficiary_id is not None:
        beneficiary = (
            visible_beneficiaries(db.query(Beneficiary))
            .filter(Beneficiary.id == visit.beneficiary_id)
            .first()
        )
    if candidates:
        visible_ids = {
            row[0] for row in visible_beneficiaries(db.query(Beneficiary.id)).all()
        }
        candidates = [
            candidate
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("id") in visible_ids
        ]
    household_id = visit.household_id
    if household_id is not None and _household_label(db, household_id) is None:
        household_id = None
    # Name is an extraction value, never the name of a database beneficiary.
    # If a visit is manually linked later, preserve the spoken name and ID separately.
    spoken_name = (
        visit.beneficiary_name
        or personal.get("name")
        or structured.get("raw_structured", {}).get("beneficiary_name")
        or structured.get("raw_structured", {}).get("name")
    )
    spoken_name = str(spoken_name).strip() if spoken_name else None
    if spoken_name:
        personal["name"] = spoken_name
    else:
        personal.pop("name", None)
    return ExtractedVisitOut(
        temp_id=visit.temp_id,
        visit_id=visit.temp_id,
        beneficiary_id=beneficiary.id if beneficiary is not None else None,
        beneficiary_name=spoken_name,
        household_id=household_id,
        household_label=_household_label(db, household_id),
        category=visit.category,
        visit_date=visit.visit_date,
        raw_structured=structured.get("raw_structured") or structured,
        personal_details=personal,
        measurements=structured.get("measurements") or {},
        observations=structured.get("observations") or [],
        follow_ups=structured.get("follow_ups") or [],
        identity_status=visit.identity_status,
        identity_reason=visit.identity_reason,
        candidates=candidates,
        clarification_required=visit.clarification_required,
        status=visit.status,
        boundary_reason=structured.get("boundary_reason", ""),
        segment_index=structured.get("segment_index", 0),
    )


def _session_meta(session: VoiceRecordingSession) -> dict[str, Any]:
    """The JSON blob stored on the session (scenario, household visits, ...)."""
    try:
        stored = json.loads(session.transcript or "{}")
    except (ValueError, TypeError):
        return {}
    return stored if isinstance(stored, dict) else {}


def _session_out(db: Session, session: VoiceRecordingSession) -> SessionOut:
    visits = (
        db.query(ExtractedVisit)
        .filter(ExtractedVisit.session_id == session.id)
        .order_by(ExtractedVisit.id)
        .all()
    )
    extra = _session_meta(session)
    return SessionOut(
        id=session.id,
        client_session_id=session.client_session_id,
        language=session.language,
        status=session.status,
        transcript=_session_transcript(session),
        mode=session.mode,
        duration_ms=session.duration_ms,
        scenario=extra.get("scenario"),
        visits=[_visit_out(db, v) for v in visits],
        household_visits=extra.get("household_visits") or [],
        corrections=extra.get("corrections") or [],
        danger_flags=extra.get("danger_flags") or [],
    )


# ----------------------------------------------------------------------
# endpoints
# ----------------------------------------------------------------------
@router.post("", response_model=SessionOut)
def open_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    """Open a recording session, or re-attach to the one with this client id."""
    session = (
        db.query(VoiceRecordingSession)
        .filter(
            VoiceRecordingSession.client_session_id == payload.client_session_id,
            VoiceRecordingSession.worker_id == worker.id,
        )
        .first()
    )
    if session is None:
        session = VoiceRecordingSession(
            worker_id=worker.id,
            client_session_id=payload.client_session_id,
            language=payload.language,
            provider=payload.provider,
            transcript=payload.transcript,
            duration_ms=payload.duration_ms,
            mode=payload.mode,
            status="recording",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session.transcript = payload.transcript or session.transcript
        session.duration_ms = payload.duration_ms or session.duration_ms
        session.language = payload.language or session.language
        session.provider = payload.provider or session.provider
        db.commit()
        db.refresh(session)
    return _session_out(db, session)


def _extract_session_impl(session: VoiceRecordingSession, db: Session, worker: AshaWorker) -> SessionExtractResponse:
    """Segment the transcript, extract each visit and resolve every identity."""
    transcript = _session_transcript(session)
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="The session has no transcript to extract.")

    t0 = time.perf_counter()
    result, mode = gnani.extract_fields_multi(transcript, session.language)
    t_extract = time.perf_counter()
    from app.rules import detect_danger_signs

    result["danger_flags"] = detect_danger_signs(transcript, structured=result)
    t_danger = time.perf_counter()

    # ---- persist the extracted visits, each with its own identity ----
    db.query(ExtractedVisit).filter(ExtractedVisit.session_id == session.id).delete(
        synchronize_session=False
    )
    db.flush()

    saved_out: list[ExtractedVisitOut] = []
    for idx, raw_visit in enumerate(result.get("visits") or []):
        raw_visit = gnani._normalize_visit_names(raw_visit)
        temp_id = raw_visit.get("visit_id") or f"visit-{idx + 1}"
        name = raw_visit.get("beneficiary_name")
        personal = raw_visit.get("personal_details") or {}
        raw_structured = raw_visit.get("raw_structured") or {}
        if not name:
            fallback = gnani._extract_demo(transcript)
            name = fallback.get("beneficiary_name")
            if name:
                raw_visit["beneficiary_name"] = name
                personal = dict(personal)
                personal["name"] = name
                raw_visit["personal_details"] = personal
                raw_structured = dict(raw_structured)
                raw_structured["beneficiary_name"] = name
                raw_visit["raw_structured"] = raw_structured

        household_id = None
        hh_label = raw_visit.get("household_id")
        if hh_label:
            hh = identity_service.find_household_by_label(db, hh_label)
            if hh is not None:
                household_id = hh.id

        # Extraction-first: do NOT auto-search beneficiary database.
        # The worker can manually link an existing beneficiary or register a new one.
        stored = dict(raw_visit)
        stored["raw_structured"] = raw_structured
        stored["boundary_reason"] = raw_visit.get("boundary_reason", "")
        stored["segment_index"] = raw_visit.get("segment_index", idx)

        identity_status = "unresolved"
        identity_reason = "Extracted from transcript. Link beneficiary manually before saving." if name else "Beneficiary name not extracted. Select or register manually before saving."
        ev = ExtractedVisit(
            session_id=session.id,
            temp_id=temp_id,
            beneficiary_id=None,
            household_id=household_id,
            beneficiary_name=name,
            visit_date=_parse_visit_date(raw_structured),
            category=raw_visit.get("category") or "general",
            structured=json.dumps(stored),
            identity_status=identity_status,
            identity_reason=identity_reason[:250],
            candidates=json.dumps([]),
            clarification_required=False,
            status="pending",
        )
        db.add(ev)
        db.flush()
        saved_out.append(_visit_out(db, ev))

    session.status = "extracted"
    session.mode = mode
    session.transcript = json.dumps(
        {
            "transcript": transcript,
            "scenario": result.get("scenario"),
            "household_visits": result.get("household_visits") or [],
            "corrections": result.get("corrections") or [],
            "danger_flags": result.get("danger_flags") or [],
        }
    )
    db.commit()
    db.refresh(session)

    total_ms = int((time.perf_counter() - t0) * 1000)
    extract_ms = int((t_extract - t0) * 1000)
    danger_ms = int((t_danger - t_extract) * 1000)
    logger.info("[voice-extract] session=%s extract_ms=%s danger_ms=%s total_ms=%s visits=%s mode=%s", session.id, extract_ms, danger_ms, total_ms, len(saved_out), mode)

    out = _session_out(db, session)
    return SessionExtractResponse(**out.model_dump())


@router.post("/{session_id}/extract", response_model=SessionExtractResponse)
def extract_session(
    session_id: int,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    """Segment the transcript, extract each visit and resolve every identity."""
    session = _get_session(db, session_id)
    return _extract_session_impl(session, db, worker)


@router.post("/extract-direct", response_model=SessionExtractResponse)
def extract_direct(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    """Open/reuse a session and extract in one round trip."""
    session = (
        db.query(VoiceRecordingSession)
        .filter(
            VoiceRecordingSession.client_session_id == payload.client_session_id,
            VoiceRecordingSession.worker_id == worker.id,
        )
        .first()
    )
    if session is None:
        session = VoiceRecordingSession(
            worker_id=worker.id,
            client_session_id=payload.client_session_id,
            language=payload.language,
            provider=payload.provider,
            transcript=payload.transcript,
            duration_ms=payload.duration_ms,
            mode=payload.mode,
            status="recording",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session.transcript = payload.transcript or session.transcript
        session.duration_ms = payload.duration_ms or session.duration_ms
        session.language = payload.language or session.language
        session.provider = payload.provider or session.provider
        db.commit()
        db.refresh(session)
    return _extract_session_impl(session, db, worker)



@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    return _session_out(db, session)


@router.patch("/{session_id}/visits/{temp_id}", response_model=ExtractedVisitOut)
def patch_visit(
    session_id: int,
    temp_id: str,
    patch: VisitPatch,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    """The ASHA worker edits or rejects one extracted visit."""
    session = _get_session(db, session_id)
    visit = (
        db.query(ExtractedVisit)
        .filter(ExtractedVisit.session_id == session.id, ExtractedVisit.temp_id == temp_id)
        .first()
    )
    if visit is None:
        raise HTTPException(status_code=404, detail="Extracted visit not found")

    try:
        stored = json.loads(visit.structured or "{}")
    except (ValueError, TypeError):
        stored = {}

    if patch.beneficiary_id is not None:
        ben = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.id == patch.beneficiary_id).first()
        if ben is None:
            raise HTTPException(status_code=404, detail="Beneficiary not found")
        visit.beneficiary_id = ben.id
        visit.beneficiary_name = ben.name
        visit.identity_status = "resolved"
        visit.identity_reason = f"Chosen by the ASHA worker ({ben.name})."
        visit.clarification_required = False
        visit.candidates = "[]"
        stored.setdefault("personal_details", {})["name"] = ben.name
    elif patch.beneficiary_name is not None:
        visit.beneficiary_name = patch.beneficiary_name
        stored.setdefault("personal_details", {})["name"] = patch.beneficiary_name

    if patch.household_id is not None:
        household = visible_households(db.query(Household)).filter(Household.id == patch.household_id).first()
        if household is None:
            raise HTTPException(status_code=404, detail="Household not found")
        visit.household_id = patch.household_id
    if patch.category is not None:
        visit.category = patch.category
        stored["category"] = patch.category
    if patch.visit_date is not None:
        visit.visit_date = patch.visit_date
        stored.setdefault("raw_structured", {})["visit_date"] = patch.visit_date.isoformat()
    if patch.raw_structured is not None:
        stored["raw_structured"] = patch.raw_structured
    if patch.status is not None:
        visit.status = patch.status

    visit.structured = json.dumps(stored)
    db.commit()
    db.refresh(visit)
    return _visit_out(db, visit)


@router.post("/{session_id}/save", response_model=SessionSaveResponse)
def save_session(
    session_id: int,
    payload: SessionSaveRequest,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    """Persist the confirmed visits of a session in one transaction.

    Only visits the worker confirmed are saved. A visit whose identity is
    still ambiguous or unresolved is reported as skipped, never written
    against an arbitrary beneficiary.
    """
    session = _get_session(db, session_id)
    confirmation = payload.confirmation
    if confirmation is None or not confirmation.confirmed:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required before saving. Review the visit and confirm before saving.")
    if confirmation.method not in {"voice", "ui_fallback"}:
        raise HTTPException(status_code=400, detail="Invalid confirmation method.")
    visits = (
        db.query(ExtractedVisit)
        .filter(ExtractedVisit.session_id == session.id)
        .order_by(ExtractedVisit.id)
        .all()
    )
    # Idempotency / duplicate-save protection: already saved session returns existing result.
    if session.status == "saved":
        saved_visits = []
        for v in visits:
            if v.saved_visit_id:
                vr = db.query(VisitRecord).filter(VisitRecord.id == v.saved_visit_id).first()
                if vr:
                    saved_visits.append({
                        "id": vr.id, "temp_id": v.temp_id, "beneficiary_id": vr.beneficiary_id,
                        "beneficiary_name": v.beneficiary_name, "visit_date": vr.visit_date.isoformat(),
                        "category": vr.category, "source": vr.source, "structured": {}, "alerts_count": 0, "follow_up": None,
                    })
        return SessionSaveResponse(session_id=session.id, saved_visits=saved_visits, saved_household_visits=[], skipped_visits=[], total_saved=len(saved_visits), alerts=[])
    by_temp = {v.temp_id: v for v in visits}

    # Each patch carries the temp id of the visit it applies to.
    patch_by_temp: dict[str, VisitPatch] = {}
    for item in payload.visits:
        temp = item.temp_id
        if temp:
            patch_by_temp[temp] = item

    saved_visits: list[dict[str, Any]] = []
    saved_hh: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    all_alerts: list[dict[str, Any]] = []

    try:
        for visit in visits:
            if visit.status == "rejected":
                continue
            if visit.saved_visit_id:
                existing_vr = db.query(VisitRecord).filter(VisitRecord.id == visit.saved_visit_id).first()
                if existing_vr:
                    saved_visits.append({
                        "id": existing_vr.id, "temp_id": visit.temp_id, "beneficiary_id": existing_vr.beneficiary_id,
                        "beneficiary_name": visit.beneficiary_name, "visit_date": existing_vr.visit_date.isoformat(),
                        "category": existing_vr.category, "source": existing_vr.source, "structured": {}, "alerts_count": 0, "follow_up": None,
                    })
                continue
            patch = patch_by_temp.get(visit.temp_id)
            if patch is not None:
                if patch.beneficiary_id is not None:
                    ben = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.id == patch.beneficiary_id).first()
                    if ben is None:
                        raise HTTPException(status_code=404, detail="Beneficiary not found")
                    visit.beneficiary_id = ben.id
                    visit.beneficiary_name = ben.name
                    visit.identity_status = "resolved"
                    visit.clarification_required = False
                if patch.household_id is not None:
                    household = visible_households(db.query(Household)).filter(Household.id == patch.household_id).first()
                    if household is None:
                        raise HTTPException(status_code=404, detail="Household not found")
                    visit.household_id = patch.household_id
                if patch.category is not None:
                    visit.category = patch.category
                if patch.raw_structured is not None:
                    try:
                        stored = json.loads(visit.structured or "{}")
                    except (ValueError, TypeError):
                        stored = {}
                    stored["raw_structured"] = patch.raw_structured
                    visit.structured = json.dumps(stored)
                if patch.status is not None:
                    visit.status = patch.status

            if visit.status != "confirmed":
                # Not confirmed by the worker -> not saved.
                skipped.append({
                    "temp_id": visit.temp_id,
                    "reason": "not_confirmed",
                    "identity_status": visit.identity_status,
                })
                continue

            if not visit.beneficiary_id:
                skipped.append({
                    "temp_id": visit.temp_id,
                    "reason": visit.identity_status or "unresolved",
                    "identity_status": visit.identity_status,
                    "candidate_count": len(json.loads(visit.candidates or "[]")),
                })
                continue

            try:
                stored = json.loads(visit.structured or "{}")
            except (ValueError, TypeError):
                stored = {}
            structured = stored.get("raw_structured") or {}
            structured.setdefault("visit_date", visit.visit_date.isoformat())

            transcript = _session_transcript(session)
            record, ben, alerts, follow_up, alert_generation_error = _process_single_visit(
                db=db,
                worker=worker,
                beneficiary_id=visit.beneficiary_id,
                beneficiary_name=visit.beneficiary_name,
                structured=structured,
                transcript=transcript,
                language=session.language,
                visit_type=visit.category,
                create_if_missing=False,
                household_id=visit.household_id,
            )
            visit.status = "saved"
            visit.saved_visit_id = record.id
            saved_visits.append({
                "id": record.id,
                "temp_id": visit.temp_id,
                "beneficiary_id": ben.id,
                "beneficiary_name": ben.name,
                "visit_date": record.visit_date.isoformat(),
                "category": record.category,
                "source": record.source,
                "structured": structured,
                "alerts_count": len(alerts),
                "follow_up": follow_up,
                "alert_generation_error": alert_generation_error,
            })
            all_alerts.extend(alerts)

        for hh_item in payload.household_visits:
            hh_id = hh_item.get("household_id")
            hh = None
            if hh_id:
                hh = db.query(Household).filter(
                    (Household.id == hh_id) | (Household.qr_id == str(hh_id))
                ).first()
            if hh is None:
                hh = db.query(Household).first()
            if hh is None:
                continue
            obs = hh_item.get("household_observations") or {}
            from app.models import HouseholdVisit

            hh_visit = HouseholdVisit(
                household_id=hh.id,
                worker_id=worker.id,
                visit_date=_parse_visit_date(obs),
                notes=json.dumps(obs),
                source="voice" if hh_item.get("transcript") else "manual",
            )
            db.add(hh_visit)
            db.flush()
            saved_hh.append({
                "id": hh_visit.id,
                "household_id": hh.id,
                "visit_date": hh_visit.visit_date.isoformat(),
                "source": hh_visit.source,
            })

        session.status = "saved"
        db.commit()
    except Exception:
        db.rollback()
        raise

    if saved_visits:
        broadcast_dashboard_event("multi_visits_saved", {
            "count": len(saved_visits),
            "beneficiary_names": [v["beneficiary_name"] for v in saved_visits],
            "visit_date": date.today().isoformat(),
        })

    alert_errors = [v.get("alert_generation_error") for v in saved_visits if v.get("alert_generation_error")]
    return SessionSaveResponse(
        session_id=session.id,
        saved_visits=saved_visits,
        saved_household_visits=saved_hh,
        skipped_visits=skipped,
        total_saved=len(saved_visits) + len(saved_hh),
        alerts=all_alerts,
        alert_generation_error="; ".join(alert_errors) if alert_errors else None,
    )


def _session_transcript(session: VoiceRecordingSession) -> str:
    try:
        stored = json.loads(session.transcript or "{}")
        if isinstance(stored, dict):
            return str(stored.get("transcript") or "")
    except (ValueError, TypeError):
        pass
    return session.transcript or ""


def _parse_visit_date(structured: dict) -> date:
    raw = structured.get("visit_date") if isinstance(structured, dict) else None
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            pass
    return date.today()
