"""Relative dates over SMS ("tomorrow") must resolve in the household's timezone.

The parser is told what day it is, and it used to be told UTC's day. From 20:00
local in summer (19:00 in winter) UTC has already rolled over, so "swap
tomorrow" resolved one day late — silently, with both parents receiving a
confirmation SMS for a date neither asked for. That is 4-5 hours of every day,
and evenings are when parents actually text about tomorrow.

Relative dates are LLM-only (HeuristicIntentParser has no notion of "tomorrow"),
so this rides the path that was recently switched on.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session

import concierge.factory as factory_module
from concierge.adapters import HeuristicIntentParser
from concierge.factory import build_default_runner
from database.schema import FamilyLink, UserTable

EDT = timezone(timedelta(hours=-4))

# 21:30 on Wednesday the 12th in Arlington == 01:30 UTC on the 13th.
EVENING_LOCAL = datetime(2026, 8, 12, 21, 30, tzinfo=EDT)
EVENING_UTC = EVENING_LOCAL.astimezone(timezone.utc)


@pytest.fixture(name="family")
def _family(session_fixture: Session) -> None:
    session_fixture.add(FamilyLink(id=771, family_name="Timezone Family"))
    session_fixture.add(
        UserTable(
            id=7101,
            family_id=771,
            role="Parent",
            phone="+17715550001",
            custody_label="Parent A",
        )
    )
    session_fixture.add(
        UserTable(
            id=7102,
            family_id=771,
            role="Parent",
            phone="+17715550002",
            custody_label="Parent B",
        )
    )
    session_fixture.commit()


def test_parser_is_given_the_household_date_not_utcs(
    session_fixture: Session, family: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression guard for the actual bug. Captures what the factory hands
    the parser rather than reaching into parser internals."""
    captured: dict[str, date] = {}

    def spy(today: date) -> HeuristicIntentParser:
        captured["today"] = today
        return HeuristicIntentParser()

    monkeypatch.setattr(factory_module, "_build_parser", spy)

    build_default_runner(session=session_fixture, now=EVENING_UTC)

    assert EVENING_UTC.date() == date(2026, 8, 13)  # what it used to be told
    assert captured["today"] == date(2026, 8, 12)  # what it is actually


def test_stored_timestamps_are_still_utc(
    session_fixture: Session, family: None
) -> None:
    """Only the calendar date moved. Audit timestamps, expires_at and decided_at
    all flow from deps.now, and every one of them is an instant that must stay
    UTC-naive — localizing those would corrupt comparisons against rows already
    written."""
    runner = build_default_runner(session=session_fixture, now=EVENING_UTC)

    assert runner.deps.now == datetime(2026, 8, 13, 1, 30)
    assert runner.deps.now.tzinfo is None


def test_llm_prompt_carries_the_household_date(
    session_fixture: Session, family: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End of the wire: the date the LLM is actually told. Reads one private
    attribute because that is where the parser keeps it; the alternative is
    asserting nothing about the path that carries the bug."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-dummy")

    runner = build_default_runner(session=session_fixture, now=EVENING_UTC)

    assert runner.deps.parser.fallback._today == date(2026, 8, 12)


def test_midday_is_unchanged(
    session_fixture: Session, family: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Most of the day already worked, and must keep working."""
    captured: dict[str, date] = {}

    def spy(today: date) -> HeuristicIntentParser:
        captured["today"] = today
        return HeuristicIntentParser()

    monkeypatch.setattr(factory_module, "_build_parser", spy)

    midday = datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc)  # 12:00 EDT
    build_default_runner(session=session_fixture, now=midday)

    assert captured["today"] == date(2026, 8, 12)
