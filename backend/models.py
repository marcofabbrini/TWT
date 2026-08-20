"""
Pydantic models for TWT (Trip Without Trap).

Phase 1: users, trips, trip_members.
Phase 2: stops, attractions.
Future schemas (hotels, expenses, exchange_rates) documented below.
"""
from datetime import datetime, timezone, date
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, HttpUrl
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
# STOP (Phase 2)
# ─────────────────────────────────────────────────────────────
TRANSPORT_MODES = ["car", "plane", "train", "walk", "other"]

_TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"


class StopBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date
    transport_mode: Literal["car", "plane", "train", "walk", "other"] = "car"
    departure_time: Optional[str] = Field(default=None, pattern=_TIME_RE)
    arrival_time: Optional[str] = Field(default=None, pattern=_TIME_RE)
    km_from_prev: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must be greater than or equal to start_date")
        return v


class StopCreate(StopBase):
    pass


class StopUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    location: Optional[str] = Field(default=None, min_length=1, max_length=200)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    transport_mode: Optional[Literal["car", "plane", "train", "walk", "other"]] = None
    departure_time: Optional[str] = Field(default=None, pattern=_TIME_RE)
    arrival_time: Optional[str] = Field(default=None, pattern=_TIME_RE)
    km_from_prev: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=2000)


class Stop(StopBase):
    model_config = ConfigDict(extra="ignore")
    stop_id: str
    trip_id: str
    order: int
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ReorderStops(BaseModel):
    stop_ids: List[str] = Field(min_length=1)


# ─────────────────────────────────────────────────────────────
# ATTRACTION (Phase 2)
# ─────────────────────────────────────────────────────────────
class AttractionBase(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    cost: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    booking_link: Optional[str] = Field(default=None, max_length=500)
    scheduled_time: Optional[str] = Field(default=None, pattern=_TIME_RE)
    duration_min: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v):
        if v is None:
            return v
        v = v.upper()
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {SUPPORTED_CURRENCIES}")
        return v

    @field_validator("booking_link")
    @classmethod
    def _link_scheme(cls, v):
        if v is None or v == "":
            return v
        v = v.strip()
        low = v.lower()
        if not (low.startswith("http://") or low.startswith("https://")):
            raise ValueError("booking_link must start with http:// or https://")
        return v


class AttractionCreate(AttractionBase):
    pass


class AttractionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=140)
    cost: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    booking_link: Optional[str] = Field(default=None, max_length=500)
    scheduled_time: Optional[str] = Field(default=None, pattern=_TIME_RE)
    duration_min: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v):
        if v is None:
            return v
        v = v.upper()
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {SUPPORTED_CURRENCIES}")
        return v

    @field_validator("booking_link")
    @classmethod
    def _link_scheme(cls, v):
        if v is None or v == "":
            return v
        v = v.strip()
        low = v.lower()
        if not (low.startswith("http://") or low.startswith("https://")):
            raise ValueError("booking_link must start with http:// or https://")
        return v


class Attraction(AttractionBase):
    model_config = ConfigDict(extra="ignore")
    attraction_id: str
    trip_id: str
    stop_id: str
    order: int
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AttractionMove(BaseModel):
    attraction_id: str
    target_stop_id: str
    new_order: int = Field(ge=0)


class ReorderAttractions(BaseModel):
    moves: List[AttractionMove] = Field(min_length=1)


# ─────────────────────────────────────────────────────────────
# FUTURE SCHEMAS — NOT EXPOSED YET (Phase 3+)
# ─────────────────────────────────────────────────────────────
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
#     category: str
#     amount: float
#     currency: str
#     amount_in_home_currency: float
#     paid_by: str
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
