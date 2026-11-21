"""Voice endpoints:

- POST /api/voice/extract  (REST extraction; mode-labelled)
- WS   /api/ws/voice       (streaming STT bridge; PCM 16 kHz frames in,
                            JSON stt_partial / stt_final / status out)
- POST /api/voice/tts      (Gnani Timbre TTS with browser-synthesis fallback)
"""
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from app.auth import create_ws_token, get_current_worker, verify_ws_token
from app.database import get_db
from app.schemas import ExtractMultiResponse, ExtractRequest, ExtractResponse, TtsRequest, TtsResponse
from app.services import gnani

router = APIRouter(prefix="/api", tags=["voice"])

# NOTE: the WebSocket is intentionally NOT behind the bearer-token
# dependency (WS clients cannot easily set Authorization headers here);
# the two REST endpoints below are protected individually.


@router.post("/voice/extract", response_model=ExtractResponse)
def extract(payload: ExtractRequest, _worker=Depends(get_current_worker)):
    """Extract structured fields + deterministic danger flags from a transcript.

    The danger flags come from rules.detect_danger_signs (approved phrase
    lists), never from the LLM. The response is labelled demo|live.
    """
    from app.rules import detect_danger_signs

    structured, mode = gnani.extract_fields(payload.transcript, payload.language)
    return {
        "structured": structured,
        "danger_flags": detect_danger_signs(payload.transcript, structured=structured),
        "mode": mode,
    }


@router.post("/voice/extract-multi", response_model=ExtractMultiResponse)
def extract_multi(payload: ExtractRequest, _worker=Depends(get_current_worker)):
    """Multi-entity structured extraction:
    - Multiple beneficiaries from different households
    - Multiple members of one household
    - Single beneficiary with rich module sections
    - Universal voice corrections
    """
    from app.rules import detect_danger_signs

    result, mode = gnani.extract_fields_multi(payload.transcript, payload.language)
    result["danger_flags"] = detect_danger_signs(payload.transcript, structured=result)
    result["mode"] = mode
    return result


@router.post("/voice/tts", response_model=TtsResponse)
def tts(payload: TtsRequest, _worker=Depends(get_current_worker)):
    """Text-to-speech via Gnani Timbre (live) or {"mode":"demo"} fallback."""
    return gnani.text_to_speech(payload.text, payload.language)


class TaraChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    language: str = "en"
    context: dict | None = None


@router.post("/voice/chat")
def tara_chat(payload: TaraChatRequest, _worker=Depends(get_current_worker)):
    """Conversational assistance for Tara (Gemini-powered). Returns honest errors on failure."""
    try:
        reply = gnani.generate_tara_response(
            payload.message,
            language=payload.language or "en",
            context=payload.context or {},
        )
        return {"reply": reply, "provider": "Google Gemini", "mode": "live"}
    except gnani.GeminiLLMError as exc:
        status = 503
        if exc.code in ("invalid_request",):
            status = 400
        elif exc.code in ("invalid_api_key", "missing_api_key", "missing_model", "unsupported_model"):
            status = 503
        elif exc.code in ("quota_exhausted", "rate_limited"):
            status = 429
        elif exc.code in ("timeout", "network_error", "provider_error", "empty_response", "malformed_response"):
            status = 502
        raise HTTPException(status_code=status, detail={"message": exc.message, "code": exc.code, "provider": "Google Gemini"})
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={"message": "Gemini request failed.", "code": "provider_error", "provider": "Google Gemini"},
        )


@router.post("/voice/ws-token")
def voice_ws_token(_worker=Depends(get_current_worker)):
    """Issue a short-lived token for the authenticated voice WebSocket."""
    return {"token": create_ws_token(_worker.id, ttl_seconds=300), "expires_in_seconds": 300}


