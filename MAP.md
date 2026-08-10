# MAP — architecture orientation

Read before reviewing a diff or planning a change. This states the structure so
you spend budget on the change itself, not on re-deriving where things live.

```
Twilio POST ─▶ api/twilio_webhook.py ─▶ concierge/factory.build_default_runner
               (HMAC-SHA1, fail-closed)              │
                                    concierge/runner.LangGraphConciergeRunner
                                                     │
                          concierge/graph.py ─▶ concierge/repos.py ─▶ SQLite
Browser     ─▶ api/router.py (schedule · overrides · feed.ics · export)
               api/auth_router.py · api/me_router.py
GH cron     ─▶ api/backup_router.py  POST /api/v1/admin/backup-email
```

**The runner does four things before the graph** (`concierge/runner.py`):
`idempotency.claim(message_sid)` at the transport boundary (re-invoking the
graph on a used sid starts a *second conversation*, it does not dedupe);
STOP/HELP/START keywords, terminal and bypassing the graph; the opt-out gate;
then thread-registry lookup — open thread ⇒ `Command(resume=body)`, else a
fresh thread id.

```
ingest_and_dedupe ─▶ parse_intent ─┬─▶ answer_schedule_query ─▶ END   (read)
                                   ├─▶ END                            (unclear)
                                   └─▶ draft_confirmation_sms
                                          ⇅ interrupt · reprompt_initiator
                                        process_initiator_reply
                                          └─▶ send_proposal_to_counterparty
                                                 ⇅ interrupt · reprompt_counterparty
                                               process_counterparty_reply
                                                 └─▶ commit_transaction ─▶ notify
```

`ingest_and_dedupe` resolves the sender and **drops unknown numbers — that is
the authorization boundary**; nothing downstream re-checks it. Only the swap
path interrupts, so read/unclear branches cannot strand a thread. Unrecognized
YES/NO replies re-prompt (the cycles above) instead of deciding.

**Schedule resolution is one implementation, two surfaces.**
`core/engine.calculate_schedule` is pure: a 2-2-3 cycle (`_SEGMENT_LENGTHS`)
overlaid with active+approved overrides. Its inputs load through
`database/schedule_reads.py`, used by **both** `api/router.py` (HTTP + ICS) and
`concierge/repos.SqlScheduleReader` (SMS) — deliberately shared so the two
surfaces cannot answer differently.

**Handshake state is two durable halves on the same `custody.db`:** the paused
graph (SqliteSaver, `concierge/factory._checkpointer_for`) and phone→thread
routing (`handshake_threads` via `SqlThreadRegistry`). Both must survive a
restart or a reply cannot be routed back.

**Clock rule.** Instants — audit timestamps, `expires_at`, `decided_at`, leases
— are UTC-naive. Calendar dates ("what day is it") come from
`core/clock.household_today` (America/New_York). The frontend still uses
browser-local `localTodayDate`; that divergence is known and unfixed.

**Database.** SQLite on a Fly volume, **one machine / one writer**. `main.py`
lifespan runs `create_all` + `ensure_*_column` migrations + per-user seeding:
new *tables* need no migration helper, new *columns* do. Constraints carry
invariants — `active_custody_days (family_id, day)` is the no-overlap backstop;
`backup_records.backup_date` is unique to prevent both chain forks and
concurrent delivery attempts.

**Seams.** Protocols in `concierge/ports.py`, SQL adapters in
`concierge/repos.py`, wired in `api/dependencies.py`; tests swap fakes there.
Time is injected (`now=`) rather than read ambiently.
