# Charter 2 — Consent / authorization

**Outcome focus:** (2) Wrong assignment / unauthorized change.

**Owns:** Who may create, confirm, approve, or reject custody changes.

**Does not own:** Schedule math or civil-date clocks.

## In-scope paths

- `api/router.py` (create / decide override; role gates)
- `core/approvals.py`
- `core/handshake.py`, `concierge/nodes.py` (initiator / counterparty replies)
- `concierge/runner.py` (`ingest_and_dedupe` / unknown sender drop — via graph entry)
- `concierge/adapters.py` (`SqlSenderResolver`)
- Frontend: Viewer cannot open override form (`canRequestOverride`)

## Must inspect

- Requester cannot approve/reject their own pending override (API + domain).
- SMS: only the counterparty’s ACCEPT/DENY decides; initiator YES/NO only on
  their confirmation step; unrecognized replies **re-prompt**, they do not
  silently cancel or approve.
- Unknown phone numbers never receive custody detail and never mutate schedule.
- Viewer (and non-Parent) cannot create or decide overrides.

## Out of scope

- Engine segment lengths, ICS formatting, backup chain cryptography.

## Forbidden conclusions

- “Role is checked in the UI” without a server-side gate repro.
- Treating a clarification/re-prompt SMS as a consent decision.

## Eval (local only)

Branch: `DO-NOT-MERGE-eval-consent` — never push.

Surgically restore pre-hardening behavior where **any non-YES initiator reply
cancelled** the draft (before explicit vocabularies in `core/handshake.py` /
nodes). Remove covering cases in `tests/test_handshake_replies.py`. Do **not**
wholesale revert `68657fe` (it also added schedule queries).

Alternate class for re-validation after a miss: weaken API self-approval only
**if** `pytest` stays green with covering tests removed/adjusted — otherwise
pick another uncovered consent defect.

## Finding template

```
Claim:
Outcome: 2 wrong assignment / unauthorized change
Location: path:line
Executable repro:
Expected:
Actual:
```

## Done when

≥1 gated finding, or written negative listing gates exercised and commands run.
