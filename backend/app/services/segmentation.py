"""Beneficiary boundary detection for continuous voice recordings.

A single ASHA recording can describe several unrelated beneficiaries. This
module splits an ordered transcript into one segment per beneficiary.

Two independent signals are used, so detection does not depend on any single
keyword:

1. **Transition phrases** — "then I visited…", "next I went to…", and their
   Kannada / Hindi / Telugu / Tamil equivalents.
2. **Identity anchors** — every "visited <Name>" mention. When a later
   anchor names somebody *different*, that is a boundary even without a
   transition phrase ("I visited Ravi and then I met Priya").

The result keeps the original transcript order and never invents a name:
segments without an identifiable person are returned with ``spoke_name``
empty so the caller can ask the worker instead of guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ----------------------------------------------------------------------
# Transition phrases (explicit "now someone else" markers)
# ----------------------------------------------------------------------
_TRANSITIONS: dict[str, list[str]] = {
    "en": [
        r"next\s+i\s+(?:visited|went\s+to|met|checked)",
        r"then\s+i\s+(?:visited|went\s+to|met|checked)",
        r"after\s+that\s+i\s+(?:visited|went\s+to|met)",
        r"after\s+that,?",
        r"i\s+also\s+(?:visited|met|checked)",
        r"also\s+(?:visited|met)",
        r"another\s+(?:patient|beneficiary|woman|man|child|baby|girl|boy)\s+(?:was|is)?",
        r"the\s+next\s+(?:household|family|patient|beneficiary)\s+(?:was|is)?",
        r"now\s+(?:i\s+)?record\s+another",
        r"after\s+visiting",
        r"moving\s+on\s+to",
        r"next\s+(?:household|family|patient)\b",
        r"let\s+me\s+(?:also\s+)?(?:visit|record)",
    ],
    "kn": [
        r"ನಂತರ\s+ನಾನು",
        r"ಅನಂತರ\s+ನಾನು",
        r"ಮುಂದೆ\s+ನಾನು",
        r"ನಂತರೆ\s+ನಾನು",
        r"ಮತ್ತೊಂದು\s+ಭೇಟಿ",
        r"ಇನ್ನೊಂದು\s+ಭೇಟಿ",
        r"ಇದರ\s+ನಂತರ",
        r"ಆಮೇಲೆ\s+ಭೇಟಿ",
        r"ಕೊಂಡು\s+ಮೇಲೆ",
        r"ಇನ್ನೊಂದು\s+(?:ಮನೆ|ಕುಟುಂಬ|ಲಸಕ)",
        r"ಬಳಿಕ\s+ನಾನು",
    ],
    "hi": [
        r"फिर\s+(?:मैंने|मैं)",
        r"इसके\s+बाद",
        r"उसके\s+बाद",
        r"इसके\s+बाद\s+मैंने",
        r"अगली\s+(?:महिला|मर्द|बच्चा|परिवार|रोगी)",
        r"एक\s+और",
        r"दूसरी\s+(?:महिला|मर्द|बच्चा)",
        r"अब\s+मैंने",
        r"इसके\s+बाद\s+मैंने",
        r"अगला\s+(?:परिवार|मरीज|महिला)",
    ],
    "te": [
        r"తర్వాత\s+(?:నేను|ఆమె)",
        r"తర్వాత\s+నుండి",
        r"పిఱ్పి\s+నేను",
        r"అప్పుడు\s+నేను",
        r"మరో\s+",
        r"ఇంకొక\s+",
        r"తర్వాత\s+ఆమె",
        r"వెంటనే",
    ],
    "ta": [
        r"பிறகு\s+(?:நான்|அவள்|அவன்)",
        r"அடுத்து\s+(?:நான்|ஆமாற்றம்)",
        r"இன்னும்\s+ஒரு",
        r"மற்றொரு",
        r"பிறகு\s+அவள்",
        r"அப்புறம்",
    ],
}

# ----------------------------------------------------------------------
# Identity anchors ("visited <Name>") — per script
#
# Latin patterns are matched CASE-SENSITIVELY so that "visited Lakshmi
# today" yields "Lakshmi" and not "Lakshmi today". Indic scripts have no
# case, so they are matched case-insensitively.
# ----------------------------------------------------------------------
_NAME_PATTERNS_LATIN: dict[str, list[str]] = {
    # English is verb-first ("visited Ravi"). The VERB is matched
    # case-insensitively but the NAME stays case-sensitive so that a trailing
    # lowercase word ("Lakshmi today") is not swallowed into the name.
    "en": [
        r"(?i:visited|visiting|met|examined|checked|saw)\s+(?:the\s+)?([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+)?)",
    ],
}

# Indic languages are name-first ("लक्ष्मी से भेट की", "లక్ష్మిని
# సందర్శించాను"), so the anchor captures the word BEFORE the verb.
_NAME_PATTERNS_INDIC: dict[str, list[str]] = {
    "kn": [
        r"([^\s.,!?]+)\s+ಭೇಟಿ\s+ಮಾಡ(?:ಿದೆ|ದೆ|ಲು|ದಿ|ಿದೆ)",
        r"([^\s.,!?]+)\s*ಭೇಟಿ\s+ಮಾಡ",
    ],
    "hi": [
        r"([^\s.,!?]+)\s+से\s+(?:भेट|मिली)",
        r"(?:भेट\s+कर|से\s+मिली)\s*([^\s.,!?]+)",
    ],
    "te": [
        r"([^\s.,!?]+)\s+(?:సందర్శించాను|కలిశాను|పరిశీలించాను)",
    ],
    "ta": [
        r"([^\s.,!?]+)\s+(?:சந்தித்தேன்|பார்த்தேன்|சரிபார்த்தேன்)",
    ],
}

# Words that follow a visit verb but are not a person's name.
_STOP_NAMES = {
    "the", "a", "an", "her", "him", "them", "house", "household", "family", "patient",
    "beneficiary", "mother", "baby", "child", "woman", "man", "girl", "boy", "new",
    "another", "next", "this", "that", "one", "each", "every", "all", "his", "her",
}


@dataclass
class Segment:
    """One beneficiary's portion of a continuous recording."""

    text: str
    spoke_name: Optional[str] = None
    household_label: Optional[str] = None
    boundary_reason: str = "start"
    index: int = 0
    anchor_names: list[str] = field(default_factory=list)


