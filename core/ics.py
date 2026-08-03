"""Build RFC 5545-ish iCalendar documents for custody schedules."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from core.models import DailyCustodyState

PRODID = "-//Moser Custody Concierge//Custody Scheduler//EN"
CAL_NAME = "Custody Schedule"


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _format_dtstamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y%m%dT%H%M%SZ")


def build_custody_ics(
    *,
    days: list[DailyCustodyState],
    family_id: int,
    now: datetime | None = None,
) -> str:
    stamped = now if now is not None else datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CAL_NAME}",
    ]
    for day in days:
        lines.extend(_vevent_lines(day=day, family_id=family_id, stamped=stamped))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _vevent_lines(
    *,
    day: DailyCustodyState,
    family_id: int,
    stamped: datetime,
) -> list[str]:
    end = day.current_date + timedelta(days=1)
    uid = f"custody-{family_id}-{_format_date(day.current_date)}@custody-scheduler"
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_format_dtstamp(stamped)}",
        f"DTSTART;VALUE=DATE:{_format_date(day.current_date)}",
        f"DTEND;VALUE=DATE:{_format_date(end)}",
    ]
    if day.is_overridden and day.override_details is not None:
        details = day.override_details
        summary = (
            f"Custody: {day.final_parent.value} ({details.override_type.value})"
        )
        lines.append(f"SUMMARY:{escape_ics_text(summary)}")
        if details.description:
            lines.append(f"DESCRIPTION:{escape_ics_text(details.description)}")
    else:
        lines.append(
            f"SUMMARY:{escape_ics_text(f'Custody: {day.final_parent.value}')}"
        )
    lines.append("END:VEVENT")
    return lines
