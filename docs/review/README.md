# Custody-truth review campaign

Read [MAP.md](../../MAP.md) via [CLAUDE.md](../../CLAUDE.md) at the start of
every review session. Constrain attention with the **charter file** for this
conversation — do not mix charters in one context window.

## Meta-rule

Every finding must trace to one of:

1. **Divergent truths** — two surfaces disagree on who has the kids for the same civil day.
2. **Wrong assignment** — the wrong parent is told they have (or will have) the kids, or an unauthorized actor changes custody.

Crashes, style, and FastAPI purity are out of scope unless they cause (1) or (2).

## Repro gate

No `file:line` + **executable repro** → not a finding. Prefer a failing
pytest/vitest case. A multi-process or two-connection harness already used in
this repo also counts. Speculative notes go to a parking lot, not the report.

## Charters and hand-off

| # | File | Owns |
|---|------|------|
| 1 | [CHARTER_01_truth.md](CHARTER_01_truth.md) | Read-path agreement (HTTP / ICS / SMS / evidence archive) given a fixed DB |
| 2 | [CHARTER_02_consent.md](CHARTER_02_consent.md) | Who may change or confirm custody |
| 3 | [CHARTER_03_clock.md](CHARTER_03_clock.md) | Civil date vs UTC-naive instants |
| 4 | [CHARTER_04_activation.md](CHARTER_04_activation.md) | Write-path integrity (`active_custody_days`, activation) |

**Hand-off:** Charter 4 owns “wrong rows written.” Charter 1 owns “surfaces
disagree given the DB.” Do not double-report.

**Pass order (defect history):** 2 → 3 → 1 → 4.

## Finding template

```
Claim:
Outcome: (1 divergent truths | 2 wrong assignment)
Location: path:line
Executable repro: (test path or harness command)
Expected:
Actual:
```

## Done-condition (per charter session)

Either:

- ≥1 gated finding filed, or
- a **written negative**: checked X, Y, Z; commands run; no outcome-1/2 repro found.

## Eval seed (before trusting a clean report)

Do **not** plant synthetic bugs the suite already catches (self-approve,
UTC-tomorrow). Those only prove pytest.

**Primary eval:** on a **local-only** branch named `DO-NOT-MERGE-eval-<charter>`:

1. Revert the historical fix **and** its covering tests (see each charter’s
   “Eval” section).
2. Confirm the suite no longer fails solely because of those removed tests
   (the defect is uncovered).
3. Run that charter in a dedicated session — it must rediscover the defect
   with a new executable repro.
4. Never `git push` the eval branch. After the pass: check out elsewhere and
   `git branch -D DO-NOT-MERGE-eval-…`.

`master` is unprotected and merges auto-deploy — mechanical isolation, not
“please don’t merge.”

**Overfitting:** if a charter misses, tighten it, then re-validate with a
*different* defect in the same class — not the revert you just tuned against.

Campaign records (after eval / clean passes):
[EVAL_RESULTS.md](EVAL_RESULTS.md), [PASS_REPORTS.md](PASS_REPORTS.md).

## Optimization

Not part of this campaign. Only with measured evidence
([PERFORMANCE_AUDIT.md](../../PERFORMANCE_AUDIT.md) or a fresh profile).
