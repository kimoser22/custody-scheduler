# Historical eval results

Local-only `DO-NOT-MERGE-eval-*` branches. **Never pushed.** Deleted after each
pass. Plants were not committed.

| Charter | Branch | Plant | Tests stripped | Repro | Result |
|---------|--------|-------|----------------|-------|--------|
| 2 Consent | `DO-NOT-MERGE-eval-consent` | `concierge/nodes.py` `process_initiator_reply`: non-YES → NO | deleted `tests/test_handshake_replies.py` | mid-handshake `"when do I get them back?"` → must stay `awaiting_initiator_confirm` | **CATCH** — got `completed` (cancelled as NO) |
| 3 Clock | `DO-NOT-MERGE-eval-clock` | `concierge/factory.py` parser `today=deps_now.date()`; ICS/export UTC; removed clock covering tests | `test_household_clock.py`, `test_sms_relative_dates.py`, feed-window test | evening EDT 21:30 → parser must get Aug 12 not UTC Aug 13 | **CATCH** — got Aug 13 |
| 1 Truth | `DO-NOT-MERGE-eval-truth` | `SqlScheduleReader` force-activates all overrides; removed SMS/HTTP agreement test | `test_sms_answer_agrees_with_the_http_schedule` | inactive Parent-B override on baseline Parent-A day | **CATCH** — SMS Parent B vs HTTP Parent A |
| 4 Activation | `DO-NOT-MERGE-eval-activation` | `activate_override` skips `active_custody_days` inserts | deleted `tests/test_active_day_backstop.py` | concurrent overlapping approvals race harness | **CATCH** — both `approved` |

## Re-validation

Not required: no charter missed its historical class. (If a miss had occurred,
tighten the charter then re-validate with a *different* defect in the same
class.)
