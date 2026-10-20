import pytest

from valley.clock import clock_text, day_of, hour_of, time_of_day


def test_step_zero_is_day_one_6_am():
    assert clock_text(0) == "Day 1, 6 am"
    assert day_of(0) == 1
    assert hour_of(0) == 6


def test_step_18_is_midnight_of_day_two():
    assert clock_text(18) == "Day 2, 12 am"


def test_noon_and_midnight_wording():
    assert clock_text(6) == "Day 1, 12 pm"
    assert clock_text(12) == "Day 1, 6 pm"
    assert clock_text(17) == "Day 1, 11 pm"


def test_a_month_runs_30_days_of_steps():
    assert day_of(719) == 31  # the 6 am start means the last hours fall just into day 31
    assert clock_text(720) == "Day 31, 6 am"


@pytest.mark.parametrize("hour, expected", [
    (4, "night"), (5, "dawn"), (6, "dawn"), (7, "day"), (17, "day"),
    (18, "dusk"), (19, "dusk"), (20, "night"), (23, "night"), (0, "night"),
])
def test_time_of_day_table(hour, expected):
    step = (hour - 6) % 24
    assert hour_of(step) == hour
    assert time_of_day(step) == expected
