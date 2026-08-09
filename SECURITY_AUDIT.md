# Static Security Audit — Custody Scheduler

*Audited 2026-08-08 against `master`. Static analysis of the whole repository (excluding `node_modules`, `.venv`, build output). Scope: exposed secrets, authentication gates, rate limiting, session/token handling, injection, transport. Every finding cites file:line evidence.*

## Overall assessment

**No High or Critical findings.** The application is fail-closed by design, every data endpoint is gated, tokens are HMAC-signed with expiry and constant-time verification, and no secrets are present in the repo or its git history. The findings below are **defense-in-depth hardening** (one Medium, the rest Low), not exploitable holes at this app's scale (a 4-person private family, custody data).

Severity uses likelihood × impact **for this deployment**, not a generic scale.

---

## Findings

### ✅ RESOLVED — 1. No security response headers (CSP, HSTS, X-Frame-Options)

> **Fixed** in [PR #20](https://github.com/kimoser22/custody-scheduler/pull/20).
> API responses carry CSP/HSTS/`X-Frame-Options`/`X-Content-Type-Options`/
> `Referrer-Policy` via `security_headers_middleware`; the frontend sets its own
> policy in `next.config.ts`. The load-bearing directive for Finding #2 is
> `connect-src 'self' <api-origin>`, which is what actually stops a token
> exfiltration POST to an attacker's host.

**Evidence:** `grep` for `Content-Security-Policy|Strict-Transport|X-Frame-Options|X-Content-Type-Options|Referrer-Policy` across [main.py](main.py), [api/](api/), and [frontend/next.config.ts](frontend/next.config.ts) returns **nothing**. No headers are set anywhere.

**Why it matters:**
- **No `Content-Security-Policy`.** This is the single highest-leverage gap because it's the mitigation for Finding #2 (localStorage tokens). Today there are no XSS vectors (React auto-escapes, no `dangerouslySetInnerHTML` — verified), but if one is ever introduced, a CSP is the difference between "bug" and "every family member's session token exfiltrated."
- **No `X-Frame-Options` / `frame-ancestors`.** The custody calendar can be framed by any site → clickjacking of the Approve/Reject buttons.
- **No `Strict-Transport-Security`.** `fly.toml` sets `force_https = true` ([fly.toml:19](fly.toml)) so the redirect happens, but without HSTS the *first* request over `http://` is still interceptable (SSL-strip). HSTS closes that window.

**Fix:** Add a response-header layer. On the frontend, `headers()` in `next.config.ts` covers the served pages; for the API, a small FastAPI middleware or per-response headers. Start with `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Strict-Transport-Security: max-age=63072000; includeSubDomains`, and a CSP as strict as the app allows (it loads no third-party scripts, so `default-src 'self'` is nearly achievable).

**Effort:** Small. **Payoff:** closes clickjacking, hardens transport, and pre-positions the XSS mitigation before it's needed.

---

### 🟠 MEDIUM — 2. Session tokens stored in `localStorage` (the "unencrypted session" surface)

**Evidence:** [frontend/src/lib/auth.ts](frontend/src/lib/auth.ts) stores the auth token, user id, and role in `window.localStorage` (lines 36, 60–62). No `httpOnly` cookie; JS-readable by design.

**Why it matters:** `localStorage` is readable by any script running on the origin, so a single XSS = token theft, and the token can't be protected with `httpOnly`/`Secure` flags the way a cookie can.

**Why it's Medium, not High — the real mitigations, verified:**
- **Tokens are short-lived:** 1-hour TTL, enforced server-side ([auth_tokens.py:53,82](api/auth_tokens.py)). A stolen token expires fast.
- **The stored `role` is display-only and never trusted.** The server re-derives role from the *signed* token on every request (`require_parent_role` → `get_current_user` → `verify_token`), so tampering with the localStorage `role` value grants nothing. Confirmed: no endpoint trusts a client-supplied role.
- **No XSS vector currently exists** (Finding #1's CSP would keep it that way).

**Fix (two tiers):**
- *Practical:* implement Finding #1's CSP — that's the proportionate mitigation, and it's cheaper than re-architecting auth.
- *If you ever want to eliminate the class:* move the token to an `httpOnly; Secure; SameSite=Strict` cookie. This is an architecture change (the API would read the cookie instead of the `Authorization` header, and CORS `allow_credentials` becomes load-bearing) — **not worth it for this app today**, but the right answer if it ever holds more sensitive data or more users.

---

### ✅ RESOLVED — 3. Passcode-change endpoint is not rate-limited

> **Fixed** in `fix/durable-shared-throttle`. `PATCH /me/passcode` now checks the
> throttle *before* `verify_passcode` and returns 429 + `Retry-After`, matching
> the login endpoint. The two surfaces share **one counter per user id**, so a
> stolen session can no longer buy a fresh five-strike budget by switching
> endpoints. New-passcode validation errors (too short, unchanged) deliberately
> do not count — otherwise a user could lock themselves out by fumbling the
> field they are setting.

**Evidence:** `PATCH /me/passcode` verifies the current passcode online ([me_router.py:174](api/me_router.py) `verify_passcode(body.current_passcode, ...)`) but has **no throttle**. The login endpoint *is* throttled ([auth_router.py:31–52](api/auth_router.py) via `login_throttle`), so this is an inconsistency in the hardening, not a blanket gap.

**Why it matters:** It's a second online passcode-guessing surface. Lower severity than login because it requires an already-authenticated session, so an attacker needs a valid token first — but on a shared/stolen device it lets someone brute the *current* passcode to lock in a change.

**Why it's Low:** the 8-character passcode floor ([me_router.py `_MIN_PASSCODE_LENGTH`](api/me_router.py)) makes brute force infeasible regardless, and the attacker already needs a session.

**Fix:** Reuse the existing `LoginThrottle` (keyed by `current_user.id`) around the `verify_passcode` failure path — a handful of lines, and it makes the two passcode surfaces consistent.

---

### 🟡 LOW — 4. Calendar feed token travels in the URL and is looked up non-constant-time

**Evidence:** `GET /schedule/feed.ics?token=...` authenticates via a query-string token ([router.py:369–390](api/router.py)), matched with a plain SQL `WHERE calendar_feed_token == token` (not a constant-time compare).

**Why it matters:**
- **URL exposure:** query strings land in proxy/access logs, browser history, and `Referer` headers — more places than an `Authorization` header would.
- **Timing:** the DB equality lookup isn't constant-time like `hmac.compare_digest`.

**Why it's Low, with the mitigations that already exist:**
- The token is `secrets.token_urlsafe(32)` = **256 bits** ([me_router.py:116](api/me_router.py)) — a timing side-channel against that is impractical, and there's no realistic online guessing.
- **Rotation is implemented** (`POST /me/calendar-feed` with `rotate: true`), so an exposed token can be revoked.
- A token-in-URL is **unavoidable** for calendar subscription — Google/Apple calendar clients can't send auth headers.

**Fix (optional):** low value given the above, but if you want to tighten: scope the token to feed-read only (it already is), and document rotating it if a device is lost. No constant-time fix is warranted for a 256-bit secret.

---

### ✅ RESOLVED — 5. Login throttle is per-process and in-memory

> **Fixed** in `fix/durable-shared-throttle`. Counters now live in a
> `login_attempts` table behind a `LoginThrottle` port, the same durable-state
> pattern as `sms_opt_outs` and `handshake_threads`.
>
> **This audit's original verdict — "none needed at current scale" — was wrong,**
> and the reason is in the bullet below that it under-weighted: the repo
> auto-deploys on merge. A two-process proof against a file-backed DB confirmed
> the old behavior concretely — five failed logins, then a restart, and the
> *correct* passcode returned **200 with a fresh token** while the lock should
> still have had ~118 seconds left. A defense that resets several times a week,
> for free, is weaker than its design implies. Same proof on the fix: 429.

**Evidence:** [api/login_throttle.py](api/login_throttle.py) holds counters in a module-level dict (`login_throttle = LoginThrottle()`), keyed by `user_id`.

**Why it matters:**
- **Resets on every deploy/restart** — and this repo auto-deploys on merge, so the counter clears often. (An attacker can't *trigger* a restart, so this only helps them incidentally.)
- **Not shared across machines** — a no-op today (single machine, enforced by the SQLite volume) but would silently weaken if ever scaled horizontally.
- **Keyed on `user_id`, not IP** — no global limit on an attacker cycling through user ids. Negligible here (3 users) but structurally worth noting.

**Why it's Low:** the 8-char passcode floor already makes brute force infeasible; the throttle is a secondary layer, and its weaknesses only reduce a defense that isn't the primary one.

**Fix:** ~~none needed at current scale.~~ Backed with a `login_attempts` table in the SQLite DB — see the resolution note above. The remaining two bullets (not shared across machines, keyed on `user_id` rather than IP) are unchanged and still acceptable: one machine is enforced by the SQLite volume, and IP-based limiting is negligible across three users while `X-Forwarded-For` behind Fly's proxy would need careful trust handling to not be spoofable.

---

## Audited and clean — no action needed

Reporting the negatives, since the audit asked for these categories specifically.

| Category | Finding |
|---|---|
| **Exposed secrets (repo)** | **None.** No `.env`, `.pem`, `.key`, or credential files tracked (`git ls-files`). `.gitignore` covers `.env`, `.env.*` (with an `!.env*.example` exception). The only secret-shaped literal is `AUTH_SIGNING_SECRET = "dev-only-change-me"` in a README **example** ([README.md:16](README.md)). |
| **Exposed secrets (git history)** | **None.** Full-history scan (`git log --all -p`) for `sk-ant-`, `SG.`, `AKIA…`, `BEGIN PRIVATE KEY`, and committed `.env` files found only `sk-ant-test-dummy` test fixtures. No real key was ever committed. |
| **Authentication gates** | **Complete.** Every data endpoint is gated: `get_current_user` (read: `/schedule`, `/me`, `/export.json`, `/overrides/pending`), `require_parent_role` (write: create/decide/sweep/`patch_me`), Twilio HMAC signature (`/sms`), or the feed token (`/feed.ics`). Only `/health` and `/token` are intentionally public. |
| **Object-level authz (IDOR)** | **Checked, safe.** `decide_override_request` verifies `row.family_id != current_user.family_id` before acting ([router.py:559](api/router.py)); `/me/*` always operate on `current_user.id`, never a path param. No horizontal-access path found. |
| **Token integrity** | **Solid.** HMAC-SHA256, `hmac.compare_digest` verification, expiry enforced, **fail-closed** when `AUTH_SIGNING_SECRET` is unset ([auth_tokens.py](api/auth_tokens.py)). Note: stateless, so no revocation before expiry — bounded by the 1h TTL. |
| **SQL injection** | **None.** All queries go through SQLModel/SQLAlchemy (parameterized). The only raw SQL is static DDL in boot migrations and a static `text("is_active = 1")` index predicate — no user data interpolated. |
| **XSS** | **No vectors.** No `dangerouslySetInnerHTML`, `innerHTML`, `eval`, or `new Function` in `frontend/src`. React auto-escapes. ICS output is escaped via `escape_ics_text` ([core/ics.py](core/ics.py)). |
| **Transport** | HTTPS forced at the edge (`force_https = true`, [fly.toml:19](fly.toml)). (Gap: no HSTS — see Finding #1.) |
| **Webhook spoofing** | **Fail-closed.** `/sms` rejects (403) without a valid Twilio signature; unverified mode requires an explicit opt-in flag never set in prod. The `X-Forwarded-*` trust in `_external_url` is **not** a bypass — forging the host only changes the URL the signature is checked against, and the attacker still can't produce a valid signature without the auth token. |
| **Error leakage** | **None.** No raw exceptions or tracebacks returned to clients; all `HTTPException` details are static strings. |
| **Debug exposure** | `SQL_ECHO` (logs bound params incl. phone numbers) defaults **off** and is documented as local-only; the one `print()` is a guarded schema-reset warning that never runs on Fly. |

---

## Minor note (not ranked)

**CORS `allow_credentials=True` is unnecessary.** [main.py:279–282](main.py) sets `allow_credentials=True` with `allow_methods=["*"]` / `allow_headers=["*"]`. This is **not a vulnerability** — `allow_origins` is an explicit allowlist (`parse_allowed_origins`), not `*`, and Starlette forbids `*`-origin-with-credentials anyway. But since the app authenticates via the `Authorization` header (localStorage), not cookies, `allow_credentials` does nothing and could be dropped; tightening `allow_methods`/`allow_headers` to the actual set used is optional defense-in-depth.

## Suggested order

~~**Finding #1 (security headers) first** — it's the highest-value single change and it pre-mitigates #2. Then #3 (reuse the existing throttle — trivial). #2's cookie migration, #4, and #5 are "only if the threat model grows."~~

**Status as of 2026-08-08:** #1, #3, and #5 are fixed. Remaining:

- **#2 (localStorage tokens)** — open by choice. #1's CSP is the proportionate mitigation and it has shipped; the cookie migration stays "only if the threat model grows."
- **#4 (feed token in URL)** — **closed as won't-fix**, deliberately. Hashing the stored token is its only real hardening, but [CalendarSubscribe.tsx](frontend/src/components/CalendarSubscribe.tsx) has a "Show link" button that re-displays the existing token; hashing would make the subscribe URL show-once, so a grandparent who lost their link would have to rotate rather than re-copy it. 256 bits of entropy plus working rotation is the better trade for this audience.
