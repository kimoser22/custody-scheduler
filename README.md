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

## Email notifications

The web calendar's core loop is *request → the other parent approves*, so the
other parent has to find out a request exists. Email needs no carrier approval,
which makes it the notification channel available before A2P clears.

| Event | Who gets the email |
|-------|--------------------|
| Override requested | The **other** parent (never the requester) |
| Request approved / declined | The **original requester** |

Configure with a Gmail app password (2FA must be enabled on that account):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<app password>
SMTP_FROM=you@gmail.com
SEED_PARENT_A_EMAIL=parent-a@example.com
SEED_PARENT_B_EMAIL=parent-b@example.com
```

With any of the `SMTP_*` values missing, notifications are a **silent no-op** —
everything else behaves identically, so local dev and unconfigured deploys need
no special casing.

Two guarantees worth knowing, both covered by tests:

- **A mail failure never fails an override.** Sending happens in a background
  task and every exception is swallowed and logged. The custody record is what
  matters; the email about it is not.
- **A missing address is not an error.** A parent with no email simply isn't
  notified; the request still succeeds.

`SEED_PARENT_*_EMAIL` is back-filled onto existing users on restart when their
email is still empty, so adding it to an already-seeded database needs no reset
(an address that is already set is never overwritten — same rule as passcodes).

## SMS double-handshake concierge

SMS sits **alongside** the web UI. A swap becomes calendar-visible only after:

1. Initiator texts a swap request → draft created → SMS asks for **YES/NO**
2. Initiator replies **YES** → status `Pending` → counterparty receives proposal
3. Counterparty replies **ACCEPT** → status `Approved` + `is_active` (engine-visible)
4. **DENY** / initiator **NO** → `Rejected` (not on calendar)

If the inbound message doesn't clearly specify **both** a date and a parent
(e.g. `swap 2026-07-08 to Parent B`), the concierge replies asking for
clarification and creates no draft — it never guesses a date or parent.

### Intent parsing (two layers, one fail-safe contract)

`HeuristicIntentParser` runs first: deterministic matching for an ISO date plus
`Parent A` / `Parent B`. It is free, instant, and handles well-formed messages.

When `ANTHROPIC_API_KEY` is set, a Claude fallback (`LLMIntentParser`) is
consulted **only if the heuristic declines** — that's what reads natural
phrasing like `swap next Friday to Parent B`, resolving relative dates against
today. Well-formed messages never cost a token. Model defaults to
`claude-opus-4-8`, overridable with `CONCIERGE_LLM_MODEL`.

**Both layers fail the same way, on purpose.** An API error, a timeout, a
refusal, a missing field, or a date that isn't a real calendar date all return
"unclear" — which sends the clarification SMS above. Neither layer is ever
allowed to guess, because a wrong parse silently drafts the wrong custody
handoff. With no API key the behavior is exactly the deterministic parser, and
the `anthropic` SDK is imported lazily so an unconfigured deploy never loads it.

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

### Paused handshakes survive restarts

A swap spans three inbound messages (request → `YES` → `ACCEPT`), so the graph
sits paused between turns. Both halves of that state are persisted to
`custody.db`: LangGraph checkpoints via `SqliteSaver`, and the phone→thread
mapping in the `handshake_threads` table. A deploy or crash mid-conversation
resumes where it left off rather than silently starting over.

The rule is *durable when the database is a file*. Against an in-memory
database — tests, and the simulator — it falls back to `MemorySaver`, because a
second connection to `:memory:` is a different database and a checkpointer
there would persist nothing. Startup logs which mode is active.

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

- **Run exactly one machine / one uvicorn process.** This is how the app is currently configured — `fly.toml` (`min_machines_running = 1`, `auto_stop_machines = 'off'`) plus the Dockerfile `CMD` (a single uvicorn process, no `--workers`). Note that `min_machines_running` is a floor, not a ceiling: nothing prevents `fly scale count 2`, so this is a rule you keep, not one Fly keeps for you. Two independent reasons:
  - **SQLite volume — data integrity, applies now.** The `sqlite_data` volume attaches to exactly one machine at a time. A second machine does not share the database; it gets its own empty volume, producing two silently diverging copies of the calendar. This holds regardless of whether SMS is live.
  - **Single writer to the checkpoint — applies once SMS is live.** In-flight handshakes are now durable: the LangGraph checkpoint and the phone→thread registry are both written to `custody.db`, so a restart or deploy resumes a paused conversation instead of dropping it. That state lives on the volume, though, so it inherits the same one-machine limit as everything else there.
- **A Fly volume is not a backup.** It survives deploys; it does not survive host loss or an accidental delete. Fly takes automatic volume snapshots, but treat those as a convenience, not a recovery plan for real custody records. Be deliberate with the `fly ssh console -C "rm -f /data/custody.db"` step in the re-seed runbook above — on Fly that permanently deletes real family data. It is a different mechanism from `ALLOW_SQLITE_SCHEMA_RESET`, which is local-only drift recovery and must never be set on Fly.
- Do **not** set `ALLOW_SQLITE_SCHEMA_RESET` on Fly — that flag is for local SQLite drift recovery only.
- The Twilio webhook **fails closed**: with no `TWILIO_AUTH_TOKEN` it rejects (403) unless `TWILIO_ALLOW_UNVERIFIED=1` is set. Set the real `TWILIO_AUTH_TOKEN` secret on Fly; do **not** set `TWILIO_ALLOW_UNVERIFIED` there — it's for local dev / the simulator only.
- `DATABASE_URL` is set in `fly.toml` to `sqlite:////data/custody.db` on the mounted volume.
- `ANTHROPIC_API_KEY` is **intentionally not set on Fly** while A2P 10DLC review is pending — the LLM intent-parser fallback is phase 2, alongside live carrier SMS. Parsing is env-gated, so with the secret unset the API runs the deterministic parser only (no LLM calls, no cost, no code change). Before re-adding it, set a spend limit on a dedicated Anthropic Console workspace and scope the key to that workspace, so a runaway can't reach the main balance.