def _compile_transitions(lang: str) -> list[re.Pattern]:
    """Transition phrases — always case-insensitive, English always included
    because ASHA workers mix languages freely."""
    langs = ["en"] if lang not in _TRANSITIONS else ["en", lang]
    out: list[re.Pattern] = []
    for key in langs:
        for pattern in _TRANSITIONS.get(key, []):
            try:
                out.append(re.compile(pattern, re.I | re.UNICODE))
            except re.error:
                continue
    return out


def _compile_anchors(lang: str) -> list[re.Pattern]:
    """Identity anchors. Latin names are matched case-sensitively so a trailing
    lowercase word ("Lakshmi today") is not swallowed into the name."""
    out: list[re.Pattern] = []
    for pattern in _NAME_PATTERNS_LATIN.get("en", []):
        try:
            out.append(re.compile(pattern, re.UNICODE))
        except re.error:
            continue
    for key in ("en", lang):
        for pattern in _NAME_PATTERNS_INDIC.get(key, []):
            try:
                out.append(re.compile(pattern, re.I | re.UNICODE))
            except re.error:
                continue
    return out


# Words that can follow a name but are not part of it.
_NAME_TAIL_WORDS = {
    "today", "yesterday", "tomorrow", "morning", "evening", "again", "too", "also",
}


# Case / gender suffixes that attach to an Indic name ("ಲಕ್ಷ್ಮಿಯನ್ನು" ->
# "ಲಕ್ಷ್ಮಿ", "లక్ష్మిని" -> "లక్ష్మి", "லக்ஷ்மியைச்" -> "லக்ஷ்மி").
_INDIC_CASE_SUFFIXES = [
    "ಯನ್ನು", "ಯನ್ನ", "ಯನಿ", "ಯ", "ಅವರ", "ಅವಳ", "ಅವನ",
    "ని", "ను", "ద", "ము", "వ", "ల",
    "யைச்", "யை", "ஐ", "ஆ", "ஓ", "உடன்",
]


def _strip_indic_case_suffix(name: str) -> str:
    """Remove the Kannada/Telugu/Tamil case suffix from a spoken name."""
    changed = True
    while changed:
        changed = False
        for suffix in _INDIC_CASE_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix) + 1:
                name = name[: -len(suffix)]
                changed = True
                break
    return name


def _clean_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    name = raw.strip(" \t\n.,!?'\"")
    if not name:
        return None
    if name.lower() in _STOP_NAMES:
        return None
    # "Ravi's" -> "Ravi"
    name = re.sub(r"['’]s\b", "", name).strip()
    if not name or name.lower() in _STOP_NAMES:
        return None
    # "Lakshmi today" -> "Lakshmi"
    parts = name.split()
    while len(parts) > 1 and parts[-1].lower() in _NAME_TAIL_WORDS:
        parts.pop()
    name = " ".join(parts).strip()
    # Indic case suffixes
    # Telugu U+0C00-U+0C7F, Kannada U+0C80-U+0CFF, Tamil U+0B80-U+0BFF
    if any("\u0C00" <= ch <= "\u0CFF" or "\u0B80" <= ch <= "\u0BFF" for ch in name):
        name = _strip_indic_case_suffix(name)
    if not name or name.lower() in _STOP_NAMES:
        return None
    if len(name) > 60:
        return None
    return name


