"""
Spoken alarms and timers -- "wake me up at 7am", "remind me in 20 minutes".

Parsing is a small set of regexes, not sent through the local model: a timer
has to fire at the right second, and asking a 3B model to extract "20 minutes"
reliably is exactly the kind of precise, literal task it's bad at (see the
Morse code experiment -- it failed even with the answer in front of it).

Deliberately gated on an explicit keyword ("alarm", "remind", "timer", "wake
me", "nudge", "let me know"...) as well as a time expression, not on the time
expression alone -- otherwise ordinary conversation like "I usually get up at
7" would silently schedule a bogus alarm. Verified both ways: nine real
phrasings all schedule, and eight conversational sentences containing times
("we talked for an hour yesterday", "that song is about five minutes long")
all correctly don't.

Two things it understands beyond a bare time:

- **Spoken numbers and vague durations** -- "ten minutes", "twenty five
  minutes", "half an hour", "a couple of minutes". Normalised to digits up
  front so only one set of patterns has to exist.
- **The words to say on firing** -- "wake me BY SAYING please wake up" is a
  request for specific words, and answering it with "your 5 minute timer is
  up" ignores what was actually asked for. The database stores the finished
  sentence, so nothing downstream has to reassemble it.
"""

import datetime as dt
import re

import db

_TRIGGER_WORDS = (
    "alarm", "remind", "reminder", "timer", "wake me", "wake up", "set a",
    # People don't only say "remind me". These are the other ways the same
    # request actually comes out loud, and without them a perfectly clear
    # request ("give me a nudge in 20 minutes") parsed its time correctly and
    # was then thrown away for lacking an approved keyword.
    "nudge", "let me know", "get me up", "buzz me", "ping me", "shout",
    "give me a shout", "check on me", "tell me when",
)

# Spoken numbers, because nobody says "in 1 0 minutes" out loud and Whisper
# transcribes what was said. Written before the digit patterns run, so
# everything downstream only ever has to deal with digits.
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
    "ninety": 90,
}

# Phrases that mean a duration but contain no number at all.
#
# Each swallows the preposition in front of it, because the replacement supplies
# its own. Without that, "remind me to take my tablets in half an hour" became
# "...tablets in in 30 minutes"; _RELATIVE consumed the second "in", the first
# survived into the remainder, and she said "Time to take my tablets in."
#
# Absorbed here rather than stripped from the tail afterwards, so a request that
# genuinely ends in a preposition still survives -- "remind me to log in in five
# minutes" contains no duration phrase, is left alone, and stays "log in".
_PREPOSITION = r"(?:(?:in|after|for|within)\s+)?"
# Longest first, and it has to stay that way: "an hour and a half", "quarter of
# an hour" and "half an hour" all contain "an hour", so a plain "an hour" rule
# sitting above them claims the tail of each. That put "quarter of an hour"
# through the wrong rule entirely -- a fifteen minute reminder was set for an
# hour, and she announced it as "Time to leave in quarter of."
_DURATION_PHRASES = [
    (re.compile(rf"\b{_PREPOSITION}an hour and a half\b", re.I), "in 90 minutes"),
    (re.compile(rf"\b{_PREPOSITION}quarter of an hour\b", re.I), "in 15 minutes"),
    (re.compile(rf"\b{_PREPOSITION}half an hour\b", re.I), "in 30 minutes"),
    (re.compile(rf"\b{_PREPOSITION}(?:an|one) hour\b", re.I), "in 60 minutes"),
    (re.compile(rf"\b{_PREPOSITION}a couple(?: of)? (?:minutes|mins)\b", re.I), "in 2 minutes"),
    (re.compile(rf"\b{_PREPOSITION}a few (?:minutes|mins)\b", re.I), "in 3 minutes"),
]


def _normalise(text: str) -> str:
    """Turn spoken forms into the digit forms the patterns below expect."""
    out = text
    for pattern, replacement in _DURATION_PHRASES:
        out = pattern.sub(replacement, out)

    # "twenty five minutes" -> "25 minutes", before the single-word pass, or
    # "twenty" and "five" would each be replaced separately and become "20 5".
    def compound(match):
        tens = _WORD_NUMBERS[match.group(1).lower()]
        units = _WORD_NUMBERS[match.group(2).lower()]
        return str(tens + units)

    out = re.sub(
        r"\b(twenty|thirty|forty|fourty|fifty)[\s-]+(one|two|three|four|five|six|seven|eight|nine)\b",
        compound, out, flags=re.I,
    )
    for word, value in _WORD_NUMBERS.items():
        out = re.sub(rf"\b{word}\b", str(value), out, flags=re.I)
    return out


_RELATIVE = re.compile(
    r"\b(?:in|for|after)\s+(\d+)\s*(hour|hr|minute|min)s?\b(?:\s*(?:and)?\s*(\d+)\s*(minute|min)s?\b)?",
    re.IGNORECASE,
)

