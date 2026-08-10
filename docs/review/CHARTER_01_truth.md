# Charter 1 — Truth consistency (read path)

**Outcome focus:** (1) Divergent truths.

**Owns:** Given a fixed DB, do HTTP schedule, ICS feed, SMS schedule answers,
and the evidence **archive/export** agree on who has the kids for a civil day?

**Does not own:** How rows got into the DB (→ [CHARTER_04_activation.md](CHARTER_04_activation.md)).

## In-scope paths

- `core/engine.py` (`calculate_schedule`)
- `database/schedule_reads.py`
- `api/router.py` (schedule GET, feed.ics, export)
- `concierge/repos.py` (`SqlScheduleReader`)
- `core/export.py`, `core/backup.py` (archive payload stating custody history)
- Agreement tests such as `tests/test_schedule_query_sms.py` (cross-surface)

## Must inspect

- Both HTTP and SMS load overrides/baseline only through `schedule_reads` (or
  prove any duplicate loader cannot drift).
- Same `family_id` + ISO date → same `final_parent` via HTTP JSON, ICS event
  summary/owner, and SMS `summarize_custody` / next-handoff facts.
- Export/archive custody days match `calculate_schedule` for a remembered week
  (no silent filter drift on notify-status or `is_active`).
- Highest-`id` override wins consistently across surfaces.

## Out of scope

- Perf, styling, Twilio transport, passcode auth (unless it causes divergent reads).

## Forbidden conclusions

- “They share a helper so they must agree” without an executable cross-surface
  repro or a written negative that ran one.
- Filing an activation/overlap bug here — hand off to Charter 4.

## Eval (local only)

Branch: `DO-NOT-MERGE-eval-truth` — never push.

Drift one surface’s loader (e.g. override filter / notify-status parsing) away
from `schedule_reads` **and** remove or skip the cross-surface agreement test
(`test_sms_answer_agrees_with_the_http_schedule`). Charter must rediscover
disagreement. Historical root: shared extraction in `68657fe`.

## Finding template

```
Claim:
Outcome: 1 divergent truths
Location: path:line
Executable repro:
Expected: (same final_parent / same day on surfaces A and B)
Actual:
```

## Done when

≥1 gated finding, or written negative listing surfaces compared and commands run.
