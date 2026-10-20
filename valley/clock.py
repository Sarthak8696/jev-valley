"""Hour, day and time-of-day helpers. All other code uses these instead of doing its own arithmetic."""

START_HOUR = 6
HOURS_PER_DAY = 24

NIGHT, DAWN, DAY, DUSK = "night", "dawn", "day", "dusk"


def day_of(step: int) -> int:
    """Day number, starting at 1. Step 0 is 6 am on day 1; a new day starts at midnight."""
    return (START_HOUR + step) // HOURS_PER_DAY + 1


def hour_of(step: int) -> int:
    """Hour of the clock, 0 to 23."""
    return (START_HOUR + step) % HOURS_PER_DAY


def time_of_day(step: int) -> str:
    """`dawn` 5:00-6:59, `day` 7:00-17:59, `dusk` 18:00-19:59, otherwise `night`."""
    hour = hour_of(step)
    if 5 <= hour < 7:
        return DAWN
    if 7 <= hour < 18:
        return DAY
    if 18 <= hour < 20:
        return DUSK
    return NIGHT


def clock_text(step: int) -> str:
    """Text such as `Day 12, 6 pm`. Midnight is `12 am` and noon is `12 pm`."""
    hour = hour_of(step)
    hour12 = hour % 12 or 12
    suffix = "am" if hour < 12 else "pm"
    return f"Day {day_of(step)}, {hour12} {suffix}"
