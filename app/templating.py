"""Shared Jinja2 templates instance.

Lives in its own module so both main.py and the page routers can import it
without a circular import. Also registers an `ist` filter that converts the
naive-UTC datetimes stored in the DB to India Standard Time for display.
"""
from datetime import timedelta

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

_IST_OFFSET = timedelta(hours=5, minutes=30)


def to_ist(dt, fmt: str = "%a %d %b %Y, %I:%M %p"):
    """Render a naive-UTC datetime in IST (UTC+5:30)."""
    if dt is None:
        return ""
    return (dt + _IST_OFFSET).strftime(fmt) + " IST"


templates.env.filters["ist"] = to_ist
