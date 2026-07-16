# Custody Scheduler

Compute-on-read 2-2-3 custody calendar with dual-parent override approvals.

## Run locally

### API (terminal 1)

```powershell
cd C:\Users\andre\custody-scheduler
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend (terminal 2)

```powershell
cd C:\Users\andre\custody-scheduler\frontend
npm run dev
```

Open http://localhost:3000/schedule

## Dev identities

Use the **Identity** dropdown on the schedule page (or set `Authorization` headers):

| Identity | Token | User id |
|----------|-------|---------|
| Viewer | `viewer:dev` | 2 |
| Parent A | `parent:a` | 101 |
| Parent B | `parent:b` | 102 |

## 60-second web demo

1. Switch to **Parent A**, click a day, submit an override request.
2. That request appears under **Pending** as “Waiting for the other parent.”
3. Switch to **Parent B**, **Approve** the request.
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
