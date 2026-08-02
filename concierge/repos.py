from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from concierge.phones import normalize_phone
from concierge.ports import OverrideConflictError
from core.models import OverrideStatus, OverrideType, ParentRole, ScheduleOverride
from core.ranges import ranges_overlap
from database.schema import (
    AuditLogTable,
    HandshakeThreadTable,
    OverrideTable,
    SmsOptOutTable,
    TwilioIdempotencyTable,
)


def _to_domain(row: OverrideTable) -> ScheduleOverride:
    return ScheduleOverride(
        id=row.id,
        override_date=row.override_date,
        end_date=row.end_date,
        assigned_parent=ParentRole(row.assigned_parent),
        override_type=OverrideType(row.override_type),
        description=row.description,
        is_active=row.is_active,
        status=OverrideStatus(row.status),
        expires_at=row.expires_at,
        requested_by_user_id=row.requested_by_user_id,
    )


class SqlOverrideRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_draft(
        self,
        *,
        family_id: int,
        override_date,
        assigned_parent: ParentRole,
        override_type: OverrideType,
        description: str,
        requested_by_user_id: int,
        expires_at: datetime,
        end_date=None,
    ) -> ScheduleOverride:
        row = OverrideTable(
            family_id=family_id,
            override_date=override_date,
            end_date=end_date,
            assigned_parent=assigned_parent.value,
            override_type=override_type.value,
            description=description,
            is_active=False,
            status=OverrideStatus.DRAFT.value,
            requested_by_user_id=requested_by_user_id,
            expires_at=expires_at,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return _to_domain(row)

    def get(self, override_id: int) -> ScheduleOverride | None:
        row = self._session.get(OverrideTable, override_id)
        return _to_domain(row) if row else None

    def set_status(
        self,
        override_id: int,
        status: OverrideStatus,
        *,
        is_active: bool | None = None,
        decided_by_user_id: int | None = None,
        decided_at: datetime | None = None,
    ) -> ScheduleOverride:
        row = self._session.get(OverrideTable, override_id)
        if row is None:
            raise KeyError(override_id)
        row.status = status.value
        if is_active is not None:
            row.is_active = is_active
        if decided_by_user_id is not None:
            row.decided_by_user_id = decided_by_user_id
        if decided_at is not None:
            row.decided_at = decided_at
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return _to_domain(row)

    def activate_and_supersede(
        self,
        override_id: int,
        *,
        decided_by_user_id: int,
        decided_at: datetime,
    ) -> ScheduleOverride:
        row = self._session.get(OverrideTable, override_id)
        if row is None:
            raise KeyError(override_id)

        new_start = row.override_date
        new_end = row.end_date if row.end_date is not None else row.override_date
        existing_active = self._session.exec(
            select(OverrideTable).where(
                OverrideTable.family_id == row.family_id,
                OverrideTable.is_active.is_(True),
                OverrideTable.id != row.id,
            )
        ).all()
        for other in existing_active:
            other_end = other.end_date if other.end_date is not None else other.override_date
            if ranges_overlap(new_start, new_end, other.override_date, other_end):
                other.is_active = False
                self._session.add(other)

        row.status = OverrideStatus.APPROVED.value
        row.is_active = True
        row.decided_by_user_id = decided_by_user_id
        row.decided_at = decided_at
        self._session.add(row)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise OverrideConflictError(
                f"An active override already exists for family {row.family_id} "
                f"on {row.override_date}."
            ) from None
        self._session.refresh(row)
        return _to_domain(row)


class SqlThreadRegistry:
    """Durable phone -> open-thread mapping.

    Same interface as InMemoryThreadRegistry, backed by a table so a paused
    handshake can still be routed to its thread after a restart or deploy.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, phone: str) -> str | None:
        row = self._session.get(HandshakeThreadTable, phone)
        return row.thread_id if row else None

    def set(self, phone: str, thread_id: str) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row = self._session.get(HandshakeThreadTable, phone)
        if row is None:
            row = HandshakeThreadTable(
                phone=phone, thread_id=thread_id, updated_at=now
            )
        else:
            row.thread_id = thread_id
            row.updated_at = now
        self._session.add(row)
        self._session.commit()

    def clear(self, phone: str) -> None:
        row = self._session.get(HandshakeThreadTable, phone)
        if row is None:
            return
        self._session.delete(row)
        self._session.commit()


class SqlAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        *,
        family_id: int,
        actor_role: str,
        action_type: str,
        description: str,
        previous_state_id: int | None = None,
        timestamp: datetime,
    ) -> int:
        row = AuditLogTable(
            timestamp=timestamp,
            family_id=family_id,
            actor_role=actor_role,
            action_type=action_type,
            description=description,
            previous_state_id=previous_state_id,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        assert row.id is not None
        return row.id


class SqlIdempotencyStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def claim(self, message_sid: str) -> bool:
        self._session.add(TwilioIdempotencyTable(message_sid=message_sid))
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            return False
        return True


class SqlOptOutStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def is_opted_out(self, phone: str) -> bool:
        return self._session.get(SmsOptOutTable, normalize_phone(phone)) is not None

    def opt_out(self, phone: str) -> None:
        phone = normalize_phone(phone)
        if self.is_opted_out(phone):
            return
        self._session.add(
            SmsOptOutTable(
                phone=phone,
                opted_out_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        try:
            self._session.commit()
        except IntegrityError:
            # Concurrent STOP raced past the existence check; already opted out.
            self._session.rollback()

    def opt_in(self, phone: str) -> None:
        phone = normalize_phone(phone)
        row = self._session.get(SmsOptOutTable, phone)
        if row is None:
            return
        self._session.delete(row)
        self._session.commit()
