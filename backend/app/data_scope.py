"""Visibility rules for local operational records vs explicitly enabled demo mode.

Normal ASHA worker mode shows only authorized operational records
(`registered`, `asha_verified`) and excludes synthetic demo, public/research,
and legacy hidden demo artifacts. Synthetic demo records remain in the database
for provenance/demo isolation but must not appear in normal operational views,
counts, histories, alerts, reminders, or SMS workflows.

When demo setup is explicitly enabled (`ENABLE_DEMO_SETUP`/`APP_MODE=demo`),
synthetic demo records may be visible for isolated demonstration, but they must
still be clearly labeled by origin and never disguised as real records.
"""
from sqlalchemy import and_, exists, func, or_, select

from app import demo_setup_enabled
from app.models import Beneficiary, Household, HouseholdMember


_DEMO_MARKER = "%[synthetic_demo]%"
_MARKED_FIELDS = (
    "name",
    "village",
    "address",
    "qr_id",
    "phone",
    "email",
    "registration_notes",
    "medical_conditions",
    "allergies",
    "current_medications",
    "child_health_notes",
    "emergency_contact",
)

# Origins allowed in local app views/analytics.
_LOCAL_VISIBLE_ORIGINS = ("registered", "asha_verified", "synthetic_demo")
_OPERATIONAL_ORIGINS = ("registered", "asha_verified")


def _is_synthetic_demo_origin(model) -> bool:
    return getattr(model, "data_origin", None) == "synthetic_demo"


def beneficiary_visible_expression(model=Beneficiary):
    if demo_setup_enabled():
        # Explicit demo mode: allow local/demo records for isolated demonstration,
        # but never expose public/research imports in operational views.
        return model.data_origin.notin_(("public_sample", "imported_research"))

    # Normal operational mode: only authorized operational records.
    return and_(
        model.data_origin.in_(_OPERATIONAL_ORIGINS),
        func.lower(func.coalesce(model.email, "")).notlike("%@example.invalid"),
        *(
            func.lower(func.coalesce(getattr(model, column), "")).notlike(_DEMO_MARKER)
            for column in _MARKED_FIELDS
            if hasattr(model, column)
        ),
    )


def visible_beneficiaries(query):
    return query.filter(beneficiary_visible_expression())


def household_visible_expression():
    if demo_setup_enabled():
        return Household.data_origin.notin_(("public_sample", "imported_research"))

    hidden_member = exists(
        select(1)
        .select_from(HouseholdMember)
        .join(Beneficiary, HouseholdMember.beneficiary_id == Beneficiary.id)
        .where(HouseholdMember.household_id == Household.id)
        .where(~beneficiary_visible_expression())
    )
    visible_member = exists(
        select(1)
        .select_from(HouseholdMember)
        .join(Beneficiary, HouseholdMember.beneficiary_id == Beneficiary.id)
        .where(HouseholdMember.household_id == Household.id)
        .where(beneficiary_visible_expression())
    )
    return and_(
        Household.data_origin.in_(_OPERATIONAL_ORIGINS),
        func.lower(func.coalesce(Household.village, "")).notlike(_DEMO_MARKER),
        func.lower(func.coalesce(Household.qr_id, "")).notlike(_DEMO_MARKER),
        or_(~hidden_member, visible_member),
    )


def visible_households(query):
    return query.filter(household_visible_expression())


def visible_household_members(query):
    if demo_setup_enabled():
        return query
    return query.outerjoin(
        Beneficiary, HouseholdMember.beneficiary_id == Beneficiary.id
    ).filter(
        or_(
            HouseholdMember.beneficiary_id.is_(None),
            and_(
                beneficiary_visible_expression(),
                or_(
                    # synthetic demo members may be present and clearly labeled
                    getattr(HouseholdMember, "beneficiary_id").is_(None),
                    func.lower(func.coalesce(HouseholdMember.name, "")).notlike(_DEMO_MARKER),
                ),
            ),
        )
    )


def visible_followups(query, db):
    if demo_setup_enabled():
        return query
    from app.models import FollowUp

    beneficiary_ids = db.query(Beneficiary.id).filter(beneficiary_visible_expression())
    household_ids = db.query(Household.id).filter(household_visible_expression())
    return query.filter(
        or_(
            FollowUp.beneficiary_id.is_(None),
            FollowUp.beneficiary_id.in_(beneficiary_ids),
        ),
        or_(
            FollowUp.household_id.is_(None),
            FollowUp.household_id.in_(household_ids),
        ),
    )
