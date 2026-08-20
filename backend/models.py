"""
Pydantic models for TWT (Trip Without Trap).

Phase 1 exposes only: users, trips, trip_members via API.
Schemas for stops, attractions, hotels, expenses, exchange_rates are
documented below but NOT exposed via API yet. They will be used in later phases.
"""
from datetime import datetime, timezone, date
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
import uuid


# ─────────────────────────────────────────────────────────────
# Base helpers
# ─────────────────────────────────────────────────────────────
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


# ─────────────────────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────────────────────
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    google_id: Optional[str] = None
    email: EmailStr
    name: str
    avatar_url: Optional[str] = None
    home_currency_default: str = "EUR"
    created_at: datetime = Field(default_factory=utcnow)


class UserPublic(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    avatar_url: Optional[str] = None
    home_currency_default: str = "EUR"


# ─────────────────────────────────────────────────────────────
# TRIP
# ─────────────────────────────────────────────────────────────
SUPPORTED_CURRENCIES = ["EUR", "USD", "GBP", "CHF", "JPY"]


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    home_currency: str
    start_date: date
    end_date: date
    cover_image_url: Optional[str] = None

    @field_validator("home_currency")
    @classmethod
    def _cur_supported(cls, v: str) -> str:
        v = v.upper()
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"home_currency must be one of {SUPPORTED_CURRENCIES}")
        return v

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must be greater than or equal to start_date")
        return v


class Trip(BaseModel):
    model_config = ConfigDict(extra="ignore")
    trip_id: str
    owner_id: str
    title: str
    home_currency: str
    start_date: date
    end_date: date
    cover_image_url: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TripWithRole(Trip):
    role: Literal["owner", "editor", "viewer"]


# ─────────────────────────────────────────────────────────────
# TRIP MEMBERS
# ─────────────────────────────────────────────────────────────
class TripMember(BaseModel):
    model_config = ConfigDict(extra="ignore")
    member_id: str
    trip_id: str
    user_id: Optional[str] = None
    invited_email: Optional[EmailStr] = None
    role: Literal["owner", "editor", "viewer"]
    status: Literal["pending", "accepted"] = "accepted"
    created_at: datetime = Field(default_factory=utcnow)


# ─────────────────────────────────────────────────────────────
# FUTURE SCHEMAS — NOT EXPOSED YET (Phase 2+)
# These are documented here so later phases can reuse them.
# ─────────────────────────────────────────────────────────────
#
# class Stop(BaseModel):
#     stop_id: str
#     trip_id: str
#     title: str
#     location: str
#     lat: float
#     lng: float
#     arrival_date: date
#     departure_date: date
#     order_index: int
#     notes: Optional[str] = None
#     created_at: datetime
#
# class Attraction(BaseModel):
#     attraction_id: str
#     stop_id: str
#     trip_id: str
#     title: str
#     category: str  # e.g. "museum", "landmark", "restaurant"
#     scheduled_at: Optional[datetime] = None
#     price_amount: Optional[float] = None
#     price_currency: Optional[str] = None
#     notes: Optional[str] = None
#     completed: bool = False
#
# class Hotel(BaseModel):
#     hotel_id: str
#     stop_id: str
#     trip_id: str
#     name: str
#     check_in: date
#     check_out: date
#     price_amount: float
#     price_currency: str
#     booking_url: Optional[str] = None
#     notes: Optional[str] = None
#
# class Expense(BaseModel):
#     expense_id: str
#     trip_id: str
#     stop_id: Optional[str] = None
#     category: str  # "transport", "food", "lodging", "attraction", "other"
#     amount: float
#     currency: str
#     amount_in_home_currency: float
#     paid_by: str  # user_id
#     description: Optional[str] = None
#     occurred_at: datetime
#     created_at: datetime
#
# class ExchangeRate(BaseModel):
#     rate_id: str
#     base_currency: str
#     quote_currency: str
#     rate: float
#     fetched_at: datetime
