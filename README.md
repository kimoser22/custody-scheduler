# Custody Scheduler

Compute-on-read 2-2-3 custody calendar with dual-parent override approvals.

## Run locally

### API (terminal 1)

The API **fails closed**: `AUTH_SIGNING_SECRET` must be set or every
authenticated request returns 401. To use the sign-in flow, also set demo
passcodes (they are hashed at seed time and never committed):

```powershell
cd C:\Users\andre\custody-scheduler
.\.venv\Scripts\Activate.ps1
$env:AUTH_SIGNING_SECRET = "dev-only-change-me"
$env:SEED_PARENT_A_PASSCODE = "alpha"
$env:SEED_PARENT_B_PASSCODE = "bravo"
$env:SEED_VIEWER_PASSCODE = "look"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

(Or put these in `.env` — see `.env.example`. Passcodes only seed on a fresh
DB; delete `custody.db` to re-seed.)

### Frontend (terminal 2)

```powershell
cd C:\Users\andre\custody-scheduler\frontend
npm run dev
```

Open http://localhost:3000/schedule

## Sign in

The API trusts only HMAC-signed tokens issued by `POST /api/v1/auth/token` in
exchange for a valid passcode. On the schedule page, pick an **Identity**, enter
that identity's passcode, and click **Sign in**; the returned token is stored and
sent as `Authorization: Bearer <token>`.

| Identity | User id | Passcode (demo) |
|----------|---------|-----------------|
| Viewer | 2 | `SEED_VIEWER_PASSCODE` |
| Parent A | 101 | `SEED_PARENT_A_PASSCODE` |
| Parent B | 102 | `SEED_PARENT_B_PASSCODE` |

Get a token directly:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/auth/token `
  -H "Content-Type: application/json" `
  -d '{"user_id": 101, "passcode": "alpha"}'
```

## 60-second web demo

1. Sign in as **Parent A** (identity + passcode), click a day, submit an override request.
2. That request appears under **Pending** as “Waiting for the other parent.”
3. Sign in as **Parent B**, **Approve** the request.
4. The calendar day gets the orange override styling.
5. Refresh — the override stays (approved + persisted).
6. Switch to **Viewer** — schedule is readable; clicking a day does not open the request form.

Use **Previous / Next** to move between months.

## SMS double-handshake concierge

SMS sits **alongside** the web UI. A swap becomes calendar-visible only after:

1. Initiator texts a swap request → draft created → SMS asks for **YES/NO**
2. Initiator replies **YES** → status `Pending` → counterparty receives proposal
3. Counterparty replies **ACCEPT** → status `Approved` + `is_active` (engine-visible)
4. **DENY** / initiator **NO** → `Rejected` (not on calendar)

If the inbound message doesn't clearly specify **both** a date and a parent
(e.g. `swap 2026-07-08 to Parent B`), the concierge replies asking for
clarification and creates no draft — it never guesses a date or parent.

Webhook: `POST /api/v1/twilio/sms` (Twilio form fields `MessageSid`, `From`, `Body`).

Seeded demo phones (recreate `custody.db` if the schema changed):

| Parent | Phone |
|--------|-------|
| Parent A | `+15550001` |
| Parent B | `+15550002` |

Optional env for live Twilio sends:

```
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

Without those, SMS bodies are recorded by `EnvTwilioSmsGateway` in-process (tests use fakes). Point Twilio at your tunnel, e.g. `https://<host>/api/v1/twilio/sms`.

### Terminal simulator (no Twilio / ngrok)

Walk the double-handshake in your terminal against the real LangGraph + in-memory DB:

```powershell
cd C:\Users\andre\custody-scheduler
.\.venv\Scripts\python.exe -m concierge.simulator
```

Example:

1. Initial SMS: `swap 2026-07-08 to Parent B for trains`
2. When paused → reply `YES` (initiator confirm)
3. When paused again → reply `ACCEPT` (counterparty consent)
4. Simulator prints final override status (`Approved` / `is_active=True`) and the FakeSms log

