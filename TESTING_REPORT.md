# Testing Report â€” ASHA Swar Nirantar

**Date:** 2026-11-15 (local workspace)  
**Environment:** Windows, Python 3.11, Node/npm (frontend), FastAPI backend + Vite frontend available locally.  
**Honesty note:** this report lists **only checks actually executed or directly evidenced in this pass** (plus previously verified items recorded in the project checkpoint). It does **not** claim full end-to-end, live-provider, device, or production-load validation.

## 1. Executed in this pass

| Area | Command / check | Result |
|---|---|---|
| Backend syntax | `python -m py_compile app\main.py app\auth.py app\routers\auth_router.py app\routers\dashboard.py app\routers\notifications.py` (from `backend/`) | **PASS** (no errors) |
| Frontend build | `npm run build` (from `frontend/`) | **PASS** â€” Vite production build succeeded. Non-blocking warnings: dynamic/static mixed import of `src/lib/voice.js`, and large main chunk (>500 kB) suggesting future code-splitting. |
| Synthetic-voice screening (API) | `python scripts\test_voiceprint.py` (backend running at `http://localhost:8000`) | **PASS â€” 11/11**. Covered: human-like `likely_human`, synthetic-like `potentially_synthetic`, short/silent `uncertain`, non-WAV and oversized rejected (400), history/stats correctness, indicators+quality notes present, unauthenticated upload refused (401), delete works. |

## 2. Previously verified (recorded in project checkpoint, not re-run end-to-end in this pass)

| Area | Evidence (checkpoint) | Result |
|---|---|---|
| Multi-visit voice session (API) | 3-visit extract/identity/save; identities `ambiguous(Lakshmi,3)/resolved(Ravi Rao)/unresolved(Anu)`; save persisted 2 correct visits, skipped 1; no observation mixing in DB | **PASS** |
| Multi-visit browser UI | Session extract/review/save flow: 3 cards, identity states, confirm-all saved | **PASS** |
| Notifications & PDF (API) | SMS preview/send demo, consent-less rejected 400, email preview/send demo with PDF attached (3234 bytes), stats correct; demo `@example.invalid` handling and `PATCH /api/beneficiaries/{id}` for contact edits | **PASS** (demo mode; no real provider delivery) |
| Notifications & Voice Verification (browser UI) | End-to-end UI checks across stats/tabs/composer, honesty banner/disclaimer, upload/analyse verdict with limitations | **PASS â€” 9/9 checks** |
| Dashboard modules | `/api/dashboard/modules` returns real counts incl. pending identity | **PASS** |
| i18n | 802 keys with parity across `en/kn/hi/te/ta`, corruption checks clean | **PASS** |
| 3D lighting / theme groundwork | Face lighting verified earlier; theme tokens/remap and initial pink palette applied with clean builds in prior runs | **PASS (as recorded)** |

## 3. Available but not executed in this pass

| Suite / script | Location | Notes |
|---|---|---|
| Backend scenario script | `backend/scripts/test_scenarios.py` | Scripted extraction/correction/batch-persistence checks; operates on app/DB state directly â€” run deliberately (not executed here). |
| Backend voice/language & seed scripts | `backend/scripts/test_kannada_voice.py`, `backend/scripts/validate_seed.py`, `backend/scripts/seed_dataset.py` | Utility/validation scripts; not executed in this pass. |
| Frontend browser-oriented tests | `frontend/tests/voice.session.test.js`, `voice.network.test.js`, `voice.household.test.js`, `voice.multivisit.test.js`, `voice.ui.test.js`, `notifications.ui.test.js` | Designed for a Vite-served/browser harness; not wired to `npm test` and not executed in this pass. |
| Node voice primitives | `scripts/test_voice.cjs` | `Pcm16Downsampler`/conversion unit tests (Node); not executed in this pass. |

## 4. Not verified / limitations

- **Live Gnani Prisma/Timbre and Google Gemini LLM behavior:** not verified without credentials/provider access; language/support claims depend on account configuration.
- **Real SMS/email delivery:** intentionally **not** performed (no provider credentials). Demo mode is labeled and must not be reported as sent/delivered.
- **Physical microphone / live streaming capture:** not exercisable in this environment (browser mic permission/real device). Prior checks used synthetic `MediaStream` and stubbed browser `SpeechRecognition` where recorded.
- **Authentication changes (new in this pass):** token expiry, login rate limiting, and authenticated SSE (`?token=`) were implemented and compiled/built successfully, but no dedicated automated regression suite was run against them in this pass.
- **Security testing:** no penetration test, fuzzing, IDOR/ownership audit, WebSocket auth validation, or dependency audit performed (see `SECURITY_REPORT.md`).
- **Performance/load/concurrency:** no Locust/k6/load run, no DB query profiling, and no multi-process/race/idempotency stress testing performed.
- **Visual regression:** UI theme sweep changes (Login, Overview gradients, Reminders accent) compiled and built; screenshots/visual diffs were not captured in this environment.

## 5. Summary

Core functionality previously verified in the checkpoint remains evidenced there, and this pass confirms a **clean frontend build**, **clean backend compilation** of modified modules, and **11/11 passing synthetic-voice screening API tests**. Broader security, live-integration, device, and load/performance validation remain outstanding and should be completed before any production claim.

