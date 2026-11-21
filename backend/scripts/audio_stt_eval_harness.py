"""Audio STT + extraction evaluation harness for ASHA Swar Nirantar.

Purpose
- Evaluate acoustic STT and structured extraction SEPARATELY on real, consenting
  speaker recordings (Kannada, Karnataka-accented English, Kanglish, Hinglish,
  Romanized Kannada, etc.).
- This script does NOT fabricate results. It only reports what was actually run.
- It does NOT write to the application database.

Input manifest (JSONL or JSON array): each item should include
{
  "audio_path": "relative/or/absolute.wav",
  "reference_transcript": "ground truth text spoken by consenting speaker",
  "language_hint": "kn-IN" | "en-IN" | "hi-IN" | "kn-IN,en-IN" | "indic-auto" | ...,
  "script": "kannada"|"latin"|"mixed"|"devanagari"|...,
  "accent": "karnataka_kannada"|"indian_english_karnataka"|...,
  "code_mix": "none"|"kanglish"|"hinglish"|"romanized_kannada"|...,
  "noise": "quiet"|"moderate"|"noisy",
  "speed": "natural"|"slow"|"fast",
  "mid_sentence_switch": false,
  "speaker_consent": true,
  "speaker_id": "anon_01",
  "expected_fields": {"beneficiary_name": "...", "weight_kg": 46, ...}  # optional
}

Usage (from backend/):
  python scripts/audio_stt_eval_harness.py --manifest path/to/manifest.json --out reports/audio_eval_report.json

Modes:
  --stt-mode api        POST audio to running backend /api/voice/transcribe-file if available (not implemented by default)
  --stt-mode gnani      Call Gnani service directly (requires live config; no secrets printed)
  --stt-mode browser-manual  Generate a template/report shell for manual browser STT transcripts
  --stt-mode skip       Skip STT, evaluate extraction only from provided hypothesis_transcript

By default this script computes WER/CER if reference and hypothesis transcripts exist.
WER/CER are reported as null when reference/hypothesis is missing or language/script makes
standard whitespace WER misleading; CER is still computed on normalized characters.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running from backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_manifest(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        items = []
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except Exception as e:
                raise ValueError(f"Invalid JSONL at line {i}: {e}") from e
        return items
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError("Manifest must be a JSON array, JSONL, or object with 'items' array")


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[\"'`“”‘’,.!?;:()\[\]{}<>/\\|@#$%^&*_+=~]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def levenshtein(a: list[str], b: list[str]) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


def wer_cer(reference: str, hypothesis: str) -> dict[str, Any]:
    ref_n = normalize_text(reference)
    hyp_n = normalize_text(hypothesis)
    ref_words = ref_n.split() if ref_n else []
    hyp_words = hyp_n.split() if hyp_n else []
    ref_chars = list(ref_n.replace(" ", ""))
    hyp_chars = list(hyp_n.replace(" ", ""))
    word_dist = levenshtein(ref_words, hyp_words)
    char_dist = levenshtein(ref_chars, hyp_chars)
    wer = (word_dist / len(ref_words)) if ref_words else None
    cer = (char_dist / len(ref_chars)) if ref_chars else None
    return {
        "reference_normalized": ref_n,
        "hypothesis_normalized": hyp_n,
        "wer": wer,
        "cer": cer,
        "word_edits": word_dist,
        "char_edits": char_dist,
        "reference_words": len(ref_words),
        "hypothesis_words": len(hyp_words),
    }


def _safe_get_audio_path(item: dict[str, Any], manifest_dir: Path) -> Path | None:
    raw = item.get("audio_path") or item.get("audio") or item.get("file")
    if not raw:
        return None
    p = Path(str(raw))
    if not p.is_absolute():
        p = (manifest_dir / p).resolve()
    return p


def evaluate_extraction(transcript: str, language_hint: str, expected_fields: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic/Gemini-configured extraction through app service, compare to expected fields."""
    from app.services.gnani import extract_fields

    predicted, mode = extract_fields(transcript or "", language_hint or "en")
    results = {}
    correct = 0
    total = 0
    for key, expected in (expected_fields or {}).items():
        total += 1
        pred = predicted.get(key)
        ok = _field_match(expected, pred)
        if ok:
            correct += 1
        results[key] = {"expected": expected, "predicted": pred, "match": ok}
    return {
        "extraction_mode": mode,
        "predicted_structured": predicted,
        "field_results": results,
        "fields_correct": correct,
        "fields_total": total,
        "field_accuracy": (correct / total) if total else None,
    }


