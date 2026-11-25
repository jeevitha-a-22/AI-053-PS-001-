"""
Date calculation utilities.
Handles leap years, calendar month addition, and exact age calculations.
"""
from datetime import date
import calendar


def is_leap_year(year: int) -> bool:
    """Check if a year is a leap year."""
    return calendar.isleap(year)


def calculate_age(date_of_birth: date, on_date: date) -> int:
    """
    Calculate age in completed years on a specific date.
    Returns negative or 0 if on_date is before or on DOB.
    """
    if on_date < date_of_birth:
        return 0
    age = on_date.year - date_of_birth.year
    if (on_date.month, on_date.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return age


def add_months(start_date: date, months: int) -> date:
    """
    Add a specified number of calendar months to a start date.
    Clamps the day if the target month has fewer days (e.g. Jan 31 + 1 month = Feb 28 or 29).
    Handles leap-year February correctly.
    """
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    max_days_in_month = calendar.monthrange(year, month)[1]
    day = min(start_date.day, max_days_in_month)
    return date(year, month, day)


def days_between(d1: date, d2: date) -> int:
    """Calculate the number of days between two dates (d2 - d1)."""
    return (d2 - d1).days
