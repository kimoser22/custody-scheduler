from datetime import date
from core.models import (
    BaselineSchedule, 
    ScheduleOverride, 
    ParentRole, 
    OverrideType
)
from core.engine import calculate_schedule

def test_calculate_schedule_empty_range():
    # Setup baseline
    baseline = BaselineSchedule(
        epoch_start_date=date(2026, 1, 5), 
        starting_parent=ParentRole.PARENT_A
    )
    
    # End date is before start date
    target_start = date(2026, 1, 10)
    target_end = date(2026, 1, 5)
    
    result = calculate_schedule(baseline, [], target_start, target_end)
    
    # Engine should return an empty list safely without breaking
    assert result == []

def test_calculate_schedule_applies_holiday_override():
    baseline = BaselineSchedule(
        epoch_start_date=date(2026, 1, 5), # Monday
        starting_parent=ParentRole.PARENT_A
    )
    
    # Jan 5 and 6 would normally both belong to Parent A in the baseline
    target_start = date(2026, 1, 5)
    target_end = date(2026, 1, 6)
    
    # Create a holiday patch that gives Jan 6 to Parent B
    holiday_patch = ScheduleOverride(
        override_date=date(2026, 1, 6),
        assigned_parent=ParentRole.PARENT_B,
        override_type=OverrideType.HOLIDAY,
        description="Special Holiday",
        is_active=True
    )
    
    result = calculate_schedule(baseline, [holiday_patch], target_start, target_end)
    
    # Assert Day 1 (Jan 5) is untouched
    assert result[0].current_date == date(2026, 1, 5)
    assert result[0].baseline_parent == ParentRole.PARENT_A
    assert result[0].final_parent == ParentRole.PARENT_A
    assert result[0].is_overridden is False
    assert result[0].override_details is None

    # Assert Day 2 (Jan 6) applies the patch over the baseline
    assert result[1].current_date == date(2026, 1, 6)
    assert result[1].baseline_parent == ParentRole.PARENT_A # Still shows the underlying truth
    assert result[1].final_parent == ParentRole.PARENT_B # The override takes effect
    assert result[1].is_overridden is True
    assert result[1].override_details == holiday_patch


def test_calculate_schedule_override_collision_last_wins():
    """If multiple active overrides exist for the same day, the last one in the list wins."""
    baseline = BaselineSchedule(
        epoch_start_date=date(2026, 1, 5),
        starting_parent=ParentRole.PARENT_A,
    )

    target_date = date(2026, 1, 6)

    override_one = ScheduleOverride(
        override_date=target_date,
        assigned_parent=ParentRole.PARENT_B,
        override_type=OverrideType.HOLIDAY,
        description="First Override",
        is_active=True,
    )

    override_two = ScheduleOverride(
        override_date=target_date,
        assigned_parent=ParentRole.PARENT_A,
        override_type=OverrideType.MUTUAL_SWAP,
        description="Latest Mutual Swap",
        is_active=True,
    )

    result = calculate_schedule(
        baseline, [override_one, override_two], target_date, target_date
    )

    assert result[0].final_parent == ParentRole.PARENT_A
    assert result[0].is_overridden is True
    assert result[0].override_details == override_two


def test_calculate_schedule_leap_year_handling():
    """Enforce that 2-2-3 math handles Feb 29, 2028 seamlessly without drifting the rotation."""
    baseline = BaselineSchedule(
        epoch_start_date=date(2028, 1, 3),
        starting_parent=ParentRole.PARENT_A,
    )

    start_dt = date(2028, 2, 28)
    end_dt = date(2028, 3, 1)

    result = calculate_schedule(baseline, [], start_dt, end_dt)

    assert result[0].current_date == date(2028, 2, 28)
    assert result[0].final_parent == ParentRole.PARENT_A

    assert result[1].current_date == date(2028, 2, 29)
    assert result[1].final_parent == ParentRole.PARENT_A

    assert result[2].current_date == date(2028, 3, 1)
    assert result[2].final_parent == ParentRole.PARENT_B


def test_calculate_schedule_long_horizon_stability():
    """Ensure that calculating 5 years out doesn't drift or break performance."""
    baseline = BaselineSchedule(
        epoch_start_date=date(2026, 1, 5),
        starting_parent=ParentRole.PARENT_A,
    )

    target_date = date(2031, 1, 6)

    result = calculate_schedule(baseline, [], target_date, target_date)

    assert result[0].final_parent == ParentRole.PARENT_B
