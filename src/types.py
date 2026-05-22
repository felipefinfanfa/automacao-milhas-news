"""Domain types compartilhados entre monitors, processor e email."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PromoType = Literal["transfer_bonus", "points_purchase", "flight_award", "other"]
SourceType = Literal["rss"]


class RawSignal(BaseModel):
    """Saída bruta de qualquer monitor — entrada do extractor."""

    source_url: str
    source_program: str | None = None
    source_type: SourceType
    title: str | None = None
    raw_content: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = Field(default_factory=dict)


class PromotionData(BaseModel):
    """Promoção estruturada produzida pelo extractor (antes de gravar no DB)."""

    fingerprint: str
    source_program: str
    source_type: SourceType
    source_url: str
    title: str | None = None
    promo_type: PromoType = "other"
    origin_program: str | None = None
    destination_program: str | None = None
    bonus_percent: float | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    conditions: str | None = None
    requires_club: bool = False
    requires_card: bool = False
    cpf_limit: str | None = None
    confidence: float = 0.8
    raw_data: dict[str, Any] = Field(default_factory=dict)
    # flight_award fields
    origin_iata: str | None = None
    destination_iata: str | None = None
    miles_count: int | None = None


class TransferPair(BaseModel):
    source: str
    dest: str


class FlightRoute(BaseModel):
    origin_iata: str | None = None
    destination_iata: str | None = None


class UserPreferencesData(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    unsubscribe_token: str | None = None
    monitored_programs: list[str] = Field(default_factory=list)
    transfer_pairs: list[TransferPair] = Field(default_factory=list)
    accumulation_programs: list[str] = Field(default_factory=list)
    flight_routes: list[FlightRoute] = Field(default_factory=list)
    flight_programs: list[str] = Field(default_factory=list)
