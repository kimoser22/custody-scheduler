# Clean-tree charter passes (2 → 3 → 1 → 4)

Tree: `docs/architecture-map` @ charter docs commit; no eval plants.
Each pass is recorded as a **written negative** (no gated finding).
Commands shared across passes where noted.

Suite command (all covering tests green):

```
pytest tests/test_handshake_replies.py tests/test_approvals.py \
  tests/test_household_clock.py tests/test_sms_relative_dates.py \
  tests/test_schedule_query_sms.py tests/test_active_day_backstop.py -q
```

Result: **45 passed**.

---

## Pass Charter 2 — Consent (written negative)

Checked:

- `core/handshake.py` `parse_initiator_reply` — vocabularies; non-answers → `None`
- `concierge/nodes.py` initiator/counterparty reply nodes use parsers (no
  `startswith("YES")` cancel path)
- `core/approvals.py` + API decide path — self-approval blocked
  (`test_self_approval_is_blocked`)
- Unknown sender drop / no custody detail
  (`test_query_from_an_unknown_number_is_ignored`)
- Viewer / role gates exercised via approvals + API tests in suite above

Commands: suite above (handshake + approvals subsets).

Parking lot: none gated.

---

## Pass Charter 3 — Clock (written negative)

Checked:

- `core/clock.py` `household_today` / fail-loud unknown TZ
- `concierge/factory.py` parser gets `household_today(instant)`; `deps.now`
  stays UTC-naive
- ICS window + export filename use `household_today` in `api/router.py`
- Evening Eastern regression covered by `tests/test_sms_relative_dates.py`
- Frontend `localTodayDate` still browser-local (known MAP divergence) —
  **not escalated**: no executable outcome-2 repro of wrong parent assignment
  from that sticky alone in this pass

Commands: `test_household_clock.py`, `test_sms_relative_dates.py`.

---

## Pass Charter 1 — Truth (written negative)

Checked:

- HTTP schedule + ICS use `database/schedule_reads.load_*`
- SMS `SqlScheduleReader.custody_between` uses the same loaders
- Cross-surface guard:
  `tests/test_schedule_query_sms.py::test_sms_answer_agrees_with_the_http_schedule`
- Engine applies only `is_active` + `Approved`
- Export/archive path (`core/export.py` / backup) builds from schedule domain
  inputs — no alternate override filter found that would silently disagree on
  a civil day without going through the same engine rules

Commands: `test_schedule_query_sms.py` (+ suite).

---

## Pass Charter 4 — Activation (written negative)

Checked:

- `database/activation.activate_override` writes per-day
  `ActiveCustodyDayTable` rows in the same unit of work as `is_active`
- Concurrent race harness requires one `approved` + one `conflict`
- Deactivate clears day rows; boot backfill present in `main.ensure_active_day_rows`
- Pending/Draft do not feed schedule_reads (`is_active` filter)

Commands: `tests/test_active_day_backstop.py`.

---

## Triage

No gated findings on the clean tree. Historical-eval catches confirm the
charters can rediscover uncovered defects; fix PRs are only needed when a
clean-tree pass files a gated finding.
