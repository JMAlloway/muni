import logging
from typing import Optional

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.core.settings import settings

log = logging.getLogger(__name__)


def _client() -> Optional[Client]:
    if not settings.SMS_ENABLED:
        return None
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER):
        log.warning("SMS disabled: missing Twilio credentials or from number")
        return None
    try:
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as exc:
        log.error("SMS client init failed: %s", exc)
        return None


def send_sms(to_number: str, body: str) -> bool:
    """
    Send an SMS via Twilio. Returns True on success, False otherwise.

    This is intentionally synchronous; call it from a threadpool if you need non-blocking behavior.
    """
    client = _client()
    if not client:
        return False

    try:
        client.messages.create(
            to=to_number,
            from_=settings.TWILIO_FROM_NUMBER,
            body=(body or "")[:320],  # trim to keep messages concise
        )
        return True
    except TwilioRestException as exc:
        log.error("SMS send failed (Twilio): %s", exc)
    except Exception as exc:  # pragma: no cover - safety net
        log.error("SMS send failed: %s", exc)
    return False
