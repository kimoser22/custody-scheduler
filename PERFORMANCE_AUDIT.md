# Performance Audit — Custody Scheduler

*Audited 2026-08-08 against `master` (post PR #18). All numbers measured, not estimated: production build output, live `curl` probes against the Fly API, and byte-level measurement of generated payloads.*

## Baseline (for context)

| Measurement | Value |
|---|---|
| First Load JS, `/schedule` | **116 kB gzipped** (102 kB is the React 19 + Next 15 framework floor; page chunk is 10.5 kB) |
| Runtime dependencies | 4 (`next`, `react`, `react-dom`, `openapi-fetch`) |
| Live API compression | **Edge-compressed by Fly proxy** — `openapi.json` 14,256 B raw → 3,320 B gzip / 2,746 B zstd, negotiated from `Accept-Encoding` |
| ICS feed payload (210 days) | 37,517 B raw → 2,027 B over the wire (edge gzip) |
| Month of schedule JSON | 4,371 B raw → ~234 B over the wire |

The bundle is small and the wire is compressed. The real costs in this app are **round trips and loading order**, not bytes — and the top issues below reflect that.

---

## Top 5 issues, by impact

### 1. Every schedule view pays a serial write-then-read before pending requests render

**What:** `PendingOverrides` awaits `POST /overrides/sweep-expired`, *then* awaits `GET /overrides/pending` — two sequential round trips on every mount ([PendingOverrides.tsx:44–51](frontend/src/components/PendingOverrides.tsx)). And it remounts constantly: `key={`${authToken}-${pendingListVersion}`}` in [schedule/page.tsx:192](frontend/src/app/schedule/page.tsx) forces a full remount (and the double round trip) on every sign-in **and every approve/reject decision**.

**Why it's #1:**
- The sweep is **redundant for display**: `list_pending_overrides` already filters `expires_at > now` server-side ([api/router.py](api/router.py)) — expired requests never appear whether or not the sweep ran. The client is paying an RTT to duplicate a server-side guarantee.
- It's a **write on every page view**. Sweep exists to persist `Expired` status; running it as a display precondition means every visit mutates.
- For **Viewers** (the grandparents), the sweep endpoint requires the Parent role — their POST is a guaranteed 403, silently swallowed. A wasted round trip on every load, for two of the four users.
- On mobile (the app just had a phone-layout pass), RTT to `iad` dominates: each serialized trip is ~100–300 ms of blank "Loading..." under the fold.

**Fix:** Delete the client-side sweep from the read path. If persisting `Expired` status matters, either sweep server-side inside the pending-list handler (it already computes `now`) or fire the sweep *after* the fetch, non-blocking, only for Parent sessions. Separately, replace the `key`-remount pattern with a `refresh` prop/callback so a decision triggers one `GET`, not a remount plus the full waterfall.

**Effort:** Small. **Payoff:** one fewer RTT on the most-visited screen, no more per-view writes, no more 403 noise.

---

### 2. Month navigation refetches everything and blanks the whole calendar

**What:** `useSchedule` keeps no cache — every Previous/Next click refetches the month even if you viewed it seconds ago, and while loading, the page renders `Loading schedule...` **instead of** the grid ([schedule/page.tsx:178–187](frontend/src/app/schedule/page.tsx)). `refetch()` after every override decision does the same: the entire calendar disappears and reflows.

**Why it matters:** This is the single biggest *perceived*-performance issue. Flipping months is the core browsing gesture; each flip costs a full RTT with a white flash and layout shift, and revisiting the current month re-pays the cost. The payload being ~234 B compressed makes this pure latency, not bandwidth — exactly what a cache eliminates.

**Fix:** Cache results keyed by `startDate` in the hook (a `Map` in a ref is enough — no library needed), render stale data immediately while revalidating, and only show the loading state when there's nothing cached. Bonus: prefetch adjacent months after the current one settles, making Previous/Next instant.

**Effort:** Small–medium (hook change + tests). **Payoff:** month navigation goes from spinner-every-click to instant; decisions no longer blank the grid.

---

### 3. Interaction- and auth-gated features are eagerly bundled and hydrated

**What:** [schedule/page.tsx](frontend/src/app/schedule/page.tsx) statically imports everything: `OverrideForm` (renders only after a Parent clicks a day), `AccountSettings` + four panels — `CalendarSubscribe`, `PasscodeSettings`, `RecordsExport`, `ContactSettings` (behind a collapsed disclosure, most never opened in a session), and `PendingOverrides` (auth-gated). All of it ships, parses, and hydrates before first paint for every visitor — including a signed-out one who can use none of it.

**Why it matters (with honest sizing):** The whole page chunk is 10.5 kB gzipped, so the byte win is modest (~4–6 kB). The real wins are parse/hydrate time on the phones this app now targets, and **keeping growth honest** — this page gains a component per feature PR (six in the last batch), and the eager-import pattern means every future feature lands in the critical path by default. This is the codebase's one genuine "synchronous loading that should be async" pattern.

**Fix:** `next/dynamic(() => import(...))` for `OverrideForm` and the `AccountSettings` subtree (load on first expand), and optionally `PendingOverrides` behind the auth check. No SSR flag needed — they're client-only already.

**Effort:** Small. **Payoff:** leaner first paint now; critical path stops growing with each new settings panel.

---

### 4. Cross-origin API gets no preconnect, and the first fetch waits for full hydration

**What:** The browser discovers `custody-scheduler-api.fly.dev` only when the first `fetch` fires — which itself waits for HTML → JS download → parse → hydrate → `localStorage` read. DNS + TCP + TLS to a second origin (~100–300 ms on mobile) is then paid serially, on top. [layout.tsx](frontend/src/app/layout.tsx) has no resource hints.

**Why it matters:** It's the cheapest fix in this list — the connection setup can overlap with JS download instead of following it. (Full SSR of schedule data would eliminate the hydration gate entirely, but auth lives in `localStorage`, so that's an architecture change — moving tokens to cookies — and not worth it for this app today. The preconnect is the practical 80%.)

