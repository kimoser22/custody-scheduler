from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from database.connection import get_session

SessionDep = Annotated[Session, Depends(get_session)]


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
    return authorization


def _role_from_token(token: str) -> str:
    if token.startswith("parent:"):
        return "Parent"
    return "Viewer"


async def get_current_user(
    token: Annotated[str, Depends(get_token)],
) -> CurrentUser:
    role = _role_from_token(token)
    user_id = 1 if role == "Parent" else 2
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
