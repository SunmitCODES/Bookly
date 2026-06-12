"""Email notifications via Resend.

`send_email` is the single choke point: every send goes through it, and it
never raises — failures are logged so a Resend outage can never break a
booking. Higher-level helpers build the HTML and call it.

Times are naive UTC (consistent with the models); human-friendly IST
formatting is deferred to the customer-facing HTML phase.
"""
import base64
import logging
from datetime import datetime

import resend

from app.config import settings
from app.services.calendar import build_ics

logger = logging.getLogger("bookly.notifications")

resend.api_key = settings.resend_api_key


def _fmt(dt: datetime) -> str:
    return dt.strftime("%a %d %b %Y, %I:%M %p")


def send_email(
    to: str,
    subject: str,
    html: str,
    attachments: list[dict] | None = None,
) -> None:
    """Send one email. Never raises — logs and swallows any error.

    `attachments` is a list of {"filename": str, "content": bytes}. The
    bytes are base64-encoded into the format Resend expects.
    """
    if not to:
        return
    try:
        payload = {
            "from": settings.email_from,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if attachments:
            payload["attachments"] = [
                {
                    "filename": a["filename"],
                    "content": base64.b64encode(a["content"]).decode("ascii"),
                }
                for a in attachments
            ]
        resend.Emails.send(payload)
    except Exception as exc:  # noqa: BLE001 — deliberately broad; must not crash booking
        logger.error("Failed to send email to %s: %s", to, exc)


def send_booking_confirmation(
    *,
    customer_email: str | None,
    customer_name: str,
    business_name: str,
    service_name: str,
    start_time: datetime,
    end_time: datetime,
    business_address: str | None = None,
    booking_id: str | None = None,
    manage_url: str | None = None,
) -> None:
    if not customer_email:
        return
    manage_line = (
        f'<p>Need to cancel? <a href="{manage_url}">Manage your booking</a>.</p>'
        if manage_url
        else ""
    )
    html = f"""
    <h2>Booking confirmed ✅</h2>
    <p>Hi {customer_name},</p>
    <p>Your booking at <strong>{business_name}</strong> is confirmed.</p>
    <ul>
      <li><strong>Service:</strong> {service_name}</li>
      <li><strong>When:</strong> {_fmt(start_time)}</li>
    </ul>
    <p>The attached calendar file lets you add this to your calendar.</p>
    {manage_line}
    <p>See you then!</p>
    """
    ics = build_ics(
        summary=f"{service_name} — {business_name}",
        start=start_time,
        end=end_time,
        location=business_address,
        description=f"Booking for {service_name} at {business_name}.",
        uid=f"{booking_id}@bookly" if booking_id else None,
    )
    send_email(
        customer_email,
        f"Your booking at {business_name} is confirmed",
        html,
        attachments=[{"filename": "booking.ics", "content": ics}],
    )


def send_owner_notification(
    *,
    owner_email: str,
    customer_name: str,
    customer_phone: str,
    service_name: str,
    start_time: datetime,
) -> None:
    html = f"""
    <h2>New booking received 📅</h2>
    <ul>
      <li><strong>Customer:</strong> {customer_name} ({customer_phone})</li>
      <li><strong>Service:</strong> {service_name}</li>
      <li><strong>When:</strong> {_fmt(start_time)}</li>
    </ul>
    """
    send_email(owner_email, f"New booking: {customer_name} — {service_name}", html)


def send_booking_reminder(
    *,
    customer_email: str | None,
    customer_name: str,
    business_name: str,
    service_name: str,
    start_time: datetime,
) -> None:
    if not customer_email:
        return
    html = f"""
    <h2>Reminder: upcoming appointment ⏰</h2>
    <p>Hi {customer_name}, this is a reminder of your booking at
       <strong>{business_name}</strong>.</p>
    <ul>
      <li><strong>Service:</strong> {service_name}</li>
      <li><strong>When:</strong> {_fmt(start_time)}</li>
    </ul>
    <p>See you soon!</p>
    """
    send_email(customer_email, f"Reminder: {service_name} at {business_name}", html)


def send_cancellation(
    *,
    to_email: str | None,
    customer_name: str,
    business_name: str,
    service_name: str,
    start_time: datetime,
    is_owner: bool = False,
) -> None:
    if not to_email:
        return
    who = "A booking was cancelled" if is_owner else "Your booking is cancelled"
    html = f"""
    <h2>{who} ❌</h2>
    <p>The following booking at <strong>{business_name}</strong> has been cancelled:</p>
    <ul>
      <li><strong>Customer:</strong> {customer_name}</li>
      <li><strong>Service:</strong> {service_name}</li>
      <li><strong>Was:</strong> {_fmt(start_time)}</li>
    </ul>
    """
    send_email(to_email, f"Cancelled: {service_name} at {business_name}", html)


def send_reschedule(
    *,
    customer_email: str | None,
    customer_name: str,
    business_name: str,
    service_name: str,
    old_start: datetime,
    new_start: datetime,
    new_end: datetime,
    business_address: str | None = None,
    booking_id: str | None = None,
) -> None:
    if not customer_email:
        return
    html = f"""
    <h2>Your booking has been rescheduled 🔄</h2>
    <p>Hi {customer_name}, your {service_name} at <strong>{business_name}</strong>
       has moved.</p>
    <ul>
      <li><strong>Old time:</strong> {_fmt(old_start)}</li>
      <li><strong>New time:</strong> {_fmt(new_start)}</li>
    </ul>
    <p>The attached calendar file has the updated time.</p>
    """
    ics = build_ics(
        summary=f"{service_name} — {business_name}",
        start=new_start,
        end=new_end,
        location=business_address,
        description=f"Rescheduled booking for {service_name} at {business_name}.",
        uid=f"{booking_id}@bookly" if booking_id else None,
    )
    send_email(
        customer_email,
        f"Rescheduled: {service_name} at {business_name}",
        html,
        attachments=[{"filename": "booking.ics", "content": ics}],
    )