**Fix:** In `layout.tsx`: `<link rel="preconnect" href="https://custody-scheduler-api.fly.dev" crossOrigin="anonymous" />` (driven by `NEXT_PUBLIC_API_URL`, omitted in local dev where the API is same-origin via rewrites).

**Effort:** One line. **Payoff:** shaves connection setup off time-to-first-data on every cold mobile visit.

---

### 5. The ICS feed has no conditional-GET support and regenerates 210 days per poll

**What:** `GET /schedule/feed.ics` recomputes the full 210-day calendar and returns 200 + full body on every request — no `ETag`, no `Last-Modified`, so `If-None-Match` from clients is impossible ([api/router.py](api/router.py), feed handler; `Cache-Control: private, max-age=300` only).

**Why it matters (and why it's last):** Calendar clients poll on their own schedule, forever, from every subscribed device — this is the app's only *unbounded* traffic source. But the measured cost is small: ~2 kB per poll over the wire (edge gzip) and a cheap in-memory generation. This is hygiene-before-it-scales, not a current pain.

**Fix:** Compute a weak ETag from what actually changes the feed — e.g. hash of `(baseline row, max(overrides.decided_at), count)` or simply the day-list bytes — and return `304 Not Modified` on match, skipping generation. Keep `max-age=300`.

**Effort:** Small. **Payoff:** most polls become header-only 304s; feed cost stays flat as devices subscribe.

---

## Audited and clean — no action needed

These were explicitly checked because the audit asked for them; reporting the negative result is part of the audit.

| Area | Finding |
|---|---|
| **Unused CSS** | None. `globals.css` is 15 lines; Tailwind content globs (`./src/**/*.{js,ts,jsx,tsx,mdx}`) are correct, so JIT emits only used utilities. |
| **Redundant JS imports** | None found. 4 runtime deps, no overlapping libraries, no lodash/moment-class offenders. `openapi/schema.json` (14 kB) and `schema.d.ts` are **not** bundled — verified type-only usage, erased at build. |
| **Uncompressed assets** | Not an issue in production — **measured**: Fly's edge proxy negotiates gzip/br/zstd from `Accept-Encoding` (14,256 B → 3,320 B gzip on `openapi.json`), and Vercel compresses the frontend. App-layer `GZipMiddleware` would only benefit direct-to-machine access and local dev; not worth the CPU on the request path. |
| **Fonts/images** | There are none — no `public/` dir, system font stack. Nothing to optimize. |
| **Bundle size** | 116 kB first load is ~framework floor for Next 15 + React 19; no route is an outlier. |
| **Backend request-path sync work** | Reviewed, deliberate, and bounded: LLM parse capped at 8 s inside a 15 s Twilio window; email sends backgrounded; Twilio sends swallowed on failure. Concierge sends up to 2 sequential Twilio REST calls inside the webhook thread — acceptable at family scale; revisit only if webhook latency ever matters. |

## Suggested order of work

1 and 2 together (they're both in the schedule-page data path and share tests), then 4 (one line), then 3, then 5.
