"""Build .ics calendar files for bookings.

Pure function — takes primitives, returns the .ics as bytes. The caller
(notifications) attaches it to the customer confirmation email.

Datetimes are treated as UTC (consistent with the naive-UTC models).
"""
import uuid
from datetime import datetime, timezone

from icalendar import Calendar, Event


def build_ics(
    *,
    summary: str,
    start: datetime,
    end: datetime,
    location: str | None = None,
    description: str = "",
    organizer_email: str | None = None,
    uid: str | None = None,
    method: str = "REQUEST",
) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Bookly//Appointment Booking//EN")
    cal.add("version", "2.0")
    cal.add("method", method)

    event = Event()
    event.add("summary", summary)
    if method == "CANCEL":
        event.add("status", "CANCELLED")
    # mark naive UTC datetimes as UTC so calendar apps place them correctly
    event.add("dtstart", start.replace(tzinfo=timezone.utc))
    event.add("dtend", end.replace(tzinfo=timezone.utc))
    event.add("dtstamp", datetime.now(timezone.utc))
    event.add("uid", uid or f"{uuid.uuid4()}@bookly")
    if location:
        event.add("location", location)
    if description:
        event.add("description", description)
    if organizer_email:
        event.add("organizer", f"mailto:{organizer_email}")

    cal.add_component(event)
    return cal.to_ical()
