"""Sleep cycle and exact-time wake calculation plus bedtime check logic."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum


class AlarmMode(Enum):
    """Supported alarm scheduling modes."""

    CYCLES = "cycles"
    EXACT = "exact"


@dataclass(frozen=True)
class SleepPlan:
    """Active scheduled alarm plan and bedtime check state."""

    mode: AlarmMode
    started_at: datetime
    target_time: datetime
    cycles: int | None = None
    cycle_minutes: int = 90
    fall_asleep_minutes: int = 15
    bedtime_shift_minutes: int = 15
    bedtime_confirmed: bool = False
    shifts_count: int = 0
    next_bedtime_check: datetime | None = None


def calculate_cycles_wake_time(
    now: datetime,
    cycles: int,
    cycle_minutes: int = 90,
    fall_asleep_minutes: int = 15,
) -> datetime:
    """Calculate wake-up time as now + fall_asleep_minutes + cycles * cycle_minutes."""
    if cycles < 1:
        raise ValueError("cycles must be >= 1")
    if cycle_minutes < 1:
        raise ValueError("cycle_minutes must be >= 1")
    if fall_asleep_minutes < 0:
        raise ValueError("fall_asleep_minutes must be >= 0")

    total_minutes = fall_asleep_minutes + (cycles * cycle_minutes)
    return now + timedelta(minutes=total_minutes)


def calculate_exact_wake_time(
    now: datetime,
    hour: int,
    minute: int,
) -> tuple[datetime, bool]:
    """Calculate target datetime for HH:MM; rolls over to tomorrow if already passed."""
    if not (0 <= hour <= 23):
        raise ValueError("hour must be in 0..23")
    if not (0 <= minute <= 59):
        raise ValueError("minute must be in 0..59")

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        return candidate + timedelta(days=1), True
    return candidate, False


def create_cycles_plan(
    cycles: int,
    cycle_minutes: int = 90,
    fall_asleep_minutes: int = 15,
    bedtime_check_enabled: bool = True,
    bedtime_check_delay_minutes: int = 15,
    bedtime_shift_minutes: int = 15,
    now: datetime | None = None,
) -> SleepPlan:
    """Create a sleep-cycle alarm plan with optional automatic bedtime check."""
    current = now or datetime.now()
    target = calculate_cycles_wake_time(
        now=current,
        cycles=cycles,
        cycle_minutes=cycle_minutes,
        fall_asleep_minutes=fall_asleep_minutes,
    )
    next_check: datetime | None = None
    if bedtime_check_enabled:
        candidate_check = current + timedelta(minutes=max(1, bedtime_check_delay_minutes))
        if candidate_check < target:
            next_check = candidate_check

    return SleepPlan(
        mode=AlarmMode.CYCLES,
        started_at=current,
        target_time=target,
        cycles=cycles,
        cycle_minutes=cycle_minutes,
        fall_asleep_minutes=fall_asleep_minutes,
        bedtime_shift_minutes=bedtime_shift_minutes,
        bedtime_confirmed=not bedtime_check_enabled,
        shifts_count=0,
        next_bedtime_check=next_check,
    )


def create_exact_plan(
    hour: int,
    minute: int,
    bedtime_shift_minutes: int = 15,
    now: datetime | None = None,
) -> SleepPlan:
    """Create an exact-time (HH:MM) alarm plan, rolling to tomorrow if needed."""
    current = now or datetime.now()
    target, _ = calculate_exact_wake_time(now=current, hour=hour, minute=minute)
    return SleepPlan(
        mode=AlarmMode.EXACT,
        started_at=current,
        target_time=target,
        cycles=None,
        bedtime_shift_minutes=bedtime_shift_minutes,
        bedtime_confirmed=True,
        shifts_count=0,
        next_bedtime_check=None,
    )


def create_snooze_plan(
    previous_plan: SleepPlan,
    snooze_minutes: int = 5,
    now: datetime | None = None,
) -> SleepPlan:
    """Create a short snooze plan from an existing plan."""
    current = now or datetime.now()
    return replace(
        previous_plan,
        started_at=current,
        target_time=current + timedelta(minutes=max(1, snooze_minutes)),
        bedtime_confirmed=True,
        next_bedtime_check=None,
    )


def is_bedtime_check_due(plan: SleepPlan, now: datetime | None = None) -> bool:
    """Return True if it is time to ask 'Did you go to sleep?'."""
    if plan.bedtime_confirmed or plan.next_bedtime_check is None:
        return False
    current = now or datetime.now()
    return plan.next_bedtime_check <= current < plan.target_time


def apply_bedtime_check(
    plan: SleepPlan,
    went_to_sleep: bool,
    now: datetime | None = None,
    shift_minutes: int | None = None,
) -> SleepPlan:
    """Apply user response to bedtime check ('yes' confirms, 'no' shifts +15 min)."""
    if went_to_sleep:
        return replace(plan, bedtime_confirmed=True, next_bedtime_check=None)

    current = now or datetime.now()
    delta_min = plan.bedtime_shift_minutes if shift_minutes is None else max(1, shift_minutes)
    new_target = plan.target_time + timedelta(minutes=delta_min)
    candidate_check = current + timedelta(minutes=delta_min)
    next_check = candidate_check if candidate_check < new_target else None

    return replace(
        plan,
        target_time=new_target,
        bedtime_confirmed=False,
        shifts_count=plan.shifts_count + 1,
        next_bedtime_check=next_check,
    )


def time_remaining(target_time: datetime, now: datetime | None = None) -> timedelta:
    """Return non-negative timedelta remaining until target_time."""
    current = now or datetime.now()
    delta = target_time - current
    return delta if delta > timedelta(0) else timedelta(0)


def is_alarm_due(target_time: datetime, now: datetime | None = None) -> bool:
    """Return True when current time has reached or passed target_time."""
    current = now or datetime.now()
    return current >= target_time


def format_hm(dt: datetime) -> str:
    """Format datetime as HH:MM."""
    return dt.strftime("%H:%M")


def format_hms(dt: datetime) -> str:
    """Format datetime as HH:MM:SS."""
    return dt.strftime("%H:%M:%S")


def format_countdown(delta: timedelta) -> str:
    """Format timedelta as HH:MM:SS."""
    total_seconds = max(0, int(delta.total_seconds()))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