def _is_new_person(previous: Optional[str], current: Optional[str]) -> bool:
    """True when two anchors clearly refer to different people."""
    if not current:
        return False
    if not previous:
        return True
    prev = re.sub(r"[^\w]", "", previous.lower())
    curr = re.sub(r"[^\w]", "", current.lower())
    if not prev or not curr:
        return True
    if prev == curr:
        return False
    # A shared first token with different surnames is still a different person.
    prev_first = prev.split()[0] if prev.split() else ""
    curr_first = curr.split()[0] if curr.split() else ""
    if prev_first and curr_first and prev_first == curr_first and len(prev.split()) > 1 and len(curr.split()) > 1:
        return True
    return prev_first != curr_first


def segment_transcript(text: str, language: str = "en") -> list[Segment]:
    """Split an ordered transcript into one segment per beneficiary."""
    raw = (text or "").strip()
    if not raw:
        return []

    transitions = _compile_transitions(language)
    anchors = _compile_anchors(language)

    # ---- collect anchors (name mentions) ----
    anchor_hits: list[tuple[int, Optional[str]]] = []
    for pat in anchors:
        for m in pat.finditer(raw):
            anchor_hits.append((m.start(), _clean_name(m.group(1))))
    anchor_hits.sort(key=lambda h: h[0])

    # ---- collect transition phrases ----
    transition_hits: list[tuple[int, str]] = []
    for pat in transitions:
        for m in pat.finditer(raw):
            transition_hits.append((m.start(), m.group(0).strip()))
    transition_hits.sort(key=lambda h: h[0])

    # ---- decide split points ----
    # A transition phrase always splits. An identity anchor splits when it
    # names somebody different from the previous anchor. The very first
    # anchor starts the first visit and never splits.
    splits: list[tuple[int, str, Optional[str]]] = []
    seen_positions: set[int] = set()

    for pos, phrase in transition_hits:
        if pos == 0:
            continue
        key = pos // 12
        if key in seen_positions:
            continue
        seen_positions.add(key)
        splits.append((pos, "transition_phrase", None))

    last_name: Optional[str] = None
    seen_anchor = False
    for pos, name in anchor_hits:
        if name and seen_anchor and _is_new_person(last_name, name):
            # A transition phrase and an identity anchor often describe the
            # same hand-over ("after that I met Ravi"); treat them as one.
            if pos > 0 and not any(abs(pos - s[0]) < 24 for s in splits):
                splits.append((pos, "identity_anchor", name))
        if name:
            last_name = name
            seen_anchor = True

    splits.sort(key=lambda s: s[0])

    # ---- build segments ----
    segments: list[Segment] = []
    boundaries = [0] + [s[0] for s in splits] + [len(raw)]
    reasons = ["start"] + [s[1] for s in splits] + ["end"]
    names = [None] + [s[2] for s in splits] + [None]

    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        chunk = raw[start:end].strip()
        if not chunk:
            continue
        spoke = names[i]
        if not spoke:
            # The first anchor inside this chunk names the person.
            for pat in anchors:
                m = pat.search(chunk)
                if m:
                    spoke = _clean_name(m.group(1))
                    if spoke:
                        break
        segments.append(
            Segment(
                text=chunk,
                spoke_name=spoke,
                boundary_reason=reasons[i] if i < len(reasons) else "start",
                index=len(segments),
                anchor_names=[n for _, n in anchor_hits if start <= _ <= end],
            )
        )

    if not segments:
        segments.append(Segment(text=raw, spoke_name=None, index=0))

    return segments


def household_label_in(text: str) -> Optional[str]:
    """Extract a spoken household reference ("Rampur's household", "household 24")."""
    m = re.search(
        r"(?:visited\s+)?([A-Za-z\u0C00-\u0C7F\u0B80-\u0BFF][\w\u0C00-\u0C7F\u0B80-\u0BFF'’-]*)'s\s+household",
        text or "",
        re.I | re.UNICODE,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"household\s+(?:of\s+)?([A-Za-z\u0C00-\u0C7F\u0B80-\u0BFF][\w\u0C00-\u0C7F\u0B80-\u0BFF'’-]*)",
        text or "",
        re.I | re.UNICODE,
    )
    if m:
        return m.group(1)
    return None
