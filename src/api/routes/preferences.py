"""Rotas FastAPI para gerenciamento de preferências do usuário."""
from __future__ import annotations

import uuid
from textwrap import dedent
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.api.schemas.preferences import (
    RegisterIn,
    RegisterOut,
    UserPreferencesIn,
    UserPreferencesOut,
)
from src.config.settings import LOYALTY_PROGRAMS, settings
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


def _unsubscribe_html(message: str) -> str:
    return dedent(f"""\
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <title>Miles Radar — Cancelar inscrição</title>
          <style>
            body {{
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
              background: #f1f5f9; display: flex; align-items: center;
              justify-content: center; min-height: 100vh; margin: 0;
            }}
            .card {{
              background: white; border-radius: 12px; padding: 2rem 2.5rem;
              box-shadow: 0 4px 24px rgba(15,23,42,.1); max-width: 420px;
              text-align: center;
            }}
            h1 {{ font-size: 1.25rem; color: #0f172a; margin-bottom: .75rem; }}
            p  {{ color: #64748b; font-size: .9375rem; line-height: 1.6; }}
            a  {{ color: #6366f1; font-weight: 600; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>Miles Radar</h1>
            <p>{message}</p>
            <p style="margin-top:1.25rem">
              <a href="/">Voltar ao site</a>
            </p>
          </div>
        </body>
        </html>
    """)


@router.get("/programs/list")
def list_programs() -> dict[str, list[str]]:
    return {"programs": LOYALTY_PROGRAMS}


@router.post("/register", response_model=RegisterOut)
def register(body: RegisterIn, session: SessionDep) -> RegisterOut:
    email = body.email.lower()
    row = session.query(UserPreferences).filter_by(email=email).first()

    if row:
        return RegisterOut(
            user_id=str(row.user_id),
            email=email,
            name=row.name,
            phone=row.phone,
            is_new=False,
        )

    user_count = session.query(UserPreferences).count()
    if user_count >= settings.max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Número máximo de cadastros atingido. Tente novamente mais tarde.",
        )

    new_user_id = uuid.uuid4()
    row = UserPreferences(
        user_id=new_user_id,
        email=email,
        name=body.name,
        phone=body.phone,
        unsubscribe_token=uuid.uuid4(),
        monitored_programs=[],
        transfer_pairs=[],
        accumulation_programs=[],
    )
    session.add(row)
    session.commit()
    return RegisterOut(
        user_id=str(new_user_id),
        email=email,
        name=body.name,
        phone=body.phone,
        is_new=True,
    )


@router.get("/unsubscribe/{token}", include_in_schema=False)
def unsubscribe(token: str, session: SessionDep) -> Response:
    """Cancela inscrição e remove todos os dados do usuário via token de e-mail."""
    try:
        token_uuid = uuid.UUID(token)
    except ValueError:
        return Response(
            content=_unsubscribe_html("Token inválido."),
            media_type="text/html",
            status_code=404,
        )

    row = session.query(UserPreferences).filter_by(unsubscribe_token=token_uuid).first()
    if not row:
        return Response(
            content=_unsubscribe_html("Usuário não encontrado ou já removido."),
            media_type="text/html",
            status_code=404,
        )

    session.delete(row)
    session.commit()
    return Response(
        content=_unsubscribe_html(
            "Inscrição cancelada com sucesso. Seus dados foram permanentemente removidos."
        ),
        media_type="text/html",
        status_code=200,
    )


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

    has_prefs = bool(row.transfer_pairs or row.accumulation_programs)
    if has_prefs and row.email:
        from src.email.dispatcher import dispatch_confirmation

        pairs = [
            type("P", (), {"source": p["source"], "dest": p["dest"]})()
            for p in (row.transfer_pairs or [])
            if "source" in p and "dest" in p
        ]
        dispatch_confirmation(
            user_id=str(row.user_id),
            user_email=row.email,
            unsubscribe_token=(
                str(row.unsubscribe_token) if row.unsubscribe_token else None
            ),
            transfer_pairs=pairs,
            accumulation_programs=row.accumulation_programs or [],
        )

    return row
