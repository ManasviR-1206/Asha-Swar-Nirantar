"""Independent beneficiary identity resolution.

The rule this module enforces: **an extracted observation is never attached
to a beneficiary unless the identity is established.**

Resolution outcomes
-------------------
``resolved``    exactly one confident match -> the visit can be saved
``ambiguous``   several plausible candidates -> the ASHA worker must choose
``unresolved``  no usable name -> ask the worker, keep the visit pending
``new``        no candidate but a usable name -> offer to register a new one

The previously selected beneficiary is deliberately NOT part of the input:
re-using the context beneficiary is exactly the bug that kept writing every
visit to "Lakshmi".
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.data_scope import visible_beneficiaries
from app.models import Beneficiary, Household, HouseholdMember

# Titles and honorifics that ASHA workers commonly speak but never store.
_TITLE_WORDS = {
    "sri", "smt", "shree", "mrs", "mr", "ms", "miss", "dr", "dr.", "kumar", "kumari",
}

_GENDER_WORDS = {
    "male": "male", "m": "male", "boy": "male", "man": "male", "men": "male", "son": "male",
    "he": "male", "his": "male", "him": "male",
    "female": "female", "f": "female", "girl": "female", "woman": "female", "women": "female",
    "daughter": "female", "she": "female", "her": "female", "hers": "female",
}


def strip_accents(value: str) -> str:
    """Fold accented Latin characters to their ASCII base (Kannada names in
    Latin script, names with diacritics, etc.)."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalise_name(name: Optional[str]) -> str:
    """Lowercase, de-accent, drop honorifics, collapse whitespace."""
    if not name:
        return ""
    text = strip_accents(str(name)).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = [tok for tok in text.split() if tok and tok not in _TITLE_WORDS]
    return " ".join(tokens)


def name_tokens(name: Optional[str]) -> list[str]:
    return [t for t in normalise_name(name).split() if t]


def normalise_gender(value: Optional[str]) -> str:
    if not value:
        return ""
    key = str(value).strip().lower()
    return _GENDER_WORDS.get(key, key)


def _score_candidate(
    spoken: str,
    spoken_tokens: list[str],
    spoken_age: Optional[int],
    spoken_gender: str,
    stored_name: str,
    stored_age: Optional[int],
    stored_gender: str,
    same_household: bool,
) -> int:
    """Heuristic score for one candidate. Higher is better.

    Not a calibrated probability — a deterministic ranking score used only to
    order candidates and to decide whether the identity is unambiguous.
    """
    stored_norm = normalise_name(stored_name)
    stored_tokens = stored_tokens_of(stored_name)
    if not stored_norm or not spoken:
        return 0

    score = 0
    if stored_norm == spoken:
        score = 100
    elif spoken_tokens and stored_tokens and spoken_tokens[0] == stored_tokens[0]:
        # Same first name ("Ravi" -> "Ravi Kumar")
        score = 85
    elif stored_norm.startswith(spoken + " "):
        score = 80
    elif spoken.startswith(stored_norm + " "):
        score = 78
    elif spoken_tokens and spoken_tokens[0] in stored_tokens:
        score = 62
    elif set(spoken_tokens) & set(stored_tokens):
        score = 55
    else:
        score = 0

    if score == 0:
        return 0

    if same_household:
        score += 15
    if spoken_age is not None and stored_age is not None:
        if abs(spoken_age - stored_age) <= 2:
            score += 10
        else:
            score -= 30
    if spoken_gender and stored_gender:
        if spoken_gender == stored_gender:
            score += 6
        else:
            score -= 22
    return score


def stored_tokens_of(name: Optional[str]) -> list[str]:
    return [t for t in normalise_name(name).split() if t]


def _beneficiary_dict(b: Beneficiary, score: int) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "age": b.age,
        "category": b.category,
        "village": b.village,
        "qr_id": b.qr_id,
        "score": score,
    }


