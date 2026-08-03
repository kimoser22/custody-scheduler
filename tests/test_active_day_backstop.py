"""Database-level backstop for overlapping active overrides.

The partial unique index on (family_id, override_date) lost its coverage when
overrides grew ranges: 08-01→08-10 and 08-05→08-15 overlap on six days but
never collide on start date. The supersede logic is a read-then-write, so two
concurrent approvals could both commit — and the calendar would show the wrong
parent on some days, undiagnosably.

active_custody_days restores the invariant structurally: one row per active
day, composite primary key (family_id, day). The race test here is the point
of the file — pre-fix, both approvals commit.
"""

import logging
import threading
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

import database.activation as activation_module
from api.dependencies import get_current_user
from concierge.ports import OverrideConflictError
from concierge.repos import SqlOverrideRepository
from core.models import OverrideStatus
from database.schema import (
    ActiveCustodyDayTable,
    FamilyLink,
    OverrideTable,
    UserTable,
)
from main import app, ensure_active_day_rows

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
EXPIRES = datetime(2026, 12, 31, 23, 59)


def _pending_override(
    *, start: date, end: date | None = None, description: str = "swap"
) -> OverrideTable:
    return OverrideTable(
        family_id=1,
        override_date=start,
        end_date=end,
        assigned_parent="Parent B",
        override_type="Mutual Swap",
        description=description,
        is_active=False,
        status=OverrideStatus.PENDING.value,
        requested_by_user_id=101,
        expires_at=EXPIRES,
    )


@pytest.fixture(name="file_engine")
def _file_engine(tmp_path):
    """File-backed DB so separate sessions/threads see each other's commits."""
    engine = create_engine(
        f"sqlite:///{tmp_path.as_posix()}/backstop.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(FamilyLink(id=1, family_name="Backstop Family"))
        session.commit()
    return engine


def _day_rows(session: Session) -> list[ActiveCustodyDayTable]:
    return list(session.exec(select(ActiveCustodyDayTable)).all())


# --- 1. the constraint primitive ----------------------------------------------


def test_overlapping_day_rows_collide_at_the_database(file_engine) -> None:
    """No app code involved: the composite primary key alone must reject a
    second override claiming a day that is already actively claimed."""
    with Session(file_engine) as session:
        for day in (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)):
            session.add(
                ActiveCustodyDayTable(family_id=1, day=day, override_id=11)
            )
        session.commit()

    with Session(file_engine) as session:
        session.add(
            ActiveCustodyDayTable(family_id=1, day=date(2026, 8, 3), override_id=22)
        )
        with pytest.raises(IntegrityError):
            session.commit()


# --- 2. the race, deterministically -------------------------------------------


