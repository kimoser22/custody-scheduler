import base64
import hashlib
import hmac
import logging
import os
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status

from api.dependencies import SessionDep
from concierge.runner import ConciergeRunner

logger = logging.getLogger(__name__)

# Body only — construct a fresh Response per request so concurrent handlers
# never share mutable response state.
_EMPTY_TWIML_BODY = "<Response></Response>"

twilio_router = APIRouter(prefix="/api/v1/twilio")


def get_concierge_runner(session: SessionDep) -> ConciergeRunner:
    from concierge.factory import build_default_runner

    # session comes from FastAPI's Depends(get_session), which closes it once
    # this request finishes — avoids leaking a DB session on every SMS.
    return build_default_runner(session=session)


def _external_url(request: Request) -> str:
    """Reconstruct the URL Twilio actually posted to, honoring a reverse proxy
    (ngrok, etc.) that sets X-Forwarded-* rather than terminating TLS locally."""
    parts = urlsplit(str(request.url))
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if proto or host:
        parts = parts._replace(scheme=proto or parts.scheme, netloc=host or parts.netloc)
    return urlunsplit(parts)


def _compute_twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    data = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


async def verify_twilio_signature(request: Request) -> None:
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        # No Twilio credentials configured. Fail closed by default — an
        # unverified webhook trusts attacker-controlled form fields (From, Body)
        # as identity. Verification is skipped only when an operator explicitly
        # opts out for local dev / the simulator (mirrors ALLOW_SQLITE_SCHEMA_RESET).
        if os.getenv("TWILIO_ALLOW_UNVERIFIED") == "1":
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Twilio signature verification is not configured.",
        )

    signature = request.headers.get("x-twilio-signature")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing Twilio signature."
        )

    form = await request.form()
    params = {key: str(value) for key, value in form.multi_items()}
    expected = _compute_twilio_signature(auth_token, _external_url(request), params)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature."
        )


@twilio_router.post("/sms", dependencies=[Depends(verify_twilio_signature)])
def receive_sms(
    runner: Annotated[ConciergeRunner, Depends(get_concierge_runner)],
    MessageSid: str = Form(...),
    From: str = Form(...),
    Body: str = Form(...),
) -> Response:
    try:
        runner.handle_sms(
            message_sid=MessageSid,
            from_phone=From,
            body=Body,
        )
    except HTTPException:
        # Must not turn intentional auth/validation signals into a silent 200.
        raise
    except Exception:
        # After signature verification this request was accepted. A 500 here
        # surfaces as Twilio 11200 and the inbound is lost from the family's
        # perspective (default messaging webhooks do not retry 5xx). Ack with
        # empty TwiML and emit an alertable marker for log recovery.
        # Note: get_concierge_runner failures still 500 *before* this try —
        # and before any message_sid claim.
        logger.exception(
            "sms_handler_failed message_sid=%s from=%s",
            MessageSid,
            From,
        )
    # Always a silent, empty-TwiML ack (dropped, ignored, handled, or failed
    # alike); the business outcome is delivered via the SMS replies the nodes
    # send when the handler succeeds.
    return Response(content=_EMPTY_TWIML_BODY, media_type="application/xml")
