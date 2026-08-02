"""
Spoken alarms and timers -- "wake me up at 7am", "remind me in 20 minutes".

Parsing is a small set of regexes, not sent through the local model: a timer
has to fire at the right second, and asking a 3B model to extract "20 minutes"
reliably is exactly the kind of precise, literal task it's bad at (see the
Morse code experiment -- it failed even with the answer in front of it).

Deliberately gated on an explicit keyword ("alarm", "remind", "timer", "wake
me") as well as a time expression, not on the time expression alone --
otherwise ordinary conversation like "I usually get up at 7" would silently
schedule a bogus alarm.
"""

import datetime as dt
import re

import db

_TRIGGER_WORDS = ("alarm", "remind", "reminder", "timer", "wake me", "wake up", "set a")

_RELATIVE = re.compile(
    r"\b(?:in|for)\s+(\d+)\s*(hour|hr|minute|min)s?\b(?:\s*(?:and)?\s*(\d+)\s*(minute|min)s?\b)?",
    re.IGNORECASE,
)
# "for 7am" is a valid absolute time ("set an alarm for 7am"), but "for 10
# minutes" is a duration, not a clock time. Safe because _RELATIVE (which
# requires an explicit hour/minute unit word) is always checked first in
# parse_request() -- "for 10 minutes" is claimed by that before it ever
# reaches here, leaving only genuine clock-time phrasings for this pattern.
_ABSOLUTE = re.compile(
    r"\b(?:at|for)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)


def _describe(delta: dt.timedelta) -> str:
    total_min = max(1, int(delta.total_seconds() // 60))
    if total_min < 60:
        return f"{total_min} minute"
    hours, minutes = divmod(total_min, 60)
    return f"{hours} hour {minutes} minute" if minutes else f"{hours} hour"


def parse_request(text: str) -> tuple[dt.datetime, str] | None:
    """(fire_at, label), or None if this isn't a recognisable timer/alarm."""
    match = _RELATIVE.search(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        delta = dt.timedelta(hours=amount) if unit.startswith("h") else dt.timedelta(minutes=amount)
        if match.group(3):
            delta += dt.timedelta(minutes=int(match.group(3)))
        fire_at = dt.datetime.now() + delta
        return fire_at, f"your {_describe(delta)} timer"

    match = _ABSOLUTE.search(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        ampm = (match.group(3) or "").lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if not (0 <= hour <= 23):
            return None

        now = dt.datetime.now()
        fire_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if fire_at <= now:
            fire_at += dt.timedelta(days=1)  # next occurrence, not today's if already past
        return fire_at, "your alarm"

    return None


def would_schedule(text: str) -> bool:
    """True if this text would actually set an alarm, without setting one --
    lets a caller decide whether to gate the action before schedule() commits
    it to the database."""
    lowered = text.lower()
    if not any(w in lowered for w in _TRIGGER_WORDS):
        return False
    return parse_request(text) is not None


def schedule(text: str) -> str | None:
    """Set an alarm from spoken text if it looks like one. Returns what to
    say to confirm it, or None if this wasn't actually an alarm request."""
    lowered = text.lower()
    if not any(w in lowered for w in _TRIGGER_WORDS):
        return None

    parsed = parse_request(text)
    if parsed is None:
        return None

    fire_at, label = parsed
    db.insert_alarm(fire_at.isoformat(), label)
    when = fire_at.strftime("%I:%M %p").lstrip("0")
    day = "" if fire_at.date() == dt.datetime.now().date() else " tomorrow"
    return f"Done -- {label} is set for {when}{day}."


def check_due() -> list[str]:
    """Anything that should fire right now, marked fired, ready to speak."""
    now_iso = dt.datetime.now().isoformat()
    due = db.due_alarms(now_iso)
    lines = []
    for row in due:
        db.mark_alarm_fired(row["id"])
        lines.append(row["label"])
    return lines
