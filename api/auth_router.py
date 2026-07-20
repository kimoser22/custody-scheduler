from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.auth_tokens import mint_token
from api.dependencies import SessionDep
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
    user = session.get(UserTable, request.user_id)
    # Identical response for unknown user and wrong passcode — no enumeration.
    if user is None or not verify_passcode(request.passcode, user.passcode_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    assert user.id is not None
    return TokenResponse(
        access_token=mint_token(user_id=user.id, role=user.role),
        user_id=user.id,
        role=user.role,
    )
