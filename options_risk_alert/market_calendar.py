from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


MARKET_TZ = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)


def is_us_regular_market_open(moment: datetime | None = None) -> bool:
    local_time = to_market_time(moment)
    if not is_us_market_trading_day(local_time):
        return False
    return REGULAR_OPEN <= local_time.time() < REGULAR_CLOSE


def is_us_market_trading_day(moment: datetime | None = None) -> bool:
    local_time = to_market_time(moment)
    if local_time.weekday() >= 5:
        return False
    return local_time.date() not in us_market_holidays(local_time.year)


def market_status_message(moment: datetime | None = None) -> str:
    local_time = to_market_time(moment)
    return (
        "미국 정규장 시간이 아니어서 Yahoo 옵션 스냅샷 수집을 건너뜁니다. "
        f"현재 뉴욕 시간: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}. "
        "정규장 기준: 월-금 09:30-16:00 New York time."
    )


def market_closed_day_message(moment: datetime | None = None) -> str:
    local_time = to_market_time(moment)
    return (
        "미국 시장 거래일이 아니어서 옵션 리스크 작업을 건너뜁니다. "
        f"현재 뉴욕 날짜/시간: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}. "
        "주말 또는 주요 미국 증시 휴장일에는 수집과 정기 리포트를 실행하지 않습니다."
    )


def to_market_time(moment: datetime | None = None) -> datetime:
    current = moment or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(MARKET_TZ)


def us_market_holidays(year: int) -> set[date]:
    holidays = {
        observed_fixed_holiday(year, 1, 1),
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        easter_date(year) - timedelta(days=2),
        last_weekday(year, 5, 0),
        observed_fixed_holiday(year, 6, 19),
        observed_fixed_holiday(year, 7, 4),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4),
        observed_fixed_holiday(year, 12, 25),
    }
    return {holiday for holiday in holidays if holiday.year == year}


def observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    current = date(year, month, 1)
    days_until_weekday = (weekday - current.weekday()) % 7
    return current + timedelta(days=days_until_weekday + 7 * (nth - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    days_since_weekday = (current.weekday() - weekday) % 7
    return current - timedelta(days=days_since_weekday)


def easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)
