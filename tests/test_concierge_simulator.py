from datetime import date

from concierge.simulator import (
    INITIATOR_PHONE,
    THREAD_ID,
    build_simulator_stack,
    run_until_complete,
)
from core.models import OverrideStatus


def test_run_until_complete_happy_path() -> None:
    graph, deps, sms, session = build_simulator_stack()
    try:
        # Force a known parse outcome via initial body with ISO date + Parent B
        final = run_until_complete(
            graph,
            initial_state={
                "message_sid": "SM-sim-test-1",
                "inbound_from": INITIATOR_PHONE,
                "inbound_body": "swap 2026-07-08 to Parent B for trains",
            },
            resumes=["YES", "ACCEPT"],
            thread_id=THREAD_ID,
        )
        assert final.get("current_step") == "completed"
        override = deps.overrides.get(final["override_id"])
        assert override is not None
        assert override.status == OverrideStatus.APPROVED
        assert override.is_active is True
        assert override.override_date == date(2026, 7, 8)
        assert any("Confirmed" in body for _, body in sms.sent)
    finally:
        session.close()
