"""Shared permission helpers for trip-scoped resources."""
from datetime import date, datetime
from fastapi import HTTPException, Depends
from typing import Literal

from db import db
from auth import require_auth

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


async def get_trip_or_404(trip_id: str) -> dict:
    trip = await db.trips.find_one({"trip_id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


async def get_membership_or_404(trip_id: str, user_id: str) -> dict:
    m = await db.trip_members.find_one(
        {"trip_id": trip_id, "user_id": user_id, "status": "accepted"},
        {"_id": 0},
    )
    if not m:
        raise HTTPException(status_code=404, detail="Trip not found")
    return m


async def require_role(
    trip_id: str,
    user_id: str,
    min_role: Literal["viewer", "editor", "owner"] = "viewer",
) -> dict:
    m = await get_membership_or_404(trip_id, user_id)
    if ROLE_RANK[m["role"]] < ROLE_RANK[min_role]:
        raise HTTPException(status_code=403, detail=f"Requires {min_role} role")
    return m


def trip_date_range(trip: dict) -> tuple[date, date]:
    """Return (start_date, end_date) for the trip as `date` objects."""
    def _to_date(v):
        if isinstance(v, str):
            return date.fromisoformat(v)
        if isinstance(v, datetime):
            return v.date()
        return v
    return _to_date(trip["start_date"]), _to_date(trip["end_date"])
