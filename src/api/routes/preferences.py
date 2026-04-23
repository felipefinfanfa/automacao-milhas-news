"""Rotas FastAPI para gerenciamento de preferências do usuário."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas.preferences import (
    RegisterIn,
    RegisterOut,
    UserPreferencesIn,
    UserPreferencesOut,
)
from src.config.settings import LOYALTY_PROGRAMS
from src.db.models import UserPreferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


def _get_session() -> Any:
    from src.config.settings import settings
    from src.db.models import create_engine_from_url, get_session_factory

    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)
    with SessionFactory() as session:
        yield session


SessionDep = Annotated[Session, Depends(_get_session)]


@router.get("/programs/list")
def list_programs() -> dict[str, list[str]]:
    return {"programs": LOYALTY_PROGRAMS}


@router.post("/register", response_model=RegisterOut)
def register(body: RegisterIn, session: SessionDep) -> RegisterOut:
    email = body.email.lower()
    row = session.query(UserPreferences).filter_by(email=email).first()

    if row:
        return RegisterOut(user_id=str(row.user_id), email=email, is_new=False)

    new_user_id = uuid.uuid4()
    row = UserPreferences(
        user_id=new_user_id,
        email=email,
        monitored_programs=[],
        transfer_pairs=[],
        accumulation_programs=[],
    )
    session.add(row)
    session.commit()
    return RegisterOut(user_id=str(new_user_id), email=email, is_new=True)


@router.get("/{user_id}", response_model=UserPreferencesOut)
def get_preferences(user_id: str, session: SessionDep) -> UserPreferences:
    row = session.query(UserPreferences).filter_by(user_id=user_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preferências não encontradas")
    return row


@router.put("/{user_id}", response_model=UserPreferencesOut)
def upsert_preferences(
    user_id: str, body: UserPreferencesIn, session: SessionDep
) -> UserPreferences:
    row = session.query(UserPreferences).filter_by(user_id=user_id).first()
    pairs = [{"source": p.source, "dest": p.dest} for p in body.transfer_pairs]

    if row:
        row.monitored_programs = body.validated_programs()
        row.transfer_pairs = pairs
        row.accumulation_programs = body.validated_accumulation()
    else:
        row = UserPreferences(
            user_id=uuid.UUID(user_id),
            monitored_programs=body.validated_programs(),
            transfer_pairs=pairs,
            accumulation_programs=body.validated_accumulation(),
        )
        session.add(row)

    session.commit()
    session.refresh(row)
    return row
