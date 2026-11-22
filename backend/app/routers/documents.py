"""Secure medical document upload, preview, download, and audited removal.

Files are stored outside public/static directories under backend/data/uploads/documents.
Access is authenticated and path traversal is prevented by using DB-resolved stored paths only.
"""
from __future__ import annotations

import mimetypes
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import AshaWorker, Beneficiary, FieldAudit, Household, UploadedDocument

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(get_current_worker)])

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
UPLOAD_ROOT = (BASE_DIR / "data" / "uploads" / "documents").resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic"}
ALLOWED_MIME_PREFIXES = ("image/", "application/pdf")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CATEGORIES = {
    "prescription",
    "lab_report",
    "blood_test",
    "scan_report",
    "vaccination_card",
    "pregnancy_record",
    "health_card",
    "other",
}


def _safe_name(original: str) -> str:
    name = os.path.basename(original or "document")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "document"
    return name[:120]


def _out(d: UploadedDocument) -> dict:
    return {
        "id": d.id,
        "beneficiary_id": d.beneficiary_id,
        "household_id": d.household_id,
        "original_filename": d.original_filename,
        "mime_type": d.mime_type,
        "size_bytes": d.size_bytes,
        "category": getattr(d, "category", "other") or "other",
        "upload_source": d.upload_source,
        "uploaded_by": d.uploaded_by,
        "verified": d.verified,
        "ocr_status": d.ocr_status,
        "notes": d.notes,
        "is_deleted": getattr(d, "is_deleted", False),
        "deleted_at": getattr(d, "deleted_at", None),
        "deleted_by": getattr(d, "deleted_by", None),
        "delete_reason": getattr(d, "delete_reason", "") or "",
        "created_at": d.created_at,
        "preview_url": f"/api/documents/{d.id}/preview" if not getattr(d, "is_deleted", False) else None,
        "download_url": f"/api/documents/{d.id}/download" if not getattr(d, "is_deleted", False) else None,
    }


def _is_admin(worker: AshaWorker | None) -> bool:
    return bool(worker and getattr(worker, "role", "asha") == "admin")


def _can_access_beneficiary(worker: AshaWorker, beneficiary: Beneficiary | None) -> bool:
    if _is_admin(worker):
        return True
    if beneficiary is None:
        return False
    assigned = getattr(beneficiary, "assigned_worker_id", None)
    if assigned and assigned != worker.id:
        return False
    # Unassigned beneficiaries are treated as team-accessible in current workflows.
    return True


def _require_beneficiary_access(worker: AshaWorker, beneficiary: Beneficiary | None):
    if not _can_access_beneficiary(worker, beneficiary):
        raise HTTPException(status_code=403, detail="Not authorized to access this beneficiary's documents")


def _can_access_document(db: Session, worker: AshaWorker, doc: UploadedDocument) -> bool:
    if _is_admin(worker):
        return True
    if doc.beneficiary_id:
        ben = db.query(Beneficiary).filter(Beneficiary.id == doc.beneficiary_id).first()
        return _can_access_beneficiary(worker, ben)
    if doc.household_id:
        # Household-only document: allow only if at least one beneficiary in household is accessible
        # and none are explicitly assigned to another worker in a conflicting way? Conservative team rule:
        # permit when household has no beneficiaries assigned to other workers exclusively; admin otherwise.
        bens = db.query(Beneficiary).filter(Beneficiary.household_id == doc.household_id).all()
        if not bens:
            return True
        return any(_can_access_beneficiary(worker, b) for b in bens)
    return False


def _require_document_access(db: Session, worker: AshaWorker, doc: UploadedDocument):
    if not _can_access_document(db, worker, doc):
        raise HTTPException(status_code=403, detail="Not authorized to access this document")


def _ensure_target(db: Session, worker: AshaWorker, beneficiary_id: int | None, household_id: int | None):
    if not beneficiary_id and not household_id:
        raise HTTPException(status_code=400, detail="beneficiary_id or household_id is required")
    b = None
    h = None
    if beneficiary_id:
        b = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
        if b is None:
            raise HTTPException(status_code=404, detail="Beneficiary not found")
        _require_beneficiary_access(worker, b)
    if household_id:
        h = db.query(Household).filter(Household.id == household_id).first()
        if h is None:
            raise HTTPException(status_code=404, detail="Household not found")
        # If a specific beneficiary is also provided, beneficiary access check above is sufficient.
        # For household-only uploads, restrict to admin unless household has an accessible beneficiary context.
        if not beneficiary_id and not _is_admin(worker):
            bens = db.query(Beneficiary).filter(Beneficiary.household_id == household_id).all()
            if bens and not any(_can_access_beneficiary(worker, bb) for bb in bens):
                raise HTTPException(status_code=403, detail="Not authorized to upload documents for this household")
    return b, h


