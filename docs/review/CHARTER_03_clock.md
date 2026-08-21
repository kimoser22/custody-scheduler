# Charter 3 — Calendar clock

**Outcome focus:** (2) Wrong day → wrong parent told they have the kids.

**Owns:** Civil calendar dates vs UTC-naive instants.

**Does not own:** Overlap constraints (→ Charter 4) or cross-surface loader drift (→ Charter 1).

## In-scope paths

- `core/clock.py` (`household_today`, `HOUSEHOLD_TIMEZONE`)
- `concierge/factory.py` (what date the parser / LLM prompt is told is “today”)
- SMS relative-date path (heuristic/LLM “tomorrow”)
- ICS feed window dating in `api/router.py`
- `frontend/src/lib/calendar.ts` (`localTodayDate`) — **known divergence** from
  household TZ; document if still unfixed, only escalate if it causes outcome 2
  in a concrete scenario

## Must inspect

- Instants (`expires_at`, audit, leases) stay UTC-naive; civil “today/tomorrow”
  use `household_today`.
- Evening Eastern (UTC already next calendar day) does not shift SMS “tomorrow”
  by one day.
- Invalid `HOUSEHOLD_TIMEZONE` fails loud (no silent UTC fallback).
- ICS window / export filename day align with household civil date where MAP says they should.

## Out of scope

- Approval authorization, active_custody_days mechanics.

## Forbidden conclusions

- “Frontend uses local today so SMS should too” without tracing MAP’s clock rule.
- Calling the known web-vs-household sticky divergence a new critical finding
  without a parent-facing wrong-assignment repro (it may be a written known gap).

## Eval (local only)

Branch: `DO-NOT-MERGE-eval-clock` — never push.

Revert `822e7a1` (or equivalent) and remove/revert
`tests/test_household_clock.py`, `tests/test_sms_relative_dates.py`, and feed
tests that exist only for that fix. Charter must rediscover UTC-vs-household
“tomorrow” slip.

## Finding template

```
Claim:
Outcome: 2 wrong assignment (wrong civil day)
Location: path:line
Executable repro:
Expected: (household civil date)
Actual: (UTC or other)
```

## Done when

≥1 gated finding, or written negative listing clock seams checked and commands run.
