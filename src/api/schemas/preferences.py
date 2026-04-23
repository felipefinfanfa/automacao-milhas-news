from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.config.settings import LOYALTY_PROGRAMS


class TransferPairIn(BaseModel):
    source: str
    dest: str

    model_config = {"str_strip_whitespace": True}


class UserPreferencesIn(BaseModel):
    monitored_programs: list[str] = Field(default_factory=list)
    transfer_pairs: list[TransferPairIn] = Field(default_factory=list)
    accumulation_programs: list[str] = Field(default_factory=list)

    def validated_programs(self) -> list[str]:
        return [p for p in self.monitored_programs if p in LOYALTY_PROGRAMS]

    def validated_accumulation(self) -> list[str]:
        return [p for p in self.accumulation_programs if p in LOYALTY_PROGRAMS]


class UserPreferencesOut(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    monitored_programs: list[str]
    transfer_pairs: list[TransferPairIn]
    accumulation_programs: list[str]

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
