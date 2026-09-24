"""Natural-language date/time parsing in the user's timezone."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser

from app.core.errors import ValidationFailedError

_TIME_ONLY = re.compile(r"^\s*(at\s+)?\d{1,2}(:\d{2})?\s*(am|pm)?\s*$", re.IGNORECASE)
_DAYPART = {
    "morning": "8:00 am",
    "this morning": "8:00 am",
    "noon": "12:00 pm",
    "afternoon": "3:00 pm",
    "evening": "6:00 pm",
    "tonight": "8:00 pm",
    "night": "9:00 pm",
}


def _normalise(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\btmrw\b|\btmr\b", "tomorrow", t)
    for part, clock in _DAYPART.items():
        t = re.sub(rf"\b(tomorrow|today)\s+{part}\b", rf"\1 {clock}", t)
        t = re.sub(rf"^{part}$", f"today {clock}", t)
    # "tomorrow at 8 am" -> dateparser prefers "tomorrow 8 am"
    t = re.sub(r"\bat\s+(?=\d)", "", t)
    # "next monday" -> "monday" (future preference already picks the next one)
    t = re.sub(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", r"\1", t)
    # A day without a time ("tomorrow", "next friday") defaults to 9 AM.
    if not re.search(r"\d|noon|morning|afternoon|evening|night|minute|hour|week|month", t) and re.search(
            r"\b(tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", t):
        t = f"{t} 9:00 am"
    # A bare clock time means "today at", rolled to tomorrow below if already past.
    if _TIME_ONLY.match(t):
        t = "today " + t
    return t


def parse_when(text: str, tz: str, *, now: datetime | None = None, require_future: bool = True) -> datetime:
    """Parse 'tomorrow at 8 AM', 'in 20 minutes', 'next Monday 9am' or ISO-8601.

    Returns an aware datetime in UTC.
    """
    if not text or not text.strip():
        raise ValidationFailedError("No time was given.", code="invalid_time")
    zone = ZoneInfo(tz)
    now = now or datetime.now(UTC)
    local_now = now.astimezone(zone)
    parsed: datetime | None = None
    try:
        iso = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        parsed = iso if iso.tzinfo else iso.replace(tzinfo=zone)
    except ValueError:
        pass
    if parsed is None:
        normalised = _normalise(text)
        parsed = dateparser.parse(
            normalised,
            settings={
                "TIMEZONE": tz,
                "TO_TIMEZONE": tz,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": local_now.replace(tzinfo=None),
            },
        )
        if parsed is not None and _TIME_ONLY.match(text) and parsed.astimezone(zone) <= local_now:
            parsed = parsed + timedelta(days=1)  # "at 7pm" when it's already 8pm -> tomorrow
    if parsed is None:
        raise ValidationFailedError(
            f"I couldn't understand the time “{text}”.",
            code="invalid_time",
            next_step="Try something like 'tomorrow at 8 AM' or 'in 30 minutes'.",
        )
    result = parsed.astimezone(UTC)
    if require_future and result <= now - timedelta(seconds=30):
        raise ValidationFailedError(
            f"“{text}” is in the past ({parsed.astimezone(zone):%a %d %b %H:%M}).",
            code="time_in_past",
            next_step="Give a time in the future.",
        )
    return result


def humanize(dt: datetime, tz: str, now: datetime | None = None) -> str:
    zone = ZoneInfo(tz)
    local = dt.astimezone(zone)
    today = (now or datetime.now(UTC)).astimezone(zone).date()
    if local.date() == today:
        day = "today"
    elif local.date() == today + timedelta(days=1):
        day = "tomorrow"
    else:
        day = local.strftime("%A %d %B")
    return f"{day} at {local.strftime('%I:%M %p').lstrip('0')}"
