from datetime import datetime, timedelta, timezone

import pytest

from core.approvals import ApprovalError, Decision, decide_override, find_expired_pending
from core.models import OverrideStatus

NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
NOT_EXPIRED = NOW + timedelta(hours=1)
ALREADY_EXPIRED = NOW - timedelta(hours=1)


def test_approve_by_other_parent_transitions_to_approved():
    result = decide_override(
        current_status=OverrideStatus.PENDING,
        requested_by_user_id=1,
        actor_user_id=2,
        decision=Decision.APPROVE,
        now=NOW,
        expires_at=NOT_EXPIRED,
    )
    assert result.ok
    assert result.new_status == OverrideStatus.APPROVED


def test_reject_by_other_parent_transitions_to_rejected():
    result = decide_override(
        current_status=OverrideStatus.PENDING,
        requested_by_user_id=1,
        actor_user_id=2,
        decision=Decision.REJECT,
        now=NOW,
        expires_at=NOT_EXPIRED,
    )
    assert result.ok
    assert result.new_status == OverrideStatus.REJECTED


def test_self_approval_is_blocked():
    result = decide_override(
        current_status=OverrideStatus.PENDING,
        requested_by_user_id=1,
        actor_user_id=1,
        decision=Decision.APPROVE,
        now=NOW,
        expires_at=NOT_EXPIRED,
    )
    assert result.error == ApprovalError.SELF_APPROVAL
    assert result.new_status == OverrideStatus.PENDING


@pytest.mark.parametrize(
    "status", [OverrideStatus.APPROVED, OverrideStatus.REJECTED, OverrideStatus.EXPIRED]
)
def test_deciding_an_already_decided_request_is_rejected(status):
    result = decide_override(
        current_status=status,
        requested_by_user_id=1,
        actor_user_id=2,
        decision=Decision.APPROVE,
        now=NOW,
        expires_at=NOT_EXPIRED,
    )
    assert result.error == ApprovalError.ALREADY_DECIDED
    assert result.new_status == status


def test_expired_request_cannot_be_approved():
    result = decide_override(
        current_status=OverrideStatus.PENDING,
        requested_by_user_id=1,
        actor_user_id=2,
        decision=Decision.APPROVE,
        now=NOW,
        expires_at=ALREADY_EXPIRED,
    )
    assert result.error == ApprovalError.EXPIRED
    assert result.new_status == OverrideStatus.EXPIRED


def test_expiry_check_takes_priority_over_self_approval():
    result = decide_override(
        current_status=OverrideStatus.PENDING,
        requested_by_user_id=1,
        actor_user_id=1,
        decision=Decision.APPROVE,
        now=NOW,
        expires_at=ALREADY_EXPIRED,
    )
    assert result.error == ApprovalError.EXPIRED


def test_expires_exactly_at_now_counts_as_expired():
    result = decide_override(
        current_status=OverrideStatus.PENDING,
        requested_by_user_id=1,
        actor_user_id=2,
        decision=Decision.APPROVE,
        now=NOW,
        expires_at=NOW,
    )
    assert result.error == ApprovalError.EXPIRED


def test_find_expired_pending_only_matches_pending_past_expiry():
    class Row:
        def __init__(self, id_, status, expires_at):
            self.id = id_
            self.status = status
            self.expires_at = expires_at

    rows = [
        Row(1, OverrideStatus.PENDING.value, ALREADY_EXPIRED),
        Row(2, OverrideStatus.PENDING.value, NOT_EXPIRED),
        Row(3, OverrideStatus.APPROVED.value, ALREADY_EXPIRED),
    ]

    expired = find_expired_pending(rows, NOW)

    assert [row.id for row in expired] == [1]
