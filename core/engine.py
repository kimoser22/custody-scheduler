from datetime import date, timedelta

from core.models import (
    BaselineSchedule,
    DailyCustodyState,
    ParentRole,
    ScheduleOverride,
)

_SEGMENT_LENGTHS = (2, 2, 3, 2, 2, 3)


def _other_parent(parent: ParentRole) -> ParentRole:
    if parent == ParentRole.PARENT_A:
        return ParentRole.PARENT_B
    return ParentRole.PARENT_A


def _baseline_parent_for_date(baseline: BaselineSchedule, target: date) -> ParentRole:
    offset = (target - baseline.epoch_start_date).days % 14
    other_parent = _other_parent(baseline.starting_parent)
    segment_parents = (
        baseline.starting_parent,
        other_parent,
        baseline.starting_parent,
        other_parent,
        baseline.starting_parent,
        other_parent,
    )

    cumulative = 0
    for length, parent in zip(_SEGMENT_LENGTHS, segment_parents, strict=True):
        if offset < cumulative + length:
            return parent
        cumulative += length

    raise RuntimeError("offset must fall within the 14-day custody cycle")


def calculate_schedule(
    baseline: BaselineSchedule,
    overrides: list[ScheduleOverride],
    start_date: date,
    end_date: date,
) -> list[DailyCustodyState]:
    if end_date < start_date:
        return []

    schedule: list[DailyCustodyState] = []
    current = start_date
    while current <= end_date:
        baseline_parent = _baseline_parent_for_date(baseline, current)

        matching_overrides = [
            override
            for override in overrides
            if override.is_active and override.override_date == current
        ]
        override = matching_overrides[-1] if matching_overrides else None

        if override is not None:
            schedule.append(
                DailyCustodyState(
                    current_date=current,
                    baseline_parent=baseline_parent,
                    final_parent=override.assigned_parent,
                    is_overridden=True,
                    override_details=override,
                )
            )
        else:
            schedule.append(
                DailyCustodyState(
                    current_date=current,
                    baseline_parent=baseline_parent,
                    final_parent=baseline_parent,
                    is_overridden=False,
                    override_details=None,
                )
            )

        current += timedelta(days=1)

    return schedule