def test_concurrent_overlapping_approvals_cannot_both_win(
    file_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two approvals read the active set before either commits (forced with a
    barrier at the read seam), then both write. Exactly one may win; the loser
    gets the conflict both paths already translate. Pre-fix, both committed."""
    with Session(file_engine) as session:
        override_a = _pending_override(
            start=date(2026, 8, 1), end=date(2026, 8, 10), description="A"
        )
        override_b = _pending_override(
            start=date(2026, 8, 5), end=date(2026, 8, 15), description="B"
        )
        session.add(override_a)
        session.add(override_b)
        session.commit()
        ids = (override_a.id, override_b.id)

    barrier = threading.Barrier(2, timeout=10)
    original_read = activation_module._overlapping_actives

    def read_then_rendezvous(*args, **kwargs):
        result = original_read(*args, **kwargs)
        barrier.wait()  # both threads now hold a stale view
        return result

    monkeypatch.setattr(
        activation_module, "_overlapping_actives", read_then_rendezvous
    )

    outcomes: dict[int, str] = {}

    def approve(override_id: int, decider: int) -> None:
        with Session(file_engine) as session:
            try:
                SqlOverrideRepository(session).activate_and_supersede(
                    override_id, decided_by_user_id=decider, decided_at=NOW
                )
                outcomes[override_id] = "approved"
            except OverrideConflictError:
                outcomes[override_id] = "conflict"

    threads = [
        threading.Thread(target=approve, args=(ids[0], 102)),
        threading.Thread(target=approve, args=(ids[1], 101)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes.values()) == ["approved", "conflict"]

    with Session(file_engine) as session:
        active = session.exec(
            select(OverrideTable).where(OverrideTable.is_active.is_(True))
        ).all()
        assert len(active) == 1
        winner = active[0]
        day_rows = _day_rows(session)
        # Day rows belong to exactly the winner, one per day, no duplicates.
        assert {row.override_id for row in day_rows} == {winner.id}
        days = [row.day for row in day_rows]
        assert len(days) == len(set(days))


# --- 3 & 4. day rows stay in sync with is_active -------------------------------


def test_activation_writes_one_row_per_day(file_engine) -> None:
    with Session(file_engine) as session:
        row = _pending_override(start=date(2026, 8, 1), end=date(2026, 8, 3))
        session.add(row)
        session.commit()

        SqlOverrideRepository(session).activate_and_supersede(
            row.id, decided_by_user_id=102, decided_at=NOW
        )

        day_rows = _day_rows(session)
        assert [r.day for r in day_rows] == [
            date(2026, 8, 1),
            date(2026, 8, 2),
            date(2026, 8, 3),
        ]
        assert {r.override_id for r in day_rows} == {row.id}


def test_single_day_override_writes_one_row(file_engine) -> None:
    with Session(file_engine) as session:
        row = _pending_override(start=date(2026, 8, 7))
        session.add(row)
        session.commit()

        SqlOverrideRepository(session).activate_and_supersede(
            row.id, decided_by_user_id=102, decided_at=NOW
        )
        assert [r.day for r in _day_rows(session)] == [date(2026, 8, 7)]


def test_supersede_removes_the_losers_day_rows(file_engine) -> None:
    """The winner's rows replace the loser's entirely — no orphans, or the
    constraint would block legitimate future approvals on those days."""
    with Session(file_engine) as session:
        first = _pending_override(start=date(2026, 8, 1), end=date(2026, 8, 10))
        session.add(first)
        session.commit()
        repo = SqlOverrideRepository(session)
        repo.activate_and_supersede(first.id, decided_by_user_id=102, decided_at=NOW)

        second = _pending_override(start=date(2026, 8, 5), end=date(2026, 8, 15))
        session.add(second)
        session.commit()
        repo.activate_and_supersede(second.id, decided_by_user_id=102, decided_at=NOW)

        session.refresh(first)
        assert first.is_active is False
        day_rows = _day_rows(session)
        assert {r.override_id for r in day_rows} == {second.id}
        assert len(day_rows) == 11  # 08-05..08-15 inclusive


# --- 7. deactivation via set_status clears day rows ----------------------------


def test_set_status_inactive_clears_day_rows(file_engine) -> None:
    with Session(file_engine) as session:
        row = _pending_override(start=date(2026, 8, 1), end=date(2026, 8, 2))
        session.add(row)
        session.commit()
        repo = SqlOverrideRepository(session)
        repo.activate_and_supersede(row.id, decided_by_user_id=102, decided_at=NOW)
        assert len(_day_rows(session)) == 2

        repo.set_status(row.id, OverrideStatus.REJECTED, is_active=False)
        assert _day_rows(session) == []


def test_set_status_inactive_is_noop_for_never_active(file_engine) -> None:
    with Session(file_engine) as session:
        row = _pending_override(start=date(2026, 8, 1))
        session.add(row)
        session.commit()
        SqlOverrideRepository(session).set_status(
            row.id, OverrideStatus.EXPIRED, is_active=False
        )  # must not raise; no day rows existed
        assert _day_rows(session) == []


# --- 8. boot backfill ----------------------------------------------------------


def _approved_active(
    *, start: date, end: date | None = None, description: str = "existing"
) -> OverrideTable:
    row = _pending_override(start=start, end=end, description=description)
    row.status = OverrideStatus.APPROVED.value
    row.is_active = True
    return row


def test_backfill_populates_day_rows_for_active_overrides(file_engine) -> None:
    """A volume upgraded in place has active overrides but an empty day table;
    boot must reconstruct the rows or the constraint guards nothing."""
    with Session(file_engine) as session:
        session.add(_approved_active(start=date(2026, 8, 1), end=date(2026, 8, 3)))
        session.commit()

    ensure_active_day_rows(file_engine)

    with Session(file_engine) as session:
        assert len(_day_rows(session)) == 3

    ensure_active_day_rows(file_engine)  # idempotent
    with Session(file_engine) as session:
        assert len(_day_rows(session)) == 3


def test_backfill_survives_preexisting_overlap_and_warns(
    file_engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Overlapping actives created before this fix must not brick the boot —
    surface them loudly and keep the first claimant."""
    with Session(file_engine) as session:
        session.add(
            _approved_active(start=date(2026, 8, 1), end=date(2026, 8, 10))
        )
        session.add(
            _approved_active(start=date(2026, 8, 5), end=date(2026, 8, 15))
        )
        session.commit()

    with caplog.at_level(logging.WARNING):
        ensure_active_day_rows(file_engine)  # must not raise

    assert any("overlap" in record.getMessage().lower() for record in caplog.records)
    with Session(file_engine) as session:
        days = [row.day for row in _day_rows(session)]
        assert len(days) == len(set(days))  # each day claimed exactly once


# --- 5. web path: normal supersede unchanged; conflict gets the new message ----


def _act_as(user: UserTable) -> None:
    async def override() -> UserTable:
        return user

    app.dependency_overrides[get_current_user] = override


def test_web_range_overlap_supersedes_normally(
    client_fixture, session_fixture, mock_parent, mock_other_parent
) -> None:
    """The everyday (non-racing) case must behave exactly as before: the new
    approval wins, the old one is superseded, 200 all the way."""
    _act_as(mock_parent)
    first = client_fixture.post(
        "/api/v1/schedule/overrides",
        json={
            "override_date": "2026-08-01",
            "end_date": "2026-08-10",
            "assigned_parent": "Parent B",
            "override_type": "Mutual Swap",
            "description": "first block",
        },
    ).json()
    _act_as(mock_other_parent)
    assert (
        client_fixture.post(
            f"/api/v1/schedule/overrides/{first['id']}/decision",
            json={"approve": True},
        ).status_code
        == 200
    )

    _act_as(mock_parent)
    second = client_fixture.post(
        "/api/v1/schedule/overrides",
        json={
            "override_date": "2026-08-05",
            "end_date": "2026-08-15",
            "assigned_parent": "Parent A",
            "override_type": "Holiday",
            "description": "overlapping block",
        },
    ).json()
    _act_as(mock_other_parent)
    decision = client_fixture.post(
        f"/api/v1/schedule/overrides/{second['id']}/decision",
        json={"approve": True},
    )

    assert decision.status_code == 200
    day_rows = _day_rows(session_fixture)
    assert {r.override_id for r in day_rows} == {second["id"]}
    assert len(day_rows) == 11


def test_web_conflict_returns_409_with_accurate_message(
    client_fixture, session_fixture, mock_parent, mock_other_parent
) -> None:
    """A day already claimed at commit time (the race remnant) must 409 with a
    message that is true under the range constraint, not the old index."""
    session_fixture.add(
        ActiveCustodyDayTable(family_id=1, day=date(2026, 8, 7), override_id=999)
    )
    session_fixture.commit()

    _act_as(mock_parent)
    pending = client_fixture.post(
        "/api/v1/schedule/overrides",
        json={
            "override_date": "2026-08-07",
            "assigned_parent": "Parent B",
            "override_type": "Mutual Swap",
            "description": "racing request",
        },
    ).json()
    _act_as(mock_other_parent)
    decision = client_fixture.post(
        f"/api/v1/schedule/overrides/{pending['id']}/decision",
        json={"approve": True},
    )

    assert decision.status_code == 409
    assert (
        decision.json()["detail"]
        == "Conflicts with an override that was just approved by another request."
    )