def _field_match(expected: Any, predicted: Any) -> bool:
    if expected is None:
        return predicted is None or predicted == "" or predicted == []
    if isinstance(expected, bool):
        return bool(predicted) is expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(predicted) - float(expected)) < 1e-6
        except Exception:
            return False
    if isinstance(expected, list):
        if not isinstance(predicted, list):
            return False
        return sorted([normalize_text(str(x)) for x in expected]) == sorted([normalize_text(str(x)) for x in predicted])
    return normalize_text(str(expected)) == normalize_text(str(predicted))


def transcribe_with_gnani(audio_path: Path, language_hint: str) -> dict[str, Any]:
    """Attempt Gnani REST STT if configured. Returns honest status; no secrets."""
    from app import get_env, gnani_requested_mode
    from app.services.gnani import _prisma_language_locale, _stt_live_enabled

    if not audio_path.exists():
        return {"status": "error", "error": "audio_file_missing", "transcript": ""}
    if not _stt_live_enabled():
        return {
            "status": "skipped",
            "reason": "gnani_stt_not_live_configured",
            "mode": gnani_requested_mode(),
            "transcript": "",
        }

    api_key = get_env("GNANI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "missing_api_key", "transcript": ""}

    url = get_env("GNANI_PRISMA_REST_URL") or "https://api.vachana.ai/stt/v3"
    model = get_env("GNANI_PRISMA_MODEL") or "prisma-v3.0"
    lang = (language_hint or "en-IN").strip()
    # Allow explicit list/indic-auto as provided in manifest; do not invent.
    form_fields = {
        "model": model,
        "language_code": lang,
    }
    # Optional format hint for code-mixed evaluation; only send if explicitly configured.
    fmt = (get_env("GNANI_PRISMA_FORMAT") or "").strip()
    if fmt:
        form_fields["format"] = fmt

    import mimetypes
    import uuid
    import urllib.request

    mime = mimetypes.guess_type(str(audio_path))[0] or "audio/wav"
    boundary = f"----AshaEval{uuid.uuid4().hex}"
    body = bytearray()
    for k, v in form_fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="audio_file"; filename="{audio_path.name}"\r\n'.encode())
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
    body.extend(audio_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "X-API-Key-ID": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        transcript = data.get("text") or data.get("transcript") or ""
        return {
            "status": "ok",
            "provider": "gnani_prisma_rest",
            "model": model,
            "language_code_sent": lang,
            "format_sent": fmt or None,
            "detected_language_code": data.get("detected_language_code"),
            "transcript": transcript,
            "raw_response_keys": sorted(list(data.keys()))[:30],
        }
    except Exception as e:
        # Do not expose secrets; include only safe error class/message.
        msg = str(e)
        msg = re.sub(r"(?i)(api[_-]?key|token|secret|authorization)[^\s,;]{0,80}", "<redacted>", msg)
        return {"status": "error", "error": e.__class__.__name__, "detail": msg[:300], "transcript": ""}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="JSON/JSONL manifest of consenting audio samples")
    ap.add_argument("--out", default="", help="Output report JSON path")
    ap.add_argument("--stt-mode", choices=["skip", "gnani", "browser-manual"], default="skip")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    manifest_path = Path(args.manifest).resolve()
    items = load_manifest(manifest_path)
    if args.limit and args.limit > 0:
        items = items[: args.limit]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "stt_mode": args.stt_mode,
        "notes": [
            "This report contains only actual run results. No fabricated WER/CER/STT claims.",
            "Acoustic STT and structured extraction are evaluated separately.",
            "Do not mark Karnataka accent/Kanglish acoustic recognition complete until real audio tests pass.",
        ],
        "summary": {},
        "items": [],
    }

    stt_ok = stt_err = stt_skip = 0
    wer_vals = []
    cer_vals = []
    field_acc_vals = []

    for idx, item in enumerate(items):
        audio_path = _safe_get_audio_path(item, manifest_path.parent)
        ref = item.get("reference_transcript") or ""
        hyp = item.get("hypothesis_transcript") or ""
        lang = item.get("language_hint") or item.get("language") or "en-IN"
        consent = bool(item.get("speaker_consent"))
        row = {
            "index": idx,
            "audio_path": str(audio_path) if audio_path else None,
            "audio_exists": bool(audio_path and audio_path.exists()),
            "speaker_id": item.get("speaker_id"),
            "speaker_consent": consent,
            "language_hint": lang,
            "accent": item.get("accent"),
            "script": item.get("script"),
            "code_mix": item.get("code_mix"),
            "noise": item.get("noise"),
            "speed": item.get("speed"),
            "mid_sentence_switch": bool(item.get("mid_sentence_switch")),
            "reference_transcript": ref,
            "hypothesis_transcript": hyp,
            "stt": None,
            "stt_metrics": None,
            "extraction": None,
        }

        if not consent:
            row["stt"] = {"status": "skipped", "reason": "speaker_consent_not_confirmed"}
            stt_skip += 1
            report["items"].append(row)
            continue

        if args.stt_mode == "gnani":
            stt = transcribe_with_gnani(audio_path, lang) if audio_path else {"status": "error", "error": "missing_audio_path", "transcript": ""}
            row["stt"] = stt
            if stt.get("status") == "ok":
                hyp = stt.get("transcript", "")
                row["hypothesis_transcript"] = hyp
                stt_ok += 1
            elif stt.get("status") == "skipped":
                stt_skip += 1
            else:
                stt_err += 1
        elif args.stt_mode == "browser-manual":
            row["stt"] = {
                "status": "manual_required",
                "reason": "browser_stt_requires_real_browser/mic_or_playback; fill hypothesis_transcript after test",
            }
            stt_skip += 1
        else:
            row["stt"] = {"status": "skipped", "reason": "stt_mode_skip"}
            stt_skip += 1

        if ref and row.get("hypothesis_transcript"):
            metrics = wer_cer(ref, row["hypothesis_transcript"])
            row["stt_metrics"] = metrics
            if metrics["wer"] is not None:
                wer_vals.append(metrics["wer"])
            if metrics["cer"] is not None:
                cer_vals.append(metrics["cer"])

        expected = item.get("expected_fields") or {}
        if expected and row.get("hypothesis_transcript"):
            try:
                ex = evaluate_extraction(row["hypothesis_transcript"], lang, expected)
                row["extraction"] = ex
                if ex.get("field_accuracy") is not None:
                    field_acc_vals.append(ex["field_accuracy"])
            except Exception as e:
                row["extraction"] = {"status": "error", "error": e.__class__.__name__, "detail": str(e)[:200]}
        elif expected and ref:
            # Allow extraction-only baseline from reference transcript when no STT hypothesis.
            try:
                ex = evaluate_extraction(ref, lang, expected)
                ex["note"] = "extraction_run_on_reference_transcript_no_stt_hypothesis"
                row["extraction"] = ex
            except Exception as e:
                row["extraction"] = {"status": "error", "error": e.__class__.__name__, "detail": str(e)[:200]}

        report["items"].append(row)

    report["summary"] = {
        "total_items": len(items),
        "stt_ok": stt_ok,
        "stt_skipped": stt_skip,
        "stt_errors": stt_err,
        "avg_wer": (sum(wer_vals) / len(wer_vals)) if wer_vals else None,
        "avg_cer": (sum(cer_vals) / len(cer_vals)) if cer_vals else None,
        "avg_field_accuracy_on_hypothesis": (sum(field_acc_vals) / len(field_acc_vals)) if field_acc_vals else None,
    }

    out_path = Path(args.out).resolve() if args.out else (BACKEND_DIR / "reports" / "audio_stt_eval_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"out": str(out_path), "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
