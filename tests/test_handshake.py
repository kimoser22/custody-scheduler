from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

from core.handshake import HandshakeError, InitiatorDecision, apply_initiator_confirm
from core.models import (
    BaselineSchedule,
    OverrideStatus,
    OverrideType,
    ParentRole,
    ScheduleOverride,
)
from core.engine import calculate_schedule
from database.schema import AuditLogTable, TwilioIdempotencyTable


NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)


NOT_EXPIRED = NOW.replace(tzinfo=None) + timedelta(hours=1)
ALREADY_EXPIRED = NOW.replace(tzinfo=None) - timedelta(hours=1)


def test_initiator_confirm_moves_draft_to_pending():
    result = apply_initiator_confirm(
        current_status=OverrideStatus.DRAFT,
        decision=InitiatorDecision.YES,
        now=NOW.replace(tzinfo=None),
        expires_at=NOT_EXPIRED,
    )
    assert result.ok
    assert result.new_status == OverrideStatus.PENDING
    assert result.is_active is False


def test_initiator_cancel_moves_draft_to_rejected():
    result = apply_initiator_confirm(
        current_status=OverrideStatus.DRAFT,
        decision=InitiatorDecision.NO,
        now=NOW.replace(tzinfo=None),
        expires_at=NOT_EXPIRED,
    )
    assert result.ok
    assert result.new_status == OverrideStatus.REJECTED
    assert result.is_active is False


def test_initiator_confirm_rejects_non_draft():
    result = apply_initiator_confirm(
        current_status=OverrideStatus.PENDING,
        decision=InitiatorDecision.YES,
        now=NOW.replace(tzinfo=None),
        expires_at=NOT_EXPIRED,
    )
    assert result.error == HandshakeError.NOT_DRAFT
    assert result.new_status == OverrideStatus.PENDING


def test_initiator_confirm_rejects_expired_draft():
    result = apply_initiator_confirm(
        current_status=OverrideStatus.DRAFT,
        decision=InitiatorDecision.YES,
        now=NOW.replace(tzinfo=None),
        expires_at=ALREADY_EXPIRED,
    )
    assert result.error == HandshakeError.EXPIRED
    assert result.new_status == OverrideStatus.EXPIRED


@pytest.mark.parametrize(
    "status",
    [OverrideStatus.DRAFT, OverrideStatus.PENDING, OverrideStatus.REJECTED],
)
def test_engine_ignores_non_approved_even_if_incorrectly_active(status):
    baseline = BaselineSchedule(
        epoch_start_date=date(2026, 1, 5),
        starting_parent=ParentRole.PARENT_A,
    )
    leaky = ScheduleOverride(
        override_date=date(2026, 1, 6),
        assigned_parent=ParentRole.PARENT_B,
        override_type=OverrideType.HOLIDAY,
        description="Should not apply",
        is_active=True,
        status=status,
    )
    result = calculate_schedule(
        baseline, [leaky], date(2026, 1, 6), date(2026, 1, 6)
    )
    assert result[0].final_parent == ParentRole.PARENT_A
    assert result[0].is_overridden is False


def test_audit_log_table_persists_rows(session_fixture: Session) -> None:
    row = AuditLogTable(
        timestamp=NOW.replace(tzinfo=None),
        family_id=1,
        actor_role="Parent",
        action_type="initiator_confirm",
        description="Draft confirmed",
        previous_state_id=None,
    )
    session_fixture.add(row)
    session_fixture.commit()
    session_fixture.refresh(row)

    stored = session_fixture.get(AuditLogTable, row.id)
    assert stored is not None
    assert stored.action_type == "initiator_confirm"
    assert stored.family_id == 1


def test_twilio_idempotency_rejects_duplicate_message_sid(
    session_fixture: Session,
) -> None:
    session_fixture.add(TwilioIdempotencyTable(message_sid="SMabc123"))
    session_fixture.commit()

    session_fixture.add(TwilioIdempotencyTable(message_sid="SMabc123"))
    with pytest.raises(IntegrityError):
        session_fixture.commit()
    session_fixture.rollback()

    rows = session_fixture.exec(select(TwilioIdempotencyTable)).all()
    assert len(rows) == 1
