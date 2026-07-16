import base64
import hashlib
import hmac
import os
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status

from api.dependencies import SessionDep
from concierge.runner import ConciergeRunner

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
        # No Twilio credentials configured (local dev / simulator / A2P not yet
        # provisioned) — nothing to verify against. Skip rather than lock the
        # endpoint out entirely; this codepath must not be reached with real
        # public traffic until TWILIO_AUTH_TOKEN is set.
        return

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
    result = runner.handle_sms(
        message_sid=MessageSid,
        from_phone=From,
        body=Body,
    )
    # Silent Twilio-friendly ack; business outcome is in SMS replies from nodes.
    if result.get("status") in {"dropped", "ignored"}:
        return Response(content="<Response></Response>", media_type="application/xml")
    return Response(content="<Response></Response>", media_type="application/xml")
