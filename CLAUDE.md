# custody-scheduler

A 2-2-3 custody calendar for one family: FastAPI + SQLModel on SQLite (Fly
volume), Next.js frontend on Vercel, and an SMS concierge over Twilio.

The architecture map below is imported so every session — reviews, planning,
implementation — starts already knowing the structure instead of re-deriving it.

@MAP.md

## Working conventions

- **TDD, red first.** Write the failing test, watch it fail, then implement.
  A test written after the fact is not evidence until it has been seen to fail
  — verify by reverting the implementation if that is in doubt.
- **Verify against production shape.** Boot the real app via `TestClient`
  lifespan against a file-backed DB for anything touching migrations,
  durability, or delivery. Multi-process proofs for anything claiming to
  survive a restart.
- **Fail closed and loudly.** Unconfigured secrets refuse (503) rather than
  defaulting; ambiguous SMS asks for clarification rather than guessing a
  custody handoff; an unrecognized reply re-prompts rather than deciding.
- **Comments explain why, not what** — especially the non-obvious constraint a
  future reader would otherwise "simplify" away.
- Run `pytest tests/` and `npx vitest run` (in `frontend/`) before pushing; CI
  gates the deploy on both.
