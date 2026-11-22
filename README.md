# ASHA Swar Nirantar â€” The Voice Pulse of Every Village

ASHA Swar Nirantar is an AI-powered, multilingual, voice-first community healthcare management platform designed to simplify and strengthen the daily work of Accredited Social Health Activists (ASHA workers). It reduces manual documentation, improves household/beneficiary record management, and supports timely follow-ups through an intelligent digital companion named Tara.

**Vision:** Listen to every voice, remember every health journey, and help protect every community.

## Key capabilities

- **Voice Visit (multi-beneficiary, reviewed):** record a continuous visit, segment and extract structured observations per beneficiary, resolve identity explicitly, and require ASHA review/confirmation before anything is saved. Unresolved or ambiguous observations are never auto-assigned.
- **Household & beneficiary register:** households, members, QR-based identification, Pulse Thread (chronological history) and Pulse Drift (deterministic overdue/upcoming follow-ups).
- **Notifications & PDF reports:** SMS/email follow-ups and A4 PDF reports generated from real beneficiary/visit/follow-up records only. When provider credentials are not configured the system runs in **honest demo mode** and labels messages **"DEMO â€” NOT ACTUALLY SENT"** (nothing is claimed as delivered).
- **Safety:** rule-based danger-sign flags use approved phrases/messages, AI assists with extraction/structuring, and human confirmation remains essential before records are saved.

## Tech stack

- **Frontend:** React 18, Vite 5, Tailwind CSS, Framer Motion, React Three Fiber / Three.js
- **Backend:** Python 3.11, FastAPI, SQLAlchemy, SQLite (default), WebSockets/SSE for real-time updates
- **Integrations (optional, credential-gated):** Gnani Prisma (STT), Google Gemini (Tara AI / structured extraction & assistance), Gnani Timbre (TTS), SMS provider, SMTP email

## Repository layout

- `backend/` â€” FastAPI app (`app/`), scripts, seed/data utilities, `.env.example`
- `frontend/` â€” Vite React app (`src/`), tests
- `scripts/` â€” utility tests (e.g. voice primitive checks)
- `TESTING_REPORT.md`, `SECURITY_REPORT.md`, `CHANGES_SUMMARY.md` â€” verification and hardening notes

## Prerequisites

- Python **3.11+**
- Node.js **18+** and npm
- (Optional) Provider credentials for Gnani/SMS/SMTP to enable live integrations; without them the app operates in honest demo mode

## Installation

### 1) Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env as needed (keep secrets out of git)
```

### 2) Frontend

```powershell
cd frontend
npm install
```

## Configuration

Copy `backend/.env.example` to `backend/.env`. Key settings:

| Variable | Purpose | Default / note |
|---|---|---|
| `GNANI_MODE` | `demo` or `live` | `demo` (never fakes live connectivity) |
| `GNANI_*` | Prisma (STT) / Timbre (TTS) endpoints & keys | required only for live voice integrations |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Google Gemini LLM for Tara AI | required for Gemini-powered extraction/assistance |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite:///./asha_swar.db` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins | `http://localhost:5173,http://127.0.0.1:5173` |
| `TOKEN_TTL_HOURS` | Bearer session lifetime (hours) | `168` (7 days); `0` disables expiry (local demo only) |
| `LOGIN_RATE_WINDOW_SECONDS` / `LOGIN_RATE_MAX_ATTEMPTS` | In-memory login rate limiting (per IP) | `300` / `10` |
| `SMS_PROVIDER_URL` / `SMS_PROVIDER_KEY` | Live SMS delivery | blank => demo mode (not actually sent) |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM/TLS` | Live email delivery | blank => demo mode (not actually sent) |
| `REPORT_DIR` | Trusted directory for generated PDF reports | defaults to `backend/generated_reports` |

The frontend proxies `/api` (including WebSockets) to `http://localhost:8000` in dev (`frontend/vite.config.js`). To point elsewhere, set `VITE_API_BASE` when building/running the frontend.

## Running locally

### Backend

```powershell
cd backend
python run.py
# serves http://localhost:8000
```

`run.py` starts Uvicorn with reload for local development. Normal startup creates the schema but does not seed beneficiaries.
Normal startup creates the schema but does not seed beneficiaries. To explicitly load sample data into an empty development database, enable demo setup before starting the backend:

```powershell
$env:ENABLE_DEMO_SETUP = "true"
python run.py
```

Demo sample records are not added to a database that already contains beneficiaries. The demo login is printed only when demo setup is enabled.

### Frontend

```powershell
cd frontend
npm run dev
# serves http://localhost:5173
```

Then open `http://localhost:5173` and sign in with a registered worker account. In explicitly enabled demo setup, use the demo credentials printed by the backend.

## Testing (what is actually available)

See **[TESTING_REPORT.md](TESTING_REPORT.md)** for executed checks, results, and limitations.

Quick commands (from repo root / folders as noted):

```powershell
# backend: Python syntax/compile check
cd backend; python -m py_compile app\main.py app\auth.py app\routers\auth_router.py app\routers\dashboard.py app\routers\notifications.py

# backend: scripted scenario tests (operate on app/DB directly; review script before running)
cd backend; python scripts\test_scenarios.py

# frontend: production build
cd frontend; npm run build

# node: voice primitive unit tests
node scripts/test_voice.cjs
```

Browser-oriented frontend tests live under `frontend/tests/` (voice session/network/household/multivisit/UI, notifications UI). They are designed for a Vite-served/browser harness and are not wired to an npm `test` script.

## Security notes

See **[SECURITY_REPORT.md](SECURITY_REPORT.md)** for hardening applied in this pass, remaining risks, and operational guidance (secrets handling, TLS, deployment/WAF rate limiting, authz scoping, media upload controls, etc.).

## Deployment notes

This repository is a **prototype/demo-oriented** setup (SQLite, in-process background loop, in-memory login limiter). For a real deployment:

- Run behind HTTPS/TLS with a reverse proxy (e.g. Nginx/Caddy) terminating TLS and enforcing security headers.
- Use a managed database (e.g. PostgreSQL) instead of SQLite for concurrency/durability; run migrations deliberately.
- Configure `CORS_ORIGINS` to exact trusted origins only; keep credentials and provider keys in a secret manager (never in git).
- Use a multi-process-safe rate limiter/WAF (the built-in limiter is per-process, in-memory) and monitor auth failures.
- Serve the built frontend (`frontend/dist`) via a static host/CDN or the proxy and restrict the backend to internal networking as appropriate.
- Load balancing is only warranted once you move off SQLite/in-memory state and make background work/idempotency safe across instances.

## Important changes in this hardening pass

See **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** for a concise list of modified files and behavior changes.

## Data & privacy

Demo data is synthetic. Do not place real personal health information into a demo deployment. Generated reports and notifications must only reflect real records for the intended beneficiary and must be handled as sensitive information in production contexts.

