# Security Report — ASHA Swar Nirantar

**Date:** 2026-11-15 (hardening pass, local codebase)  
**Scope:** backend FastAPI app, frontend integration points, configuration/docs.  
**Status:** targeted hardening applied; **not a full security audit or penetration test**. Remaining risks are listed below.

## 1. Hardening applied in this pass

### Authentication & session handling
- **Bearer token expiry enforced:** `app/auth.py` now rejects expired opaque tokens using `TOKEN_TTL_HOURS` (default **168h / 7 days**, configurable; `0` disables for controlled local demos only). Expired tokens are deleted on use.
- **Login rate limiting (per IP):** `app/routers/auth_router.py` adds an in-memory sliding-window limiter (`LOGIN_RATE_MAX_ATTEMPTS` / `LOGIN_RATE_WINDOW_SECONDS`, defaults `10` / `300s`) returning **HTTP 429** on excess attempts. Intended for single-process deployments; production should add a gateway/WAF limiter.

### CORS / browser surface
- **Explicit, configurable CORS:** `app/main.py` reads `CORS_ORIGINS` (comma-separated, defaults to local Vite origins), restricts methods/headers to those needed (`GET,POST,PUT,PATCH,DELETE,OPTIONS` and `Authorization,Content-Type,Accept,X-Requested-With`), keeps credentials enabled only for configured origins.

### Real-time endpoints
- **Dashboard SSE authenticated:** `GET /api/dashboard/events` (`app/routers/dashboard.py`) now requires a valid (non-expired) bearer token via `Authorization: Bearer` or `?token=` query parameter. Frontend `Overview.jsx` passes the stored token when opening the `EventSource` stream.

### File/PDF safety
- **Report download path confinement:** `app/routers/notifications.py` resolves the stored report path and serves it only if it is within the configured report directory (`REPORT_DIR` / default `backend/generated_reports`), returning 404 otherwise. Filenames are normalized with `os.path.basename`.

### Configuration & documentation
- **`.env.example` expanded:** documents CORS, token TTL, login rate limits, SMS/SMTP settings, and `REPORT_DIR` with a reminder not to commit secrets. **`README.md`** updated with install/config/run/deployment/security/testing guidance.

## 2. Controls already present (verified in code)

- **Password storage:** PBKDF2-HMAC-SHA256 with per-password salt and constant-time comparison (`app/auth.py`).
- **Opaque bearer tokens:** random `secrets.token_hex(32)` stored server-side (`ApiToken`), resolved per request.
- **Route protection:** core resource routers (beneficiaries, households, visits, alerts, reminders, notifications, voice sessions/extraction/TTS, voice verification, drift, dashboard data/modules) require authenticated workers via dependencies.
- **Notification consent:** SMS/email send endpoints require `consent_granted` and record consent; messages are honest about demo vs provider-submitted/failed states (never claim delivery beyond provider confirmation).
- **Voice verification upload checks:** in-memory processing (audio not stored), WAV/PCM validation and size limit in `app/services/voiceprint.py` / router; invalid uploads rejected with 400.
- **PDF generation:** built from real DB records; filenames sanitized in `app/services/pdf.py`.

## 3. Remaining risks / gaps (not fully remediated)

| Area | Risk | Notes / recommended follow-up |
|---|---|---|
| **Authorization / IDOR** | Resource access is authenticated but generally **not scoped to worker/assignment/tenant** (beneficiaries, households, visits, alerts, reminders, reports, sessions fetched/modified by ID). | Appropriate for a single-team demo register in some setups, but for production enforce ownership/assignment checks on every read/write and audit access. |
| **WebSocket voice auth** | `WS /api/ws/voice` (`app/routers/voice.py`) is not bearer-protected (accepts connection without token validation). | Accept and validate a short-lived token (query param/subprotocol) before bridging audio; apply origin checks and rate/size limits. |
| **SSE token in URL** | Frontend passes token as `?token=` (EventSource limitation). | Tokens in URLs may appear in logs/proxies; prefer cookie-based auth or a fetch-stream with headers + short-lived stream tokens; ensure TLS and log redaction. |
| **Rate limiting scope** | Login limiter is **in-memory, per-process** and per-IP only. | Add distributed/gateway rate limiting, optional account lockout/backoff, and monitoring/alerting. No CAPTCHA/MFA implemented. |
| **Token lifecycle** | No explicit logout/revocation endpoint, rotation, device binding, or idle timeout. | Add logout (token deletion), rotation on privilege changes, and admin revocation; consider shorter TTL for production. |
| **Input validation depth** | Some endpoints accept broad `dict`/free-form structured payloads and long transcripts without strict length/schema limits. | Enforce max sizes, stricter schemas/allowlists per field, and server-side normalization to reduce abuse and storage bloat. |
| **Secrets & transport** | `.env` may contain secrets locally; dev server runs without TLS. | Use a secret manager, rotate keys, enforce HTTPS/HSTS in production, and restrict DB/file permissions. |
| **SQLite / concurrency** | SQLite + default dev settings are not hardened for multi-user production load. | Move to a managed RDBMS, use least-privilege DB credentials, backups, and integrity/retention policies. |
| **PII/health data handling** | App handles beneficiary/contact/health observations and generates PDFs. | Define retention, encryption-at-rest, access logging, consent records lifecycle, and data minimization per policy/regulation; restrict report directory access. |
| **Dependencies & supply chain** | No dependency audit/SBOM/pinning review performed in this pass. | Run `pip audit`/`npm audit`, pin/lock versions as appropriate, and keep frameworks updated. |
| **XSS / frontend** | UI is React-based (escaped by default) but not exhaustively reviewed for unsafe HTML sinks or third-party content. | Audit for `dangerouslySetInnerHTML`, untrusted rendering, and tighten CSP/security headers at the proxy. |

## 4. Operational recommendations

- Deploy behind **HTTPS** with a reverse proxy; set strict `CORS_ORIGINS` to production domains only.
- Keep `GNANI_MODE=demo` and notification providers unset unless real, tested credentials and safeguards are in place.
- Store generated reports in a **trusted, access-controlled** directory; treat PDFs and notification logs as sensitive.
- Back up the database and test restore; monitor for 401/429 spikes and anomalous access patterns.

## 5. Honest assessment

This pass improves baseline hygiene (configurable CORS, token expiry, login throttling, SSE auth, report path confinement, env/docs). **It does not claim the system is fully secure.** Production use requires ownership-scoped authorization, hardened WebSocket auth, distributed rate limiting, transport security, secret management, and a formal security review/test against the deployed environment.
