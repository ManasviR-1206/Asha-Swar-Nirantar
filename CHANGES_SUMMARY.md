# Changes Summary â€” Hardening & Completion Pass

**Date:** 2026-11-15  
**Scope:** Phase 10 (theme consistency sweep), Phase 11/12 (security hardening + risk documentation), Phase 15 (verification actually run), Phase 16 (docs/deliverables). Existing architecture and features were preserved; no rebuild-from-scratch.

## Modified files

### Backend â€” security, config, realtime
- `backend/app/main.py`
  - CORS made explicit and configurable via `CORS_ORIGINS` (comma-separated) with safe local defaults.
  - Restricted allowed methods/headers to those required by the app.
- `backend/app/auth.py`
  - Added configurable bearer token lifetime (`TOKEN_TTL_HOURS`, default 168h) and expiry enforcement in `get_current_worker`.
  - Expired tokens are removed when encountered; expired sessions return 401 ("Session expired. Please sign in again.").
- `backend/app/routers/auth_router.py`
  - Added in-memory, per-IP login rate limiting (`LOGIN_RATE_MAX_ATTEMPTS` / `LOGIN_RATE_WINDOW_SECONDS`, defaults 10 / 300s) returning HTTP 429 on excess attempts.
- `backend/app/routers/dashboard.py`
  - `GET /api/dashboard/events` (SSE) now requires authentication (Bearer header or `?token=` query param) with token-expiry validation, preventing unauthenticated subscription to live dashboard events.
- `backend/app/routers/notifications.py`
  - PDF report download now resolves the stored path and serves it only when confined to the configured report directory; returns 404 for missing/out-of-scope paths and uses a normalized filename.

### Backend â€” configuration/docs
- `backend/.env.example`
  - Expanded and documented: `CORS_ORIGINS`, `TOKEN_TTL_HOURS`, `LOGIN_RATE_WINDOW_SECONDS`, `LOGIN_RATE_MAX_ATTEMPTS`, SMTP/email settings, and `REPORT_DIR`; clarified demo-vs-live and secret-handling notes.

### Frontend â€” theme consistency (Phase 10 sweep)
- `frontend/src/pages/Login.jsx`
  - Restyled to the premium blush-pink healthcare theme: light warm-ivory form pane with `card-ivory` surfaces, accessible dark-slate/rose text and inputs, palette-aligned accents/buttons.
  - Kept the Tara 3D experience in an intentional dark/rose hero pane (and subtle mobile backdrop) so 3D remains legible while the form/UI is on-theme.
- `frontend/src/pages/dashboard/Overview.jsx`
  - Replaced hardcoded off-palette feature-card gradients and glow with palette-aligned gradients and `shadow-blush`.
  - Dashboard live-sync SSE connection now includes the stored bearer token (`?token=`) to work with authenticated SSE.
- `frontend/src/pages/dashboard/Reminders.jsx`
  - Replaced legacy green consent checkbox accent (`#39D6B0`) with dusty-rose palette accent (`#B96F85`).

### Documentation / deliverables (new or rewritten)
- `README.md` â€” rewritten with product overview, capabilities, tech stack, prerequisites, install/config/run, testing commands, security/deployment notes, and references to reports.
- `SECURITY_REPORT.md` â€” new: hardening applied, existing controls, remaining risks/gaps, operational recommendations, honest assessment.
- `TESTING_REPORT.md` â€” new: checks executed in this pass, previously verified checkpoint items, available-but-not-run suites, limitations, summary.
- `CHANGES_SUMMARY.md` â€” this file.

## Important behavior changes / notes

- **Sessions expire** by default after 7 days (configurable). Clients with stale tokens receive 401 and must sign in again.
- **Login throttling** may return 429 after repeated failures from the same IP (tunable via env). In-memory limiter is per-process.
- **Live dashboard updates** require an authenticated SSE connection; the frontend now supplies the token automatically.
- **Report downloads** are confined to the report directory to mitigate path traversal via stored paths.
- **Demo honesty preserved:** notification flows remain demo-labeled when providers are unconfigured; synthetic-voice screening remains a separate, explicitly-invoked, non-calibrated indicator.

## Verification performed (this pass)

- `python -m py_compile` on modified backend modules: **pass**.
- `npm run build` (frontend): **pass** (existing chunk-size/dynamic-import warnings only).
- `python scripts/test_voiceprint.py` (backend at `:8000`): **11/11 pass**.

See `TESTING_REPORT.md` and `SECURITY_REPORT.md` for full, honest detail and remaining gaps.