@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket, language: str = "en", token: str = ""):
    """Streaming voice WebSocket.

    Protocol (per spec):
    - Client -> server: binary PCM 16 kHz frames; text JSON {"type":"reset"}
      to start a new utterance and {"type":"finalize"} to close the current
      utterance (the ASHA worker stopped speaking).
    - Server -> client: {"type":"stt_partial","text":...},
      {"type":"stt_final","text":...}, {"type":"status","stage":...},
      {"type":"error","code":...}.
    Speech is either supplied by the configured Gnani provider or by the
    browser's speech-recognition API. The server never fabricates transcripts.
    """
    worker_id = verify_ws_token(token)
    if not worker_id:
        await ws.accept()
        await _ws_send(ws, {"type": "error", "code": "ws_auth", "message": "Voice session authentication required."})
        await ws.close(code=4401)
        return
    # Best-effort worker active check; do not log token.
    try:
        from app.database import SessionLocal
        from app.models import AshaWorker
        db = SessionLocal()
        try:
            worker = db.query(AshaWorker).filter(AshaWorker.id == worker_id, AshaWorker.is_active == True).first()  # noqa: E712
            if worker is None:
                await ws.accept()
                await _ws_send(ws, {"type": "error", "code": "ws_auth", "message": "Voice session authentication required."})
                await ws.close(code=4401)
                return
        finally:
            db.close()
    except Exception:
        await ws.accept()
        await _ws_send(ws, {"type": "error", "code": "ws_auth", "message": "Voice session authentication failed."})
        await ws.close(code=4401)
        return

    await ws.accept()
    if not gnani.prisma_language_enabled(language):
        reason = "integration_not_configured" if not gnani._live_enabled() else "language_not_verified"
        await _ws_send(
            ws,
            {
                "type": "status",
                "stage": "browser_fallback",
                "mode": "demo",
                "provider": "browser",
                "reason": reason,
            },
        )
        await ws.close()
        return

    # ---- LIVE path: bridge to Gnani Prisma v3.0 WebSocket ----
    import websockets

    url = gnani.prisma_connection_url(language)
    headers = gnani.prisma_connection_headers(language)
    upstream = None
    try:
        upstream = await websockets.connect(url, extra_headers=headers)  # type: ignore[call-arg]
        await _ws_send(
            ws,
            {"type": "status", "stage": "listening", "mode": "live", "provider": "Gnani Prisma"},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
        reason = "provider_auth" if status_code in (401, 403) else "provider_unavailable"
        await _ws_send(
            ws,
            {
                "type": "status",
                "stage": "browser_fallback",
                "mode": "demo",
                "provider": "browser",
                "reason": reason,
                "detail": {"status_code": status_code, "error": str(exc)},
            },
        )
        await ws.close()
        return

    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            text = message.get("text")
            if text:
                try:
                    msg = json.loads(text)
                except (ValueError, TypeError):
                    continue
                kind = msg.get("type")
                if kind == "reset":
                    await upstream.send(json.dumps({"type": "reset"}))
                    await _ws_send(
                        ws,
                        {"type": "status", "stage": "listening", "mode": "live", "provider": "Gnani Prisma"},
                    )
                elif kind == "finalize":
                    # The worker stopped speaking: ask Gnani Prisma to flush
                    # and wait for its final transcript before we close.
                    await _ws_send(
                        ws,
                        {"type": "status", "stage": "finalizing", "mode": "live", "provider": "Gnani Prisma"},
                    )
                    got_final = await _finalize_upstream(ws, upstream, "live")
                    if not got_final:
                        await _ws_send(ws, {
                            "type": "error",
                            "code": "no_final",
                            "mode": "live",
                            "message": "The speech provider did not return a final transcript.",
                        })
                continue
            if data:
                await upstream.send(data)
                # Relay whatever upstream produced (non-blocking best effort).
                try:
                    while True:
                        upstream_msg = await gnani.asyncio_wait_for(upstream.recv(), timeout=0.01)
                        await _ws_send(ws, gnani._parse_upstream(upstream_msg))
                except TimeoutError:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await upstream.close()
        except Exception:
            pass


async def _finalize_upstream(ws: WebSocket, upstream, mode: str, timeout: float = 5.0) -> bool:
    """Ask Gnani Prisma to flush the utterance and relay its final transcript.

    Returns True when a final transcript was received. The upstream socket is
    NOT closed here — the caller owns its lifetime.
    """
    import asyncio

    try:
        await upstream.send(json.dumps({"type": "finalize"}))
    except Exception:
        # Some providers finalise implicitly on a trailing silence; still try
        # to read whatever is already buffered.
        pass

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            upstream_msg = await gnani.asyncio_wait_for(upstream.recv(), timeout=0.3)
        except TimeoutError:
            continue
        except Exception:
            break
        event = gnani._parse_upstream(upstream_msg)
        await _ws_send(ws, event)
        if event.get("type") == "stt_final":
            return True
    return False


async def _ws_send(ws: WebSocket, payload: dict) -> None:
    if ws.client_state == WebSocketState.CONNECTED:
        await ws.send_json(payload)


@router.get("/voice/beneficiary-history/{beneficiary_id}")
def beneficiary_history(beneficiary_id: int, question: str = "", db: Session = Depends(get_db), _worker=Depends(get_current_worker)):
    """DB-grounded beneficiary history retrieval. Never fabricates missing data."""
    from app.services.history_retrieval import answer_history_question, beneficiary_history_summary
    if question.strip():
        return answer_history_question(db, beneficiary_id, question)
    return beneficiary_history_summary(db, beneficiary_id)
