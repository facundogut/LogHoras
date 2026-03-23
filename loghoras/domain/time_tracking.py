from __future__ import annotations

from datetime import date, datetime, timedelta

from loghoras.shared.config import TrackerConfig


def parse_jira_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    if len(value) >= 5 and value[-5] in ['+', '-'] and value[-3:].isdigit():
        value = value[:-5] + value[-5:-2] + ':' + value[-2:]
    return datetime.fromisoformat(value)


def is_business_day(dt_or_date: date | datetime, config: TrackerConfig) -> bool:
    current_date = dt_or_date.date() if isinstance(dt_or_date, datetime) else dt_or_date
    if current_date.strftime('%Y-%m-%d') in config.holidays:
        return False
    return current_date.weekday() in config.business_days


def clamp_day_interval(start_dt: datetime, end_dt: datetime, day: date, config: TrackerConfig) -> timedelta:
    work_start = datetime.combine(day, config.work_start, tzinfo=start_dt.tzinfo)
    work_end = datetime.combine(day, config.work_end, tzinfo=start_dt.tzinfo)
    seg_start = max(start_dt, work_start)
    seg_end = min(end_dt, work_end)
    return max(seg_end - seg_start, timedelta(0))


def calculate_working_hours(start_dt: datetime | None, end_dt: datetime | None, config: TrackerConfig) -> float:
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0.0
    total = timedelta(0)
    current_day = start_dt.date()
    last_day = end_dt.date()
    while current_day <= last_day:
        if is_business_day(current_day, config):
            total += clamp_day_interval(start_dt, end_dt, current_day, config)
        current_day += timedelta(days=1)
    return round(total.total_seconds() / 3600.0, 2)


def month_key(dt: datetime) -> str:
    return dt.strftime('%Y-%m')


def first_day_of_month(dt: datetime) -> date:
    return date(dt.year, dt.month, 1)


def last_day_of_month(dt: datetime) -> date:
    if dt.month == 12:
        return date(dt.year, 12, 31)
    first_next = date(dt.year + (dt.month // 12), (dt.month % 12) + 1, 1)
    return first_next - timedelta(days=1)


def month_filename(dt: datetime, config: TrackerConfig) -> str:
    return str(config.output_dir / f'jira_log_{month_key(dt)}.json')


def find_last_business_day_of_month(dt: datetime, config: TrackerConfig) -> date:
    current_day = last_day_of_month(dt)
    while not is_business_day(current_day, config):
        current_day -= timedelta(days=1)
    return current_day


def find_first_business_day_of_month(dt: datetime, config: TrackerConfig) -> date:
    current_day = first_day_of_month(dt)
    while not is_business_day(current_day, config):
        current_day += timedelta(days=1)
    return current_day


def first_business_moment_of_year_month(year: int, month: int, tzinfo, config: TrackerConfig) -> datetime:
    current_day = date(year, month, 1)
    while not is_business_day(current_day, config):
        current_day += timedelta(days=1)
    return datetime.combine(current_day, config.work_start, tzinfo=tzinfo)


def last_business_moment_of_year_month(year: int, month: int, tzinfo, config: TrackerConfig) -> datetime:
    if month == 12:
        current_day = date(year, 12, 31)
    else:
        current_day = date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)
    while not is_business_day(current_day, config):
        current_day -= timedelta(days=1)
    return datetime.combine(current_day, config.work_end, tzinfo=tzinfo)
