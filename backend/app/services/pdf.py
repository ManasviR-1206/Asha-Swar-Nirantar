"""Follow-up PDF report generation.

Reports are built from the actual database records for one beneficiary —
never from hardcoded sample data. The layout follows the product's pink
healthcare identity.

Only information the ASHA worker legitimately needs for a follow-up is
included; the report deliberately avoids clinical detail that would be
unnecessary in a reminder document.
"""
from __future__ import annotations

import io
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import (
    Beneficiary,
    FollowUp,
    ImmunisationRecord,
    NewbornRecord,
    PregnancyRecord,
    VisitRecord,
)

# Product palette (Phase 10 — premium pink healthcare identity).
PINK = "#E8A8B8"
DEEP_ROSE = "#98566C"
BLUSH = "#F6DCE3"
IVORY = "#FFF8F6"
SLATE = "#34434A"
SAGE = "#A8C8B5"
RULE = "#E7D4DA"


def _fmt_date(value: Optional[date]) -> str:
    if value is None:
        return "—"
    try:
        return value.strftime("%d %b %Y")
    except Exception:
        return str(value)


def _collect(db: Session, beneficiary: Beneficiary) -> dict[str, Any]:
    """Gather the real records for one beneficiary."""
    visits = (
        db.query(VisitRecord)
        .filter(VisitRecord.beneficiary_id == beneficiary.id)
        .order_by(VisitRecord.visit_date.desc())
        .all()
    )
    followups = (
        db.query(FollowUp)
        .filter(FollowUp.beneficiary_id == beneficiary.id)
        .order_by(FollowUp.due_date)
        .all()
    )
    pregnancy = (
        db.query(PregnancyRecord)
        .filter(PregnancyRecord.beneficiary_id == beneficiary.id)
        .order_by(PregnancyRecord.id.desc())
        .first()
    )
    newborn = (
        db.query(NewbornRecord)
        .filter(NewbornRecord.beneficiary_id == beneficiary.id)
        .order_by(NewbornRecord.id.desc())
        .first()
    )
    immunisation = (
        db.query(ImmunisationRecord)
        .filter(ImmunisationRecord.beneficiary_id == beneficiary.id)
        .order_by(ImmunisationRecord.date_given.desc())
        .first()
    )
    return {
        "visits": visits,
        "followups": followups,
        "pregnancy": pregnancy,
        "newborn": newborn,
        "immunisation": immunisation,
    }


