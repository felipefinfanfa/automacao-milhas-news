import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class Promotion(Base):
    __tablename__ = "promotions"

    id: Any = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Any = Column(Text, nullable=False, unique=True)
    source_program: Any = Column(Text, nullable=False)
    source_type: Any = Column(Text, nullable=False)
    source_url: Any = Column(Text, nullable=False)
    title: Any = Column(Text)
    promo_type: Any = Column(Text, nullable=False, default="other")
    origin_program: Any = Column(Text)
    destination_program: Any = Column(Text)
    bonus_percent: Any = Column(Numeric(6, 2))
    starts_at: Any = Column(DateTime(timezone=True))
    ends_at: Any = Column(DateTime(timezone=True))
    conditions: Any = Column(Text)
    requires_club: Any = Column(Boolean, nullable=False, default=False)
    requires_card: Any = Column(Boolean, nullable=False, default=False)
    cpf_limit: Any = Column(Text)
    confidence: Any = Column(Numeric(3, 2), nullable=False, default=0.80)
    raw_data: Any = Column(JSONB)
    created_at: Any = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Any = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    email_logs: Any = relationship("EmailLog", back_populates="promotion")


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    id: Any = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Any = Column(Text, nullable=False, unique=True)
    content_hash: Any = Column(Text, nullable=False)
    raw_content: Any = Column(Text)
    fetched_at: Any = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Any = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Any = Column(UUID(as_uuid=True), nullable=False, unique=True)
    email: Any = Column(Text, nullable=True, unique=True)
    name: Any = Column(Text, nullable=True)
    phone: Any = Column(Text, nullable=True)
    unsubscribe_token: Any = Column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=sa_text("gen_random_uuid()"),
    )
    monitored_programs: Any = Column(JSONB, nullable=False, default=list)
    transfer_pairs: Any = Column(JSONB, nullable=False, default=list)
    accumulation_programs: Any = Column(JSONB, nullable=False, default=list)
    created_at: Any = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Any = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    email_logs: Any = relationship("EmailLog", back_populates="user_prefs")


class EmailLog(Base):
    """Fonte da verdade para a sequência de 3 dias por (promo_id, user_id)."""

    __tablename__ = "email_log"

    id: Any = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Any = Column(
        UUID(as_uuid=True),
        ForeignKey("user_preferences.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    promo_id: Any = Column(
        UUID(as_uuid=True),
        ForeignKey("promotions.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_number: Any = Column(Integer, nullable=False)
    sent_at: Any = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "promo_id", "day_number", name="uq_email_log"),)

    promotion: Any = relationship("Promotion", back_populates="email_logs")
    user_prefs: Any = relationship("UserPreferences", back_populates="email_logs")


class MonitorState(Base):
    """Cooldown por domínio após receber 429/403."""

    __tablename__ = "monitor_state"

    id: Any = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Any = Column(Text, nullable=False, unique=True)
    blocked_until: Any = Column(DateTime(timezone=True), nullable=False)
    updated_at: Any = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AutomationLog(Base):
    """Audit log for every GitHub Actions pipeline run."""

    __tablename__ = "automation_logs"

    id: Any = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at: Any = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    workflow: Any = Column(Text, nullable=False)
    tier: Any = Column(Integer, nullable=False)
    status: Any = Column(Text, nullable=False)
    signals_found: Any = Column(Integer, default=0)
    promos_new: Any = Column(Integer, default=0)
    emails_sent: Any = Column(Integer, default=0)
    error_message: Any = Column(Text)
    error_traceback: Any = Column(Text)
    duration_seconds: Any = Column(Numeric(8, 2))
    gh_run_id: Any = Column(Text)


def get_session_factory(engine: Any) -> Any:
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=engine, expire_on_commit=False)


def create_engine_from_url(database_url: str) -> Any:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    # NullPool: never cache connections between queries.
    # Required on Supabase free tier (session-mode pooler, hard limit of 15 connections).
    # hash_diff and other monitors each open their own engine; pooling would exhaust the limit.
    return create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