### Private family launch — seed & re-seed

Login passcodes come from the `SEED_*_PASSCODE` secrets, hashed into the `users`
rows when they are first created. Seeding **reconciles per-user on boot**
(`ensure_default_seed_data` in `main.py`): it inserts any missing seed user and
**back-fills a NULL passcode** from its secret when that secret is now set — but
it **never overwrites a passcode that is already set**.

Consequences:

- **Enabling login for the first time** (or after adding a secret that wasn't set
  when the volume was first seeded): just set the secret and redeploy — the next
  boot back-fills the NULL hash. No reset needed.

  ```powershell
  fly secrets set SEED_PARENT_A_PASSCODE=... SEED_PARENT_B_PASSCODE=... SEED_VIEWER_PASSCODE=...
  fly deploy   # or: fly apps restart custody-scheduler-api
  ```

- **Changing an already-set passcode** requires a full re-seed, because the stored
  hash is never overwritten. Reset the volume's DB and let the fresh seed re-hash
  (destroys existing overrides — fine pre-launch):

  ```powershell
  fly secrets set SEED_PARENT_A_PASSCODE=<new-known-value>   # + others as needed
  fly ssh console -C "rm -f /data/custody.db"
  fly apps restart custody-scheduler-api
  ```

- **Verify** a passcode works (use the value you set; never commit real passcodes):

  ```powershell
  curl.exe -X POST https://custody-scheduler-api.fly.dev/api/v1/auth/token `
    -H "Content-Type: application/json" `
    -d '{"user_id": 101, "passcode": "<value>"}'   # -> access_token on success
  ```

  A `401` means the seeded user has no matching hash — re-check the secret, then
  re-seed. (In PowerShell use `curl.exe`, not the `curl` alias.)

Both grandparents share the single **Viewer** login (`SEED_VIEWER_PASSCODE`);
viewers are read-only, so no separate identity is needed.

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

### A2P campaign Privacy / Terms URLs

After Vercel is live, enter these in the Twilio campaign registry:

- Privacy: `https://YOUR_APP.vercel.app/privacy`
- Terms: `https://YOUR_APP.vercel.app/terms`

Copy lives in `frontend/src/lib/legal-copy.ts`. SMS `STOP` / `HELP` / `START` are handled in `concierge/runner.py` before any swap handshake. `STOP` persists to `sms_opt_outs` and blocks further outbound scheduling texts until `START`.
