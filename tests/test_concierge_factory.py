from sqlmodel import Session

from concierge.factory import build_default_runner
from concierge.repos import SqlOverrideRepository
from core.models import OverrideStatus
from database.schema import FamilyLink, UserTable


def test_handshake_state_persists_across_separate_runner_builds(
    session_fixture: Session,
) -> None:
    """Regression test for the bug where FastAPI's Depends(get_concierge_runner)
    builds a brand-new LangGraphConciergeRunner (fresh in-memory checkpointer +
    thread registry) on every HTTP request, silently discarding a paused
    handshake between the initial SMS and the reply SMS. build_default_runner
    must share checkpoint/registry state across independently-constructed
    runner instances the way separate webhook requests do."""
    session_fixture.add(FamilyLink(id=999, family_name="Isolated Test Family"))
    session_fixture.add(
        UserTable(
            id=9001,
            family_id=999,
            role="Parent",
            phone="+19995550001",
            custody_label="Parent A",
        )
    )
    session_fixture.add(
        UserTable(
            id=9002,
            family_id=999,
            role="Parent",
            phone="+19995550002",
            custody_label="Parent B",
        )
    )
    session_fixture.commit()

    # Each call below mirrors one separate HTTP request: its own runner
    # instance, built fresh, exactly as api.twilio_webhook.get_concierge_runner
    # does via FastAPI's Depends.
    first = build_default_runner(session=session_fixture).handle_sms(
        message_sid="SM-fac-1", from_phone="+19995550001", body="swap please"
    )
    assert first["status"] == "waiting"

    second = build_default_runner(session=session_fixture).handle_sms(
        message_sid="SM-fac-2", from_phone="+19995550001", body="YES"
    )
    assert second["status"] == "waiting"

    third = build_default_runner(session=session_fixture).handle_sms(
        message_sid="SM-fac-3", from_phone="+19995550002", body="ACCEPT"
    )
    assert third["status"] == "ok"

    override_id = third["result"]["override_id"]
    override = SqlOverrideRepository(session_fixture).get(override_id)
    assert override is not None
    assert override.status == OverrideStatus.APPROVED
    assert override.is_active is True
