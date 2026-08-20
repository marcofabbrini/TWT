"""Notifications + KM recompute helpers (Phase 5)."""
import logging
from datetime import date, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from db import db
from auth import require_auth
from permissions import require_role
from services.distance import recompute_trip_km

logger = logging.getLogger("twt.notifications")

trip_router = APIRouter(prefix="/trips/{trip_id}", tags=["km"])
notif_router = APIRouter(prefix="/notifications", tags=["notifications"])


@trip_router.post("/recompute-km")
async def recompute_km(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "editor")
    result = await recompute_trip_km(trip_id)
    logger.info("km.recompute trip=%s updated=%s errors=%s",
                trip_id, result["updated_count"], len(result["errors"]))
    return result


def _to_date(v):
    if isinstance(v, str):
        return date.fromisoformat(v)
    if isinstance(v, datetime):
        return v.date()
    return v


@notif_router.get("/cancellation-alerts")
async def cancellation_alerts(current_user: dict = Depends(require_auth)):
    """Aggregate all hotels across trips where the current user is an accepted
    member, whose cancellation_deadline is within the next 7 days (inclusive)
    or already past. Sorted by days_until asc."""
    memberships = await db.trip_members.find(
        {"user_id": current_user["user_id"], "status": "accepted"},
        {"_id": 0, "trip_id": 1},
    ).to_list(500)
    trip_ids = [m["trip_id"] for m in memberships]
    if not trip_ids:
        return []

    trips = await db.trips.find(
        {"trip_id": {"$in": trip_ids}}, {"_id": 0, "trip_id": 1, "title": 1}
    ).to_list(500)
    trip_by_id = {t["trip_id"]: t for t in trips}

    hotels = await db.hotels.find(
        {"trip_id": {"$in": trip_ids}, "cancellation_deadline": {"$ne": None}},
        {"_id": 0},
    ).to_list(2000)

    today = date.today()
    stop_cache = {}
    out = []
    for h in hotels:
        deadline = _to_date(h.get("cancellation_deadline"))
        if not deadline:
            continue
        days_until = (deadline - today).days
        if days_until > 7:
            continue

        sid = h["stop_id"]
        if sid not in stop_cache:
            s = await db.stops.find_one({"stop_id": sid}, {"_id": 0, "title": 1})
            stop_cache[sid] = (s or {}).get("title", "")
        severity = "red" if days_until <= 3 else "yellow"

        out.append({
            "trip_id": h["trip_id"],
            "trip_title": trip_by_id.get(h["trip_id"], {}).get("title", ""),
            "hotel_id": h["hotel_id"],
            "hotel_name": h["name"],
            "stop_title": stop_cache[sid],
            "cancellation_deadline": deadline.isoformat(),
            "days_until": days_until,
            "severity": severity,
        })

    out.sort(key=lambda x: x["days_until"])
    return out
