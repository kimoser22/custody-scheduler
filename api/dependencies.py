from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from database.connection import get_session

SessionDep = Annotated[Session, Depends(get_session)]


class CurrentUser(BaseModel):
    id: int
    role: str


async def get_current_user() -> CurrentUser:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


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