def resolve_beneficiary(
    db: Session,
    *,
    name: Optional[str] = None,
    household_id: Optional[int] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    category: Optional[str] = None,
    allow_new: bool = True,
) -> dict[str, Any]:
    """Resolve one spoken identity against the register.

    Returns a dict with ``status``, ``beneficiary_id``, ``beneficiary``,
    ``candidates`` and a human-readable ``reason``.
    """
    spoken = normalise_name(name)
    spoken_tokens = name_tokens(name)
    spoken_gender = normalise_gender(gender)
    spoken_age = age if isinstance(age, int) else None

    if not spoken:
        # Nothing identifies this visit — never guess.
        return {
            "status": "unresolved",
            "beneficiary_id": None,
            "beneficiary": None,
            "candidates": [],
            "contradiction": None,
            "reason": "No beneficiary name was mentioned for this visit.",
        }

    # Household members are strong identity evidence.
    household_ids: set[int] = set()
    if household_id is not None:
        household_ids.add(int(household_id))

    rows = visible_beneficiaries(db.query(Beneficiary)).all()
    scored: list[tuple[int, Beneficiary]] = []
    for b in rows:
        same_household = False
        if household_ids:
            member = (
                db.query(HouseholdMember)
                .filter(HouseholdMember.beneficiary_id == b.id)
                .first()
            )
            if member is not None and member.household_id in household_ids:
                same_household = True
        score = _score_candidate(
            spoken,
            spoken_tokens,
            spoken_age,
            spoken_gender,
            b.name,
            b.age,
            b.gender,
            same_household,
        )
        if score > 0:
            scored.append((score, b))

    if not scored:
        if allow_new:
            return {
                "status": "new",
                "beneficiary_id": None,
                "beneficiary": None,
                "candidates": [],
                "contradiction": None,
                "reason": f"No registered beneficiary matches '{name}'.",
            }
        return {
            "status": "unresolved",
            "beneficiary_id": None,
            "beneficiary": None,
            "candidates": [],
            "contradiction": None,
            "reason": f"No registered beneficiary matches '{name}'.",
        }

    # Sort: score desc, then the closest name length, then oldest id for stability.
    scored.sort(key=lambda pair: (-pair[0], len(pair[1].name or ""), pair[1].id))
    candidates = [_beneficiary_dict(b, s) for s, b in scored[:8]]
    best_score, best = scored[0]

    # A contradiction between the spoken details and the stored record is
    # surfaced so the worker double-checks before saving.
    contradiction = _contradiction(spoken_age, spoken_gender, best)

    if contradiction:
        # Spoken details conflict with the best stored record. Never silently attach.
        return {
            "status": "ambiguous",
            "beneficiary_id": None,
            "beneficiary": None,
            "candidates": candidates,
            "contradiction": contradiction,
            "reason": (
                f"'{name}' may match {best.name}, but {contradiction}. "
                "The worker must confirm the identity before saving."
            ),
        }

    if len(scored) == 1:
        return {
            "status": "resolved",
            "beneficiary_id": best.id,
            "beneficiary": _beneficiary_dict(best, best_score),
            "candidates": candidates,
            "contradiction": None,
            "reason": f"Matched '{name}' to {best.name}.",
        }

    runner_up = scored[1][0]
    # A clear margin means the identity is established; a near tie is ambiguous.
    if best_score >= 80 and best_score - runner_up >= 15:
        return {
            "status": "resolved",
            "beneficiary_id": best.id,
            "beneficiary": _beneficiary_dict(best, best_score),
            "candidates": candidates,
            "contradiction": None,
            "reason": f"Matched '{name}' to {best.name}.",
        }

    return {
        "status": "ambiguous",
        "beneficiary_id": None,
        "beneficiary": None,
        "candidates": candidates,
        "contradiction": None,
        "reason": (
            f"'{name}' matches {len(candidates)} registered beneficiaries - "
            "the worker needs to choose."
        ),
    }


def _contradiction(
    spoken_age: Optional[int],
    spoken_gender: str,
    stored: Beneficiary,
) -> Optional[str]:
    """Describe a mismatch between the spoken details and the stored record."""
    notes: list[str] = []
    if spoken_age is not None and stored.age is not None and abs(spoken_age - stored.age) > 2:
        notes.append(f"the spoken age is {spoken_age} but the register says {stored.age}")
    if spoken_gender and stored.gender and spoken_gender != stored.gender:
        notes.append(
            f"the spoken gender is {spoken_gender} but the register says {stored.gender}"
        )
    return "; ".join(notes) if notes else None


def resolve_for_household_member(
    db: Session,
    *,
    name: Optional[str],
    household_id: Optional[int],
    age: Optional[int] = None,
    gender: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve a household member.

    Members of the same household are preferred, but a member is never
    assumed to belong to that household without evidence.
    """
    return resolve_beneficiary(
        db,
        name=name,
        household_id=household_id,
        age=age,
        gender=gender,
    )


def household_member_names(db: Session, household_id: int) -> list[dict[str, Any]]:
    """Names of the members of a household (used to detect 'my wife' etc.)."""
    members = (
        db.query(HouseholdMember).filter(HouseholdMember.household_id == household_id).all()
    )
    return [{"id": m.id, "name": m.name, "relation": m.relation} for m in members]


def find_household_by_label(db: Session, label: Optional[str]) -> Optional[Household]:
    """Resolve a spoken household reference ("Rampur household", "household 24")."""
    if not label:
        return None
    text = str(label).strip().lower()
    households = db.query(Household).all()
    for h in households:
        if (h.qr_id or "").lower() == text:
            return h
    for h in households:
        if (h.village or "").lower() == text:
            return h
    for h in households:
        if text and text in (h.village or "").lower():
            return h
    return None
