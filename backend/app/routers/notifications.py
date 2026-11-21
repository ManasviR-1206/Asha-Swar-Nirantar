"""Notification endpoints: SMS (TextBee/legacy/demo), PDF reports, stats, and consent history.

Every response states plainly whether the message was actually sent, submitted to a provider,
or only simulated.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import get_env
from app.auth import get_current_worker
from app.database import get_db
from app.models import AshaWorker, Beneficiary, ConsentRecord, FollowUp, PdfReport, SmsNotification
from app.schemas import NotificationStats, PdfReportListResponse, SmsNotificationListResponse, SmsNotificationOut
from app.services import notifications as notify
from app.services import pdf as pdf_service
from app.services.textbee import sms_compliance_approved, textbee_enabled

router = APIRouter(prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(get_current_worker)])


def _report_dir() -> str:
    base = get_env("REPORT_DIR") or os.path.join(os.getcwd(), "backend", "generated_reports")
    return base


class SmsSendRequest(BaseModel):
    beneficiary_id: int
    type: str = "anc"
    language: str = "en"
    body: Optional[str] = None
    follow_up_id: Optional[int] = None
    consent_granted: bool = False


class PreviewRequest(BaseModel):
    beneficiary_id: int
    type: str = "anc"
    language: str = "en"


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------
@router.post("/sms/preview")
def preview_sms(payload: PreviewRequest, db: Session = Depends(get_db)):
    ben = db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first()
    if ben is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    phone = notify.validate_phone(ben.phone)
    configured = notify.sms_provider_configured()
    compliance = sms_compliance_approved()
    demo_label = notify.DEMO_LABEL
    if configured:
        demo_label = "SMS provider configured and compliance-approved. Message will be submitted when sent (subject to consent, preferences, and provider/device availability)."
    elif not compliance:
        demo_label = "SMS is disabled by default until hackathon/organizer compliance is explicitly approved. " + notify.DEMO_LABEL
    elif not textbee_enabled():
        demo_label = "SMS delivery is disabled. " + notify.DEMO_LABEL
    return {
        "beneficiary_id": ben.id,
        "beneficiary_name": ben.name,
        "phone": phone or (ben.phone or ""),
        "phone_valid": bool(phone),
        "body": notify.build_sms_body(payload.type, payload.language),
        "type": payload.type,
        "language": payload.language,
        "is_demo": not configured,
        "demo_label": demo_label,
        "sms_provider_configured": configured,
        "sms_compliance_approved": compliance,
    }


@router.post("/sms/send", response_model=SmsNotificationOut)
async def send_sms(
    payload: SmsSendRequest,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    ben = db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first()
    if ben is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    if not payload.consent_granted:
        raise HTTPException(
            status_code=400,
            detail="Consent is required before a notification can be sent to a beneficiary.",
        )

    consent = notify.record_consent(db, ben, "sms", True, "follow_up_reminder", worker.id)
    try:
        result = await notify.send_sms_notification(
            db,
            beneficiary=ben,
            follow_up_type=payload.type,
            language=payload.language,
            body=payload.body,
            worker_id=worker.id,
            follow_up_id=payload.follow_up_id,
            consent=consent,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Could not process the SMS request. Please try again.")

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("note", "Could not send the SMS."))
    record = db.query(SmsNotification).filter(SmsNotification.id == result["id"]).first()
    if record is None:
        raise HTTPException(status_code=500, detail="SMS record could not be loaded after sending.")
    return _sms_out(record)


@router.get("/sms", response_model=SmsNotificationListResponse)
def list_sms(db: Session = Depends(get_db)):
    rows = (
        db.query(SmsNotification)
        .order_by(SmsNotification.created_at.desc())
        .limit(200)
        .all()
    )
    return {"notifications": [_sms_out(r) for r in rows]}


def _sms_out(r: SmsNotification) -> dict[str, Any]:
    return {
        "id": r.id,
        "beneficiary_id": r.beneficiary_id,
        "type": r.type,
        "phone": r.phone,
        "body": r.body,
        "language": r.language,
        "status": r.status,
        "provider_note": r.provider_note,
        "is_demo": r.is_demo,
        "created_at": r.created_at,
        "sent_at": r.sent_at,
    }


# ---------------------------------------------------------------------------
# PDF reports (retained; reports are not email notifications)
# ---------------------------------------------------------------------------
@router.get("/reports", response_model=PdfReportListResponse)
def list_reports(db: Session = Depends(get_db)):
    rows = db.query(PdfReport).order_by(PdfReport.generated_at.desc()).limit(200).all()
    return {
        "reports": [
            {
                "id": r.id,
                "beneficiary_id": r.beneficiary_id,
                "filename": r.filename,
                "size_bytes": r.size_bytes,
                "generated_at": r.generated_at,
            }
            for r in rows
        ]
    }


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db)):
    record = db.query(PdfReport).filter(PdfReport.id == report_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Report not found")

    base_dir = os.path.abspath(_report_dir())
    path = os.path.abspath(record.storage_path or "")
    # Guard against path traversal / serving files outside the report directory.
    if not path.startswith(base_dir + os.sep):
        raise HTTPException(status_code=404, detail="The report file is no longer available.")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="The report file is no longer available.")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=os.path.basename(record.filename or path),
    )


@router.get("/reports/preview/{beneficiary_id}")
def preview_report(beneficiary_id: int, db: Session = Depends(get_db)):
    """Render the report for a beneficiary without storing it."""
    ben = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    if ben is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    pdf_bytes = pdf_service.build_followup_report(db, ben)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="followup-{ben.qr_id}.pdf"'},
    )


# ---------------------------------------------------------------------------
# stats + consent
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=NotificationStats)
def notification_stats(db: Session = Depends(get_db)):
    sms_rows = db.query(SmsNotification).all()
    pdf_rows = db.query(PdfReport).all()
    upcoming = db.query(FollowUp).filter(FollowUp.status == "upcoming").count()
    return {
        "sms_total": len(sms_rows),
        "sms_demo": sum(1 for r in sms_rows if r.is_demo),
        "sms_real": sum(1 for r in sms_rows if not r.is_demo),
        "pending": sum(1 for r in sms_rows if r.status == "pending"),
        "failed": sum(1 for r in sms_rows if r.status == "failed"),
        "pdf_reports": len(pdf_rows),
        "upcoming_followups": upcoming,
        "sms_provider_configured": notify.sms_provider_configured(),
        "sms_enabled": textbee_enabled(),
        "sms_compliance_approved": sms_compliance_approved(),
        "sms_provider": notify.sms_provider_name(),
    }


@router.get("/consent/{beneficiary_id}")
def list_consent(beneficiary_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(ConsentRecord)
        .filter(ConsentRecord.beneficiary_id == beneficiary_id)
        .order_by(ConsentRecord.recorded_at.desc())
        .all()
    )
    return {
        "consent": [
            {
                "id": r.id,
                "channel": r.channel,
                "purpose": r.purpose,
                "granted": r.granted,
                "recorded_at": r.recorded_at,
            }
            for r in rows
        ]
    }
