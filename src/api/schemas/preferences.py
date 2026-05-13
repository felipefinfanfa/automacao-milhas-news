from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.config.airports import AIRPORTS_LIST
from src.config.settings import ACCUMULATION_PROGRAMS, LOYALTY_PROGRAMS, VALID_TRANSFER_PAIRS

_VALID_IATA: frozenset[str] = frozenset(a["iata"] for a in AIRPORTS_LIST)


class TransferPairIn(BaseModel):
    source: str
    dest: str

    model_config = {"str_strip_whitespace": True}


class FlightRouteIn(BaseModel):
    origin_iata: str | None = None
    destination_iata: str | None = None

    model_config = {"str_strip_whitespace": True}


class UserPreferencesIn(BaseModel):
    monitored_programs: list[str] = Field(default_factory=list)
    transfer_pairs: list[TransferPairIn] = Field(default_factory=list)
    accumulation_programs: list[str] = Field(default_factory=list)
    flight_routes: list[FlightRouteIn] = Field(default_factory=list)
    flight_programs: list[str] = Field(default_factory=list)

    def validated_programs(self) -> list[str]:
        return [p for p in self.monitored_programs if p in LOYALTY_PROGRAMS]

    def validated_accumulation(self) -> list[str]:
        return [p for p in self.accumulation_programs if p in ACCUMULATION_PROGRAMS]

    def validated_transfer_pairs(self) -> list[TransferPairIn]:
        return [p for p in self.transfer_pairs if (p.source, p.dest) in VALID_TRANSFER_PAIRS]

    def validated_flight_routes(self) -> list[FlightRouteIn]:
        result: list[FlightRouteIn] = []
        for r in self.flight_routes:
            if r.origin_iata is None and r.destination_iata is None:
                continue
            if r.origin_iata and r.origin_iata not in _VALID_IATA:
                continue
            if r.destination_iata and r.destination_iata not in _VALID_IATA:
                continue
            result.append(r)
        return result

    def validated_flight_programs(self) -> list[str]:
        return [p for p in self.flight_programs if p in LOYALTY_PROGRAMS]


class UserPreferencesOut(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    monitored_programs: list[str]
    transfer_pairs: list[TransferPairIn]
    accumulation_programs: list[str]
    flight_routes: list[FlightRouteIn] = Field(default_factory=list)
    flight_programs: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator("user_id", mode="before")
    @classmethod
    def coerce_uuid(cls, v: Any) -> str:
        return str(v)


class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=30)

    model_config = {"str_strip_whitespace": True}


class RegisterOut(BaseModel):
    user_id: str
    email: str
    name: str | None = None
    phone: str | None = None
    is_new: bool
