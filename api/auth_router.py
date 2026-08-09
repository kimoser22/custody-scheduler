from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.auth_tokens import mint_token
from api.dependencies import LoginThrottleDep, SessionDep
from api.login_throttle import lockout_error
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
def issue_token(
    request: TokenRequest, session: SessionDep, throttle: LoginThrottleDep
) -> TokenResponse:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    locked_until = throttle.locked_until(request.user_id, now=now)
    if locked_until is not None:
        # Refuse before checking the passcode: a correct guess on the next
        # attempt must not bypass the lock, or it stops being a lock.
        raise lockout_error(locked_until, now=now)

    user = session.get(UserTable, request.user_id)
    # Identical response for unknown user and wrong passcode — no enumeration.
    if user is None or not verify_passcode(request.passcode, user.passcode_hash):
        # Unknown ids are counted too, or they would be a free oracle.
        throttle.record_failure(request.user_id, now=now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    throttle.record_success(request.user_id)
    assert user.id is not None
    return TokenResponse(
        access_token=mint_token(user_id=user.id, role=user.role),
        user_id=user.id,
        role=user.role,
    )
