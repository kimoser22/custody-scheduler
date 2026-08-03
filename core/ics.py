"""Build RFC 5545-ish iCalendar documents for custody schedules."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from core.models import DailyCustodyState

PRODID = "-//Moser Custody Concierge//Custody Scheduler//EN"
CAL_NAME = "Custody Schedule"


MAX_LINE_OCTETS = 75


def fold_ics_line(line: str, limit: int = MAX_LINE_OCTETS) -> str:
    """Fold a content line to RFC 5545's 75-octet limit.

    Continuation lines begin with a single space, which clients strip when
    unfolding. The limit is in *octets*, but breaks are taken on character
    boundaries — splitting a multi-byte UTF-8 sequence would corrupt the feed
    for any client that decodes it. A parent's free-text override description
    is user-controlled, so long lines are routine rather than exceptional.
    """
    if len(line.encode("utf-8")) <= limit:
        return line

    chunks: list[str] = []
    current: list[str] = []
    current_octets = 0
    # Continuation lines spend one octet on their leading space.
    budget = limit

    for character in line:
        octets = len(character.encode("utf-8"))
        if current_octets + octets > budget:
            chunks.append("".join(current))
            current = [character]
            current_octets = octets
            budget = limit - 1
        else:
            current.append(character)
            current_octets += octets

    if current:
        chunks.append("".join(current))
    return "\r\n ".join(chunks)


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
    return "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n"


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
