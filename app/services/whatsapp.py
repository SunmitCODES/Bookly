"""WhatsApp messages via Gupshup.

Mirrors notifications.send_email: a single never-raises choke point. No-op
when the API key or recipient phone is missing, so reminders degrade
gracefully to email-only until Gupshup is configured.

Note: business-initiated WhatsApp requires a pre-approved Gupshup template.
The HTTP shape here matches Gupshup's text-message API; swap to the template
endpoint once your template is approved.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger("bookly.whatsapp")

_GUPSHUP_URL = "https://api.gupshup.io/wa/api/v1/msg"


def send_whatsapp(to_phone: str | None, message: str) -> None:
    if not to_phone or not settings.gupshup_api_key or not settings.gupshup_source:
        return
    try:
        httpx.post(
            _GUPSHUP_URL,
            headers={"apikey": settings.gupshup_api_key},
            data={
                "channel": "whatsapp",
                "source": settings.gupshup_source,
                "destination": to_phone,
                "src.name": settings.gupshup_app_name,
                "message": message,
            },
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 — must never crash the caller
        logger.error("Failed to send WhatsApp to %s: %s", to_phone, exc)
