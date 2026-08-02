"""Self-service profile: contact phone and email for the signed-in user."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from api.dependencies import CurrentUser, SessionDep, get_current_user, require_parent_role
from concierge.phones import normalize_phone
from database.schema import UserTable

me_router = APIRouter(prefix="/api/v1")


class MeResponse(BaseModel):
    id: int
    role: str
    custody_label: str | None
    phone: str | None
    email: str | None


class MeUpdate(BaseModel):
    phone: str | None = None
    email: str | None = None


def _to_response(user: UserTable) -> MeResponse:
    assert user.id is not None
    return MeResponse(
        id=user.id,
        role=user.role,
        custody_label=user.custody_label,
        phone=user.phone,
        email=user.email,
    )


def _load_user(session: SessionDep, user_id: int) -> UserTable:
    user = session.get(UserTable, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user


def _normalize_phone_or_400(raw: str) -> str:
    stripped = raw.strip()
    if not stripped or not any(ch.isdigit() for ch in stripped):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="phone must include digits.",
        )
    normalized = normalize_phone(stripped)
    if not any(ch.isdigit() for ch in normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="phone could not be normalized.",
        )
    return normalized


def _normalize_email_or_400(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if "@" not in stripped or len(stripped) > 254 or " " in stripped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email is invalid.",
        )
    local, _, domain = stripped.partition("@")
    if not local or not domain or "." not in domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email is invalid.",
        )
    return stripped.lower()


@me_router.get("/me")
def get_me(
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MeResponse:
    return _to_response(_load_user(session, current_user.id))


@me_router.patch("/me")
def patch_me(
    body: MeUpdate,
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> MeResponse:
    user = _load_user(session, current_user.id)

    if "phone" in body.model_fields_set:
        if body.phone is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="phone cannot be cleared.",
            )
        normalized = _normalize_phone_or_400(body.phone)
        conflict = session.exec(
            select(UserTable).where(
                UserTable.phone == normalized,
                UserTable.id != user.id,
            )
        ).first()
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="phone is already in use.",
            )
        user.phone = normalized

    if "email" in body.model_fields_set:
        user.email = _normalize_email_or_400(body.email)

    session.add(user)
    session.commit()
    session.refresh(user)
    return _to_response(user)