def build_followup_report(db: Session, beneficiary: Beneficiary) -> bytes:
    """Render the A4 follow-up report for one beneficiary."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    data = _collect(db, beneficiary)
    visits = data["visits"]
    followups = data["followups"]
    last_visit = visits[0] if visits else None
    upcoming = [f for f in followups if f.status in ("upcoming", "overdue")]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Follow-up report — {beneficiary.name}",
        author="ASHA Swar Nirantar",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "H1", parent=styles["Heading1"], fontSize=19, leading=23,
        textColor=colors.HexColor(DEEP_ROSE), spaceAfter=2,
    )
    sub = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontSize=9, leading=12,
        textColor=colors.HexColor("#7C6A70"), spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=11.5, leading=14,
        textColor=colors.HexColor(DEEP_ROSE), spaceBefore=12, spaceAfter=5,
    )
    body = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=9.5, leading=13,
        textColor=colors.HexColor(SLATE),
    )
    cell = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=8.8, leading=11.5,
        textColor=colors.HexColor(SLATE),
    )
    cellHead = ParagraphStyle(
        "CellHead", parent=styles["Normal"], fontSize=8.5, leading=11,
        textColor=colors.white,
    )
    small = ParagraphStyle(
        "Small", parent=styles["Normal"], fontSize=8, leading=10.5,
        textColor=colors.HexColor("#8A7B80"),
    )

    story = []

    # ---------- header band ----------
    story.append(
        Table(
            [
                [
                    Paragraph(
                        '<font size="9" color="#FFFFFF">ASHA SWAR NIRANTAR</font><br/>'
                        '<font size="8" color="#F6DCE3">The Voice Pulse of Every Village</font>',
                        cellHead,
                    ),
                    Paragraph(
                        f'<font size="13" color="#FFFFFF"><b>Health Follow-up Report</b></font><br/>'
                        f'<font size="8" color="#F6DCE3">Generated {_fmt_date(date.today())}</font>',
                        cellHead,
                    ),
                ]
            ],
            colWidths=[90 * mm, 84 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(DEEP_ROSE)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]
            ),
        )
    )
    story.append(Spacer(1, 8))

    # ---------- beneficiary ----------
    story.append(Paragraph("Beneficiary", h2))
    story.append(
        Table(
            [
                [Paragraph("Name", cell), Paragraph(beneficiary.name, cell),
                 Paragraph("ASHA ID", cell), Paragraph(beneficiary.qr_id, cell)],
                [Paragraph("Age", cell), Paragraph(str(beneficiary.age), cell),
                 Paragraph("Category", cell), Paragraph(beneficiary.category.replace("_", " ").title(), cell)],
                [Paragraph("Village", cell), Paragraph(beneficiary.village or "—", cell),
                 Paragraph("Phone", cell), Paragraph(beneficiary.phone or "—", cell)],
            ],
            colWidths=[22 * mm, 50 * mm, 24 * mm, 78 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(IVORY)),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(DEEP_ROSE)),
                    ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor(DEEP_ROSE)),
                ]
            ),
        )
    )

    # ---------- last visit ----------
    story.append(Paragraph("Last recorded visit", h2))
    if last_visit:
        story.append(
            Paragraph(
                f"{_fmt_date(last_visit.visit_date)} · {last_visit.category.replace('_', ' ').title()} "
                f"· recorded by voice" if last_visit.source == "voice"
                else f"{_fmt_date(last_visit.visit_date)} · {last_visit.category.replace('_', ' ').title()}",
                body,
            )
        )
    else:
        story.append(Paragraph("No visit has been recorded yet.", body))

    # ---------- recent visits ----------
    story.append(Paragraph("Recent visits", h2))
    rows = [[
        Paragraph("Date", cellHead),
        Paragraph("Category", cellHead),
        Paragraph("Summary", cellHead),
    ]]
    for v in visits[:6]:
        rows.append([
            Paragraph(_fmt_date(v.visit_date), cell),
            Paragraph(v.category.replace("_", " ").title(), cell),
            Paragraph(_visit_summary(v), cell),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("—", cell), Paragraph("—", cell), Paragraph("No visits recorded.", cell)])
    story.append(
        Table(
            rows,
            colWidths=[28 * mm, 34 * mm, 112 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PINK)),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(IVORY), colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        )
    )

    # ---------- follow-ups ----------
    story.append(Paragraph("Follow-up due", h2))
    if upcoming:
        frows = [[Paragraph("Type", cellHead), Paragraph("Due date", cellHead), Paragraph("Status", cellHead)]]
        for f in upcoming[:6]:
            frows.append([
                Paragraph((f.type or "").replace("_", " ").title(), cell),
                Paragraph(_fmt_date(f.due_date), cell),
                Paragraph((f.status or "").title(), cell),
            ])
        story.append(
            Table(
                frows,
                colWidths=[56 * mm, 40 * mm, 78 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PINK)),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(IVORY), colors.white]),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ]
                ),
            )
        )
    else:
        story.append(Paragraph("No follow-up is currently scheduled.", body))

    # ---------- pending actions ----------
    actions = _pending_actions(data)
    story.append(Paragraph("Pending actions", h2))
    if actions:
        for a in actions:
            story.append(Paragraph(f"• {a}", body))
    else:
        story.append(Paragraph("Nothing pending for this beneficiary.", body))

    # ---------- footer ----------
    story.append(Spacer(1, 12))
    story.append(
        Table(
            [[Paragraph(
                "This report was generated by ASHA Swar Nirantar for the follow-up of the "
                "beneficiary named above. Please contact your ASHA worker if any detail is "
                "incorrect. This document contains information about a named person — please "
                "keep it safe.",
                small,
            )]],
            colWidths=[174 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BLUSH)),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(PINK)),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _visit_summary(visit: VisitRecord) -> str:
    """A short, non-diagnostic summary of one visit."""
    import json

    try:
        structured = json.loads(visit.notes or "{}")
    except (ValueError, TypeError):
        structured = {}
    parts: list[str] = []
    if structured.get("weeks_pregnant") is not None:
        parts.append(f"{structured['weeks_pregnant']} weeks pregnant")
    if structured.get("weight_kg") is not None:
        parts.append(f"Weight {structured['weight_kg']} kg")
    if structured.get("bp_sys") is not None and structured.get("bp_dia") is not None:
        parts.append(f"BP {structured['bp_sys']}/{structured['bp_dia']}")
    if structured.get("temperature") is not None:
        parts.append(f"Temperature {structured['temperature']} C")
    if structured.get("vaccine_name"):
        parts.append(f"{structured['vaccine_name']} given")
    if not parts:
        return "Visit recorded."
    return " · ".join(parts)


def _pending_actions(data: dict[str, Any]) -> list[str]:
    """Actions the ASHA worker still has to take for this beneficiary."""
    actions: list[str] = []
    for f in data["followups"]:
        if f.status == "overdue":
            actions.append(
                f"{f.type.replace('_', ' ').title()} follow-up was due {_fmt_date(f.due_date)} and needs attention."
            )
        elif f.status == "upcoming":
            actions.append(
                f"{f.type.replace('_', ' ').title()} follow-up is scheduled for {_fmt_date(f.due_date)}."
            )
    preg = data.get("pregnancy")
    if preg is not None and preg.weeks_pregnant is not None:
        actions.append(
            f"Antenatal care is in progress ({preg.weeks_pregnant} weeks at the last visit)."
        )
    newborn = data.get("newborn")
    if newborn is not None:
        actions.append("Newborn follow-up visits are due as per the immunisation schedule.")
    imm = data.get("immunisation")
    if imm is not None and imm.next_due_date:
        actions.append(f"Next immunisation dose is due {_fmt_date(imm.next_due_date)}.")
    return actions[:8]


def store_report(
    db: Session,
    beneficiary: Beneficiary,
    worker_id: Optional[int],
    directory: str,
) -> tuple[bytes, str, str]:
    """Render the report and write it to `directory`.

    Returns (pdf_bytes, filename, path).
    """
    from app.models import PdfReport

    pdf_bytes = build_followup_report(db, beneficiary)
    safe_name = "".join(ch for ch in beneficiary.name if ch.isalnum() or ch in " -_").strip() or "beneficiary"
    filename = f"followup-{safe_name.replace(' ', '-').lower()}-{beneficiary.qr_id}.pdf"
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)

    record = PdfReport(
        beneficiary_id=beneficiary.id,
        filename=filename,
        storage_path=path,
        size_bytes=len(pdf_bytes),
        generated_by=worker_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return pdf_bytes, filename, path
