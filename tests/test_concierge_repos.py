from datetime import date, datetime, timedelta, timezone

from core.models import OverrideStatus, OverrideType, ParentRole
from concierge.ports import FakeIntentParser, FakeSmsGateway, ParsedIntent
from concierge.repos import SqlAuditRepository, SqlIdempotencyStore, SqlOverrideRepository
from database.schema import AuditLogTable
from sqlmodel import select


NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def test_create_draft_is_inactive(session_fixture) -> None:
    repo = SqlOverrideRepository(session_fixture)
    draft = repo.create_draft(
        family_id=1,
        override_date=date(2026, 7, 8),
        assigned_parent=ParentRole.PARENT_B,
        override_type=OverrideType.MUTUAL_SWAP,
        description="Trains",
        requested_by_user_id=101,
        expires_at=NOW + timedelta(hours=24),
    )
    assert draft.status == OverrideStatus.DRAFT
    assert draft.is_active is False
    assert draft.id is not None


def test_idempotency_claim_returns_false_on_duplicate(session_fixture) -> None:
    store = SqlIdempotencyStore(session_fixture)
    assert store.claim("SM1") is True
    assert store.claim("SM1") is False


def test_audit_append_links_previous_state(session_fixture) -> None:
    audit = SqlAuditRepository(session_fixture)
    first = audit.append(
        family_id=1,
        actor_role="Parent",
        action_type="draft_created",
        description="Created",
        previous_state_id=None,
        timestamp=NOW,
    )
    second = audit.append(
        family_id=1,
        actor_role="Parent",
        action_type="initiator_confirm",
        description="Confirmed",
        previous_state_id=first,
        timestamp=NOW,
    )
    row = session_fixture.exec(
        select(AuditLogTable).where(AuditLogTable.id == second)
    ).one()
    assert row.previous_state_id == first


def test_fake_sms_and_parser_record_behavior() -> None:
    sms = FakeSmsGateway()
    parser = FakeIntentParser(
        ParsedIntent(
            override_date=date(2026, 7, 8),
            assigned_parent=ParentRole.PARENT_B,
            reason="trains",
        )
    )
    intent = parser.parse("whatever")
    sms.send("+15551212", f"Swap {intent.override_date}")
    assert intent.assigned_parent == ParentRole.PARENT_B
    assert sms.sent == [("+15551212", "Swap 2026-07-08")]


def test_activate_range_supersedes_overlapping_active(session_fixture) -> None:
    """A newly approved range deactivates any active override that overlaps it."""
    repo = SqlOverrideRepository(session_fixture)
    first = repo.create_draft(
        family_id=1,
        override_date=date(2026, 7, 8),
        end_date=date(2026, 7, 10),
        assigned_parent=ParentRole.PARENT_B,
        override_type=OverrideType.MUTUAL_SWAP,
        description="First range",
        requested_by_user_id=101,
        expires_at=NOW + timedelta(hours=24),
    )
    repo.activate_and_supersede(
        first.id, decided_by_user_id=102, decided_at=NOW
    )

    second = repo.create_draft(
        family_id=1,
        override_date=date(2026, 7, 9),
        end_date=date(2026, 7, 11),
        assigned_parent=ParentRole.PARENT_A,
        override_type=OverrideType.HOLIDAY,
        description="Overlapping replacement",
        requested_by_user_id=101,
        expires_at=NOW + timedelta(hours=24),
    )
    activated = repo.activate_and_supersede(
        second.id, decided_by_user_id=102, decided_at=NOW
    )

    assert activated.is_active is True
    assert activated.end_date == date(2026, 7, 11)
    assert repo.get(first.id).is_active is False