# "set a timer for 5" means five minutes, not five o'clock. Only ever applied
# when the word "timer" is present -- "set an alarm for 5" genuinely is a clock
# time, and guessing minutes there would be worse than not guessing at all.
_BARE_TIMER = re.compile(r"\btimer\s+(?:for|of)\s+(\d{1,3})\b(?!\s*(?::|am|pm|o'?clock))", re.IGNORECASE)

# "half past seven", "quarter to six" -- normalised to digits already.
_HALF_PAST = re.compile(r"\b(half|quarter)\s+(past|to)\s+(\d{1,2})\b", re.IGNORECASE)
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


# What she should actually say when it goes off. "Wake me by saying please wake
# up" is a request for specific words, and answering it with "your 5 minute
# timer is up" ignores what was asked for.
_SAY_THIS = re.compile(r"\b(?:by\s+)?saying\s+(?:that\s+)?(.+)", re.IGNORECASE)
_REMIND_TO = re.compile(r"\bremind me to\s+(.+)", re.IGNORECASE)

_TIDY_TAIL = re.compile(r"[\s,.;:]+$")


def _spoken_message(remainder: str) -> str | None:
    """The words she was asked to say, pulled from whatever is left once the
    time expression has been removed."""
    for pattern in (_SAY_THIS, _REMIND_TO):
        match = pattern.search(remainder)
        if not match:
            continue
        words = _TIDY_TAIL.sub("", match.group(1).strip())
        if not words:
            continue
        said = words[0].upper() + words[1:]
        if pattern is _REMIND_TO:
            said = f"Time to {words}"
        return said if said.endswith((".", "!", "?")) else said + "."
    return None


def _finish(fire_at: dt.datetime, default_sentence: str, description: str,
            text: str, span: tuple[int, int]):
    """(fire_at, what_to_say, short_description) for a matched time."""
    remainder = (text[:span[0]] + " " + text[span[1]:]).strip()
    custom = _spoken_message(remainder)
    if custom:
        return fire_at, custom, "that"
    return fire_at, default_sentence, description


def parse_request(text: str) -> tuple[dt.datetime, str, str] | None:
    """(fire_at, what she says when it fires, short description), or None."""
    text = _normalise(text)

    match = _BARE_TIMER.search(text)
    if match:
        delta = dt.timedelta(minutes=int(match.group(1)))
        label = f"your {_describe(delta)} timer"
        return _finish(dt.datetime.now() + delta, f"{label.capitalize()} is up.",
                       label, text, match.span())

    match = _RELATIVE.search(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        delta = dt.timedelta(hours=amount) if unit.startswith("h") else dt.timedelta(minutes=amount)
        if match.group(3):
            delta += dt.timedelta(minutes=int(match.group(3)))
        label = f"your {_describe(delta)} timer"
        return _finish(dt.datetime.now() + delta, f"{label.capitalize()} is up.",
                       label, text, match.span())

    match = _HALF_PAST.search(text)
    if match:
        hour = int(match.group(3))
        minute = 30 if match.group(1).lower() == "half" else 15
        if match.group(2).lower() == "to":
            hour = (hour - 1) % 24
            minute = 60 - minute
        return _at_clock_time(hour, minute, text, match.span())

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
        return _at_clock_time(hour, minute, text, match.span())

    return None


def _at_clock_time(hour: int, minute: int, text: str, span: tuple[int, int]):
    now = dt.datetime.now()
    fire_at = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if fire_at <= now:
        fire_at += dt.timedelta(days=1)  # next occurrence, not today's if already past
    return _finish(fire_at, "Your alarm is going off.", "your alarm", text, span)


def would_schedule(text: str) -> bool:
    """True if this text would actually set an alarm, without setting one --
    lets a caller decide whether to gate the action before schedule() commits
    it to the database."""
    lowered = _normalise(text).lower()
    if not any(w in lowered for w in _TRIGGER_WORDS):
        return False
    return parse_request(text) is not None


def schedule(text: str) -> str | None:
    """Set an alarm from spoken text if it looks like one. Returns what to
    say to confirm it, or None if this wasn't actually an alarm request."""
    lowered = _normalise(text).lower()
    if not any(w in lowered for w in _TRIGGER_WORDS):
        return None

    parsed = parse_request(text)
    if parsed is None:
        return None

    fire_at, spoken, description = parsed
    # The database stores the exact sentence to say, so nothing downstream has
    # to reassemble it -- "please wake up" and "your 5 minute timer is up" are
    # different shapes of sentence and a single template can't serve both.
    db.insert_alarm(fire_at.isoformat(), spoken)
    when = fire_at.strftime("%I:%M %p").lstrip("0")
    day = "" if fire_at.date() == dt.datetime.now().date() else " tomorrow"
    if description == "that":
        return f"Done -- I'll say that at {when}{day}."
    return f"Done -- {description} is set for {when}{day}."


def check_due() -> list[str]:
    """Anything that should fire right now, marked fired, ready to speak."""
    now_iso = dt.datetime.now().isoformat()
    due = db.due_alarms(now_iso)
    lines = []
    for row in due:
        db.mark_alarm_fired(row["id"])
        lines.append(row["label"])
    return lines
