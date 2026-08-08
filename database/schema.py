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
    passcode_hash: str | None = None
    # Nullable so existing rows stay valid; ensure_user_email_column() adds the
    # column in place on databases created before it existed.
    email: str | None = None
    # Opaque subscribe token for GET /schedule/feed.ics?token=… Unique when set.
    calendar_feed_token: str | None = Field(
        default=None, unique=True, index=True
    )


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
    # Inclusive end; NULL means single-day (same as override_date).
    end_date: date | None = None
    assigned_parent: str
    override_type: str
    description: str
    is_active: bool = False
    status: str = "Pending"
    requested_by_user_id: int
    decided_by_user_id: int | None = None
    decided_at: datetime | None = None
    expires_at: datetime
    # Counterparty notify outcomes for the create-path ping (nullable legacy).
    email_notify_status: str | None = None
    sms_notify_status: str | None = None


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


class ActiveCustodyDayTable(SQLModel, table=True):
    """One row per day covered by an active override.

    The composite primary key (family_id, day) IS the no-overlap constraint
    that ix_overrides_one_active_per_date lost when overrides grew end_date:
    two ranges can overlap without sharing a start date, but they cannot both
    claim the same day here. Rows exist iff the override is active — written
    and cleared inside the same transaction as the is_active flip
    (database/activation.py).
    """

    __tablename__ = "active_custody_days"

    family_id: int = Field(primary_key=True)
    day: date = Field(primary_key=True)
    override_id: int = Field(index=True)  # index for deactivation deletes


class HandshakeThreadTable(SQLModel, table=True):
    """Maps a phone number to the LangGraph thread awaiting its reply.

    Durable half of the in-flight handshake state: the checkpointer holds the
    paused graph, this says which conversation a given number owes a reply to.
    Both must survive a restart or the reply cannot be routed back.
    """

    __tablename__ = "handshake_threads"

    phone: str = Field(primary_key=True)
    thread_id: str
    updated_at: datetime


class SmsOptOutTable(SQLModel, table=True):
    """Phones that replied STOP — suppress all outbound scheduling SMS."""

    __tablename__ = "sms_opt_outs"

    phone: str = Field(primary_key=True)
    opted_out_at: datetime


class LoginAttemptTable(SQLModel, table=True):
    """Consecutive failed passcode attempts, and the lock they earned.

    On disk rather than in a dict because this app redeploys on every merge to
    master: a process-local counter hands an attacker a clean slate for free,
    several times a week. Rows exist only while a user has failures to their
    name — a success or an expired lock deletes the row.

    No foreign key to users: unknown user ids are counted too (api/auth_router),
    or probing for which ids exist would be an unthrottled oracle.
    """

    __tablename__ = "login_attempts"

    user_id: int = Field(primary_key=True)
    failure_count: int = 0
    locked_until: datetime | None = None
