"""Email, sent from a background job so a slow or failing provider never blocks a request and
failures are retried.

EMAIL_BACKEND=console logs each email instead of sending it, for development. resend sends
through resend.com; any provider with an HTTP API fits in `_send` the same way.
"""

import html
import logging

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import PermanentError, enqueue, handler

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


def send_email(session: Session, to: str, subject: str, text: str) -> None:
    """Queue an email. It goes out after the session commits."""
    enqueue(session, "send_email", {"to": to, "subject": subject, "text": text})


@handler("send_email")
def _send(session: Session, payload: dict) -> None:
    settings = get_settings()
    if settings.email_backend == "console":
        logger.info("Email to %s: %s\n%s", payload["to"], payload["subject"], payload["text"])
        return
    if settings.email_backend != "resend" or not settings.resend_api_key:
        raise PermanentError("EMAIL_BACKEND=resend needs RESEND_API_KEY.")
    body = {
        "from": settings.email_from,
        "to": [payload["to"]],
        "subject": payload["subject"],
        "text": payload["text"],
        "html": "<p>" + html.escape(payload["text"]).replace("\n\n", "</p><p>") + "</p>",
    }
    response = httpx.post(
        RESEND_URL,
        json=body,
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        timeout=15,
    )
    if response.status_code in (400, 401, 403, 422):
        # A bad address or key won't fix itself by retrying.
        raise PermanentError(f"Resend refused the email ({response.status_code}).")
    response.raise_for_status()
