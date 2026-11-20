"""Unit tests for alarm_tui.sleep."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from alarm_tui.sleep import (
    AlarmMode,
    apply_bedtime_check,
    calculate_cycles_wake_time,
    calculate_exact_wake_time,
    create_cycles_plan,
    create_exact_plan,
    create_snooze_plan,
    format_countdown,
    is_alarm_due,
    is_bedtime_check_due,
    time_remaining,
)


def test_calculate_cycles_wake_time_default_and_custom() -> None:
    now = datetime(2026, 11, 20, 23, 0, 0)
    # 5 * 90m (450m = 7h30m) + 15m = 7h45m -> 06:45 next day
    target = calculate_cycles_wake_time(now, cycles=5, cycle_minutes=90, fall_asleep_minutes=15)
    assert target == datetime(2026, 11, 21, 6, 45, 0)

    # 0 fall-asleep minutes, custom 80-minute cycle
    target_zero = calculate_cycles_wake_time(now, cycles=3, cycle_minutes=80, fall_asleep_minutes=0)
    assert target_zero == datetime(2026, 11, 21, 3, 0, 0)


def test_calculate_cycles_wake_time_validation() -> None:
    now = datetime(2026, 11, 20, 23, 0, 0)
    with pytest.raises(ValueError):
        calculate_cycles_wake_time(now, cycles=0)
    with pytest.raises(ValueError):
        calculate_cycles_wake_time(now, cycles=3, cycle_minutes=0)
    with pytest.raises(ValueError):
        calculate_cycles_wake_time(now, cycles=3, fall_asleep_minutes=-5)


def test_calculate_exact_wake_time_today_and_tomorrow_rollover() -> None:
    now = datetime(2026, 11, 20, 10, 30, 15)

    # Later today
    target_today, is_tomorrow = calculate_exact_wake_time(now, hour=14, minute=45)
    assert target_today == datetime(2026, 11, 20, 14, 45, 0)
    assert is_tomorrow is False

    # Already passed today -> tomorrow
    target_past, is_tomorrow_past = calculate_exact_wake_time(now, hour=7, minute=15)
    assert target_past == datetime(2026, 11, 21, 7, 15, 0)
    assert is_tomorrow_past is True

    # Exact current HH:MM with seconds past -> tomorrow
    target_same, is_tomorrow_same = calculate_exact_wake_time(now, hour=10, minute=30)
    assert target_same == datetime(2026, 11, 21, 10, 30, 0)
    assert is_tomorrow_same is True


def test_calculate_exact_wake_time_validation() -> None:
    now = datetime(2026, 11, 20, 10, 30, 0)
    with pytest.raises(ValueError):
        calculate_exact_wake_time(now, hour=24, minute=0)
    with pytest.raises(ValueError):
        calculate_exact_wake_time(now, hour=7, minute=60)


def test_bedtime_check_due_confirm_and_shift() -> None:
    start = datetime(2026, 11, 20, 23, 0, 0)
    plan = create_cycles_plan(
        cycles=5,
        cycle_minutes=90,
        fall_asleep_minutes=15,
        bedtime_check_enabled=True,
        bedtime_check_delay_minutes=15,
        bedtime_shift_minutes=15,
        now=start,
    )
    assert plan.mode == AlarmMode.CYCLES
    assert plan.target_time == datetime(2026, 11, 21, 6, 45, 0)
    assert plan.next_bedtime_check == datetime(2026, 11, 20, 23, 15, 0)

    # Before 23:15 -> not due yet
    assert is_bedtime_check_due(plan, now=datetime(2026, 11, 20, 23, 14, 59)) is False
    # At 23:15 -> due
    assert is_bedtime_check_due(plan, now=datetime(2026, 11, 20, 23, 15, 0)) is True

    # Answer "No" -> shifts target by +15m and schedules next check at now + 15m
    check_time = datetime(2026, 11, 20, 23, 15, 0)
    shifted = apply_bedtime_check(plan, went_to_sleep=False, now=check_time)
    assert shifted.target_time == datetime(2026, 11, 21, 7, 0, 0)
    assert shifted.shifts_count == 1
    assert shifted.bedtime_confirmed is False
    assert shifted.next_bedtime_check == datetime(2026, 11, 20, 23, 30, 0)
    assert is_bedtime_check_due(shifted, now=datetime(2026, 11, 20, 23, 29, 0)) is False
    assert is_bedtime_check_due(shifted, now=datetime(2026, 11, 20, 23, 30, 0)) is True

    # Answer "No" a second time -> shifts another +15m
    shifted_twice = apply_bedtime_check(
        shifted, went_to_sleep=False, now=datetime(2026, 11, 20, 23, 30, 0)
    )
    assert shifted_twice.target_time == datetime(2026, 11, 21, 7, 15, 0)
    assert shifted_twice.shifts_count == 2
    assert shifted_twice.next_bedtime_check == datetime(2026, 11, 20, 23, 45, 0)

    # Answer "Yes" -> confirms bedtime and disables further checks
    confirmed = apply_bedtime_check(
        shifted_twice, went_to_sleep=True, now=datetime(2026, 11, 20, 23, 45, 0)
    )
    assert confirmed.bedtime_confirmed is True
    assert confirmed.next_bedtime_check is None
    assert confirmed.target_time == datetime(2026, 11, 21, 7, 15, 0)
    assert is_bedtime_check_due(confirmed, now=datetime(2026, 11, 21, 0, 0, 0)) is False


def test_create_snooze_plan() -> None:
    base_now = datetime(2026, 11, 20, 7, 30, 0)
    plan = create_exact_plan(hour=7, minute=30, now=base_now - timedelta(hours=8))
    snoozed = create_snooze_plan(plan, snooze_minutes=5, now=base_now)

    assert snoozed.target_time == datetime(2026, 11, 20, 7, 35, 0)
    assert snoozed.started_at == base_now
    assert snoozed.bedtime_confirmed is True
    assert snoozed.next_bedtime_check is None
    assert is_alarm_due(snoozed.target_time, now=datetime(2026, 11, 20, 7, 34, 59)) is False
    assert is_alarm_due(snoozed.target_time, now=datetime(2026, 11, 20, 7, 35, 0)) is True


def test_time_remaining_and_format_countdown() -> None:
    target = datetime(2026, 11, 20, 8, 0, 0)
    rem = time_remaining(target, now=datetime(2026, 11, 20, 6, 54, 55))
    assert format_countdown(rem) == "01:05:05"

    # Clamped at zero once target passed
    past_rem = time_remaining(target, now=datetime(2026, 11, 20, 8, 10, 0))
    assert past_rem == timedelta(0)
    assert format_countdown(past_rem) == "00:00:00"
