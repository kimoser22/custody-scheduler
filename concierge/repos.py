from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from concierge.ports import OverrideConflictError
from core.models import OverrideStatus, OverrideType, ParentRole, ScheduleOverride
from database.schema import AuditLogTable, OverrideTable, TwilioIdempotencyTable


def _to_domain(row: OverrideTable) -> ScheduleOverride:
    return ScheduleOverride(
        id=row.id,
        override_date=row.override_date,
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
    ) -> ScheduleOverride:
        row = OverrideTable(
            family_id=family_id,
            override_date=override_date,
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

        existing_active = self._session.exec(
            select(OverrideTable).where(
                OverrideTable.family_id == row.family_id,
                OverrideTable.override_date == row.override_date,
                OverrideTable.is_active.is_(True),
                OverrideTable.id != row.id,
            )
        ).all()
        for other in existing_active:
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
