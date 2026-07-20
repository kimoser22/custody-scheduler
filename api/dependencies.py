from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from api.auth_tokens import TokenError, verify_token
from database.connection import get_session

SessionDep = Annotated[Session, Depends(get_session)]

_BEARER_PREFIX = "Bearer "


class CurrentUser(BaseModel):
    id: int
    role: str
    family_id: int = 1


async def get_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if authorization.startswith(_BEARER_PREFIX):
        return authorization[len(_BEARER_PREFIX):]
    return authorization


async def get_current_user(
    token: Annotated[str, Depends(get_token)],
) -> CurrentUser:
    try:
        user_id, role = verify_token(token)
    except TokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from None
    return CurrentUser(id=user_id, role=role)


async def require_parent_role(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if current_user.role != "Parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action restricted to Parent roles only.",
        )
    return current_user


def require_role(role: str) -> Callable[..., CurrentUser]:
    async def _require_role(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _require_role