@router.get("/beneficiary/{beneficiary_id}")
def list_beneficiary_documents(
    beneficiary_id: int,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    ben = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    if ben is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    _require_beneficiary_access(worker, ben)
    q = db.query(UploadedDocument).filter(UploadedDocument.beneficiary_id == beneficiary_id)
    if not include_deleted:
        q = q.filter(getattr(UploadedDocument, "is_deleted", False) == False)  # noqa: E712
    rows = q.order_by(UploadedDocument.created_at.desc(), UploadedDocument.id.desc()).all()
    return {"documents": [_out(r) for r in rows]}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    beneficiary_id: int | None = Form(None),
    household_id: int | None = Form(None),
    category: str = Form("other"),
    notes: str = Form(""),
    upload_source: str = Form("upload"),
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    _ensure_target(db, worker, beneficiary_id, household_id)
    category = (category or "other").strip().lower()
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid document category")
    upload_source = (upload_source or "upload").strip().lower()
    if upload_source not in {"upload", "camera"}:
        upload_source = "upload"

    original = file.filename or "document"
    ext = Path(original).suffix.lower()
    content_type = (file.content_type or mimetypes.guess_type(original)[0] or "").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Allowed: PDF, JPG, PNG, WEBP, HEIC")
    if not any(content_type.startswith(p) if p.endswith("/") else content_type == p for p in ("image/", "application/pdf")):
        # allow common cases where browser omits precise type but extension is allowed
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file content type")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    safe_base = _safe_name(original)
    stored = f"{datetime.utcnow().strftime('%Y%m%d')}_{secrets.token_hex(8)}_{safe_base}"
    target_path = (UPLOAD_ROOT / stored).resolve()
    if UPLOAD_ROOT not in target_path.parents:
        raise HTTPException(status_code=400, detail="Invalid storage path")

    with open(target_path, "wb") as f:
        f.write(data)

    doc = UploadedDocument(
        beneficiary_id=beneficiary_id,
        household_id=household_id,
        original_filename=os.path.basename(original)[:256],
        stored_filename=stored,
        storage_path=str(target_path),
        mime_type=content_type or (mimetypes.guess_type(original)[0] or "application/octet-stream"),
        size_bytes=len(data),
        category=category,
        upload_source=upload_source,
        ocr_status="not_run",
        extracted_data="{}",
        qr_data="",
        verified=False,
        uploaded_by=worker.id,
        notes=(notes or "").strip(),
        is_deleted=False,
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.flush()
    db.add(FieldAudit(
        entity_type="uploaded_document",
        entity_id=doc.id,
        field_name="document",
        old_value="",
        new_value=f"uploaded:{doc.original_filename}",
        changed_by=worker.id,
        reason=f"Uploaded document (category={category})",
        source="upload",
        changed_at=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(doc)
    return {"document": _out(doc)}


def _get_doc(db: Session, document_id: int) -> UploadedDocument:
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == document_id).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _file_response(doc: UploadedDocument, inline: bool):
    if getattr(doc, "is_deleted", False):
        raise HTTPException(status_code=404, detail="Document not available")
    path = Path(doc.storage_path).resolve()
    if UPLOAD_ROOT not in path.parents and path != UPLOAD_ROOT:
        raise HTTPException(status_code=403, detail="Access denied")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file not found")
    media = doc.mime_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    disp = "inline" if inline else "attachment"
    filename = doc.original_filename or path.name
    return FileResponse(path=str(path), media_type=media, filename=filename, content_disposition_type=disp)


@router.get("/{document_id}/preview")
def preview_document(document_id: int, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    doc = _get_doc(db, document_id)
    _require_document_access(db, worker, doc)
    return _file_response(doc, inline=True)


@router.get("/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    doc = _get_doc(db, document_id)
    _require_document_access(db, worker, doc)
    return _file_response(doc, inline=False)


@router.post("/{document_id}/delete")
def delete_document(
    document_id: int,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    doc = _get_doc(db, document_id)
    _require_document_access(db, worker, doc)
    if getattr(doc, "is_deleted", False):
        return {"document": _out(doc), "status": "already_deleted"}
    doc.is_deleted = True
    doc.deleted_at = datetime.utcnow()
    doc.deleted_by = worker.id
    doc.delete_reason = (reason or "").strip()
    db.add(FieldAudit(
        entity_type="uploaded_document",
        entity_id=doc.id,
        field_name="document",
        old_value=doc.original_filename or "document",
        new_value="deleted",
        changed_by=worker.id,
        reason=doc.delete_reason or "Removed by authorized user",
        source="document_remove",
        changed_at=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(doc)
    return {"document": _out(doc), "status": "deleted"}