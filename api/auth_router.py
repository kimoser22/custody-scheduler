import math
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.auth_tokens import mint_token
from api.dependencies import SessionDep
from api.login_throttle import login_throttle
from api.passcodes import verify_passcode
from database.schema import UserTable

auth_router = APIRouter(prefix="/api/v1/auth")


class TokenRequest(BaseModel):
    user_id: int
    passcode: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str


@auth_router.post("/token")
def issue_token(request: TokenRequest, session: SessionDep) -> TokenResponse:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    locked_until = login_throttle.locked_until(request.user_id, now=now)
    if locked_until is not None:
        # Refuse before checking the passcode: a correct guess on the next
        # attempt must not bypass the lock, or it stops being a lock.
        retry_after = max(1, math.ceil((locked_until - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    user = session.get(UserTable, request.user_id)
    # Identical response for unknown user and wrong passcode — no enumeration.
    if user is None or not verify_passcode(request.passcode, user.passcode_hash):
        # Unknown ids are counted too, or they would be a free oracle.
        login_throttle.record_failure(request.user_id, now=now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    login_throttle.record_success(request.user_id)
    assert user.id is not None
    return TokenResponse(
        access_token=mint_token(user_id=user.id, role=user.role),
        user_id=user.id,
        role=user.role,
    )
