# Charter 4 — Active schedule integrity (write path)

**Outcome focus:** Wrong calendar truth after approve/overlap (feeds outcome 1
later; file **write** defects here).

**Owns:** Does activation record the right days and reject impossible states?

**Does not own:** Whether two readers agree after the fact (→ Charter 1).

## In-scope paths

- `database/activation.py`
- `database/schema.py` (`ActiveCustodyDayTable`)
- Override decide / activate paths in `api/router.py` and concierge commit
- `tests/test_active_day_backstop.py`
- Pending/Expired/Draft must not affect `calculate_schedule` inputs

## Must inspect

- Approving an override writes `active_custody_days` for every covered day in
  the same transaction as `is_active`.
- Two overlapping active ranges cannot both commit (409 / constraint).
- Deactivate/reject clears day rows; no orphan claims.
- Only `Approved` + `is_active` overrides reach the engine via schedule_reads.

## Out of scope

- SMS copy wording, passcode throttle, backup email delivery (unless activation
  rows are wrong).

## Forbidden conclusions

- “HTTP and SMS disagree” without proving bad writes — that is Charter 1.
- Soft-deleting the unique constraint “for simplicity” as an acceptable note.

## Eval (local only)

Branch: `DO-NOT-MERGE-eval-activation` — never push.

Revert `79ee715` (`active_custody_days` backstop) and its tests. Confirm
overlapping ranges can both go active again. Charter must rediscover the gap.

## Finding template

```
Claim:
Outcome: 1 or 2 (via wrong persisted schedule)
Location: path:line
Executable repro:
Expected:
Actual:
```

## Done when

≥1 gated finding, or written negative listing activation/overlap cases run.
