"""Domain types compartilhados entre monitors, processor e email."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


PromoType = Literal["transfer_bonus", "points_purchase", "other"]
SourceType = Literal["direct_scraper", "hash_diff", "rss", "google_news", "sitemap",
                     "robots", "news_scraper", "url_fuzzer", "visual_diff", "ct_logs",
                     "dns_monitor", "search_console"]


class RawSignal(BaseModel):
    """Saída bruta de qualquer monitor — entrada do extractor."""
    source_url: str
    source_program: str | None = None
    source_type: SourceType
    title: str | None = None
    raw_content: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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


class TransferPair(BaseModel):
    source: str
    dest: str


class UserPreferencesData(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    unsubscribe_token: str | None = None
    monitored_programs: list[str] = Field(default_factory=list)
    transfer_pairs: list[TransferPair] = Field(default_factory=list)
    accumulation_programs: list[str] = Field(default_factory=list)