Tests: `pytest tests/` covers handshake domain, repos, nodes, LangGraph interrupt/resume, webhook, runner E2E, and the simulator helper.

## Deploy API to Fly.io

The Next.js app stays on Vercel (or local). Fly hosts **only** the FastAPI API with a persistent SQLite volume.

Prerequisites: [flyctl](https://fly.io/docs/flyctl/install/) installed and `fly auth login`.

From the **repo root** (where `Dockerfile` and `fly.toml` live):

1. Create the app without deploying (first time only):

```powershell
fly launch --no-deploy
```

2. Create the 1GB volume in `iad` (must match `primary_region` / mounts):

```powershell
fly volumes create sqlite_data --region iad --size 1
```

3. Set the required auth signing secret (a long random value) and Twilio
   secrets (use your real values). Optionally seed demo login passcodes:

```powershell
fly secrets set AUTH_SIGNING_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
fly secrets set TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... TWILIO_FROM_NUMBER=...
# Optional demo logins (omit to disable passcode login for those users):
fly secrets set SEED_PARENT_A_PASSCODE=... SEED_PARENT_B_PASSCODE=... SEED_VIEWER_PASSCODE=...
```

Without `AUTH_SIGNING_SECRET` set, the deployed API returns 401 for every
authenticated request. Passcodes are hashed and only seed on a fresh volume.

4. After you have a Vercel URL, allow its origin (keep localhost for local UI against prod API if needed):

```powershell
fly secrets set ALLOWED_ORIGINS="http://localhost:3000,https://YOUR_APP.vercel.app"
```

5. Deploy:

```powershell
fly deploy
```

6. Smoke-test: open `https://custody-scheduler-api.fly.dev/docs`

7. Point Twilio’s SMS webhook at:

`https://custody-scheduler-api.fly.dev/api/v1/twilio/sms`

Notes:

- Run **one machine / one uvicorn process** (as in `fly.toml` + Dockerfile `CMD`) so in-memory SMS handshakes survive between requests. **In-flight handshakes are not durable** — the LangGraph checkpoint and phone→thread registry live only in process memory, so any restart or deploy drops conversations paused mid-handshake (the app logs a warning about this at startup). Making them survive restarts would require a durable checkpointer; deferred for now.
- Do **not** set `ALLOW_SQLITE_SCHEMA_RESET` on Fly — that flag is for local SQLite drift recovery only.
- The Twilio webhook **fails closed**: with no `TWILIO_AUTH_TOKEN` it rejects (403) unless `TWILIO_ALLOW_UNVERIFIED=1` is set. Set the real `TWILIO_AUTH_TOKEN` secret on Fly; do **not** set `TWILIO_ALLOW_UNVERIFIED` there — it's for local dev / the simulator only.
- `DATABASE_URL` is set in `fly.toml` to `sqlite:////data/custody.db` on the mounted volume.

## Deploy frontend to Vercel

The calendar UI deploys from the `frontend/` folder. It calls the Fly API directly via `NEXT_PUBLIC_API_URL`.

1. Confirm the API is up: `https://custody-scheduler-api.fly.dev/docs` (and `/api/v1/health`).
2. In Vercel: Import the GitHub repo.
3. Set **Root Directory** to `frontend` (Framework Preset: Next.js).
4. Add environment variable (Production):

   `NEXT_PUBLIC_API_URL=https://custody-scheduler-api.fly.dev`

5. Deploy. Open `https://YOUR_APP.vercel.app/schedule`.
6. Allow the Vercel origin on Fly (CORS):

```powershell
fly secrets set ALLOWED_ORIGINS="http://localhost:3000,https://YOUR_APP.vercel.app"
```

7. On the schedule page, pick **Viewer** / **Parent A** / **Parent B** in the identity bar (API requires an `Authorization` token).

Notes:

- Local: leave `NEXT_PUBLIC_API_URL` unset so Next rewrites proxy to `127.0.0.1:8000`.
- `npm run build` uses the committed `frontend/openapi/schema.json` (no localhost OpenAPI fetch). Set `API_OPENAPI_URL` only when regenerating types from a running API.
