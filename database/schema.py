from datetime import date, datetime

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class FamilyLink(SQLModel, table=True):
    __tablename__ = "family_links"

    id: int | None = Field(default=None, primary_key=True)
    family_name: str


class UserTable(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    family_id: int = Field(foreign_key="family_links.id")
    role: str
    phone: str | None = None
    custody_label: str | None = None


class BaselineTable(SQLModel, table=True):
    __tablename__ = "baselines"

    id: int | None = Field(default=None, primary_key=True)
    family_id: int = Field(foreign_key="family_links.id")
    epoch_start_date: date
    starting_parent: str


class OverrideTable(SQLModel, table=True):
    __tablename__ = "overrides"
    __table_args__ = (
        Index(
            "ix_overrides_one_active_per_date",
            "family_id",
            "override_date",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    family_id: int = Field(foreign_key="family_links.id")
    override_date: date
    assigned_parent: str
    override_type: str
    description: str
    is_active: bool = False
    status: str = "Pending"
    requested_by_user_id: int
    decided_by_user_id: int | None = None
    decided_at: datetime | None = None
    expires_at: datetime


class AuditLogTable(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime
    family_id: int = Field(foreign_key="family_links.id")
    actor_role: str
    action_type: str
    description: str
    previous_state_id: int | None = None


class TwilioIdempotencyTable(SQLModel, table=True):
    __tablename__ = "twilio_idempotency"

    id: int | None = Field(default=None, primary_key=True)
    message_sid: str = Field(unique=True, index=True)