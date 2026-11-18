#!/usr/bin/env python3
"""When the Proving Ground is supposed to run.

Monthly, early in the week: the first Monday of the month at 9:00 AM
America/Chicago (changed from first Friday on 2026-11-18 per the owner, so the
results give us things to work on through the week). The window stays open
through the end of that month, so a missed Monday can still be run. One
official run per calendar month; a second official run needs an explicit
force flag from the owner.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import paths

TZ = paths.TZ
SESSION_WEEKDAY = 0  # Monday
SESSION_TIME = time(9, 0)
# Back-compat names
RESET_WEEKDAY = SESSION_WEEKDAY
RESET_TIME = SESSION_TIME


def first_monday(year: int, month: int) -> date:
    day = date(year, month, 1)
    # Monday=0 ... Sunday=6
    delta = (SESSION_WEEKDAY - day.weekday()) % 7
    return day + timedelta(days=delta)


first_friday = first_monday  # old name, kept so callers don't break


def session_open_at(year: int, month: int) -> datetime:
    monday = first_monday(year, month)
    return datetime.combine(monday, SESSION_TIME, tzinfo=TZ)


def next_session(when: datetime | None = None) -> datetime:
    """The next (or current, if already open today) official window start."""
    stamp = when or paths.now()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=TZ)
    stamp = stamp.astimezone(TZ)
    this_open = session_open_at(stamp.year, stamp.month)
    if stamp < this_open:
        return this_open
    # Window is open for the rest of this month.
    return this_open


def window_for(when: datetime | None = None) -> tuple[datetime, datetime]:
    """(opens, last instant of the month)."""
    stamp = when or paths.now()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=TZ)
    stamp = stamp.astimezone(TZ)
    opens = session_open_at(stamp.year, stamp.month)
    if stamp.month == 12:
        end = datetime(stamp.year + 1, 1, 1, tzinfo=TZ)
    else:
        end = datetime(stamp.year, stamp.month + 1, 1, tzinfo=TZ)
    closes = end - timedelta(seconds=1)
    return opens, closes


def in_window(when: datetime | None = None) -> bool:
    stamp = when or paths.now()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=TZ)
    stamp = stamp.astimezone(TZ)
    opens, closes = window_for(stamp)
    return opens <= stamp <= closes


def describe(when: datetime | None = None) -> str:
    stamp = when or paths.now()
    opens, closes = window_for(stamp)
    if in_window(stamp):
        return (
            f"Official window for {paths.month_id(stamp)} is open. "
            f"It opened {opens.strftime('%Y-%m-%d %-I:%M %p')} {paths.TZ_LABEL} "
            f"(first Monday of the month, 9:00 AM) and closes "
            f"{closes.strftime('%Y-%m-%d %-I:%M %p')} {paths.TZ_LABEL}."
        )
    if stamp < opens:
        return (
            f"Next official window opens {opens.strftime('%Y-%m-%d %-I:%M %p')} "
            f"{paths.TZ_LABEL} (first Monday of the month, 9:00 AM)."
        )
    # After the month? next_session already handles by using next month if we pass a later date.
    nxt = session_open_at(stamp.year + (1 if stamp.month == 12 else 0), 1 if stamp.month == 12 else stamp.month + 1)
    return (
        f"The {paths.month_id(stamp)} window has closed. "
        f"Next official window opens {nxt.strftime('%Y-%m-%d %-I:%M %p')} {paths.TZ_LABEL}."
    )
