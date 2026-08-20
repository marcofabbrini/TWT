"""Hotels routes (Phase 3)."""
import logging
from datetime import date, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from db import db
from auth import require_auth
from models import Hotel, HotelCreate, HotelUpdate, utcnow, new_id
from permissions import get_trip_or_404, require_role

logger = logging.getLogger("twt.hotels")

stop_router = APIRouter(prefix="/trips/{trip_id}/stops/{stop_id}/hotels", tags=["hotels"])
trip_router = APIRouter(prefix="/trips/{trip_id}", tags=["hotels"])


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("check_in", "check_out", "cancellation_deadline"):
        v = out.get(k)
        if isinstance(v, str):
            out[k] = date.fromisoformat(v)
        elif isinstance(v, datetime):
            out[k] = v.date()
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, str):
            out[k] = datetime.fromisoformat(v)
    return out


async def _get_stop_or_404(trip_id: str, stop_id: str) -> dict:
    s = await db.stops.find_one({"stop_id": stop_id, "trip_id": trip_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Stop not found")
    return s


@stop_router.get("", response_model=List[Hotel])
async def list_hotels(trip_id: str, stop_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    await _get_stop_or_404(trip_id, stop_id)
    docs = await db.hotels.find(
        {"trip_id": trip_id, "stop_id": stop_id}, {"_id": 0}
    ).sort("check_in", 1).to_list(500)
    return [Hotel(**_serialize(d)) for d in docs]


@stop_router.post("", response_model=Hotel, status_code=status.HTTP_201_CREATED)
async def create_hotel(
    trip_id: str,
    stop_id: str,
    body: HotelCreate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    await _get_stop_or_404(trip_id, stop_id)
    trip = await get_trip_or_404(trip_id)
    currency = body.currency or trip["home_currency"]

    doc = {
        "hotel_id": new_id("hot_"),
        "trip_id": trip_id,
        "stop_id": stop_id,
        "name": body.name.strip(),
        "location": (body.location or "").strip() or None,
        "check_in": body.check_in.isoformat(),
        "check_out": body.check_out.isoformat(),
        "cost": body.cost,
        "currency": currency,
        "booking_link": body.booking_link,
        "cancellation_deadline": body.cancellation_deadline.isoformat()
            if body.cancellation_deadline else None,
        "notes": body.notes,
        "created_at": utcnow().isoformat(),
        "updated_at": utcnow().isoformat(),
    }
    await db.hotels.insert_one(doc)
    logger.info("hotels.create trip=%s stop=%s hotel=%s", trip_id, stop_id, doc["hotel_id"])
    return Hotel(**_serialize(doc))


@trip_router.patch("/hotels/{hotel_id}", response_model=Hotel)
async def update_hotel(
    trip_id: str,
    hotel_id: str,
    body: HotelUpdate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    existing = await db.hotels.find_one({"hotel_id": hotel_id, "trip_id": trip_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Hotel not found")

    updates = body.model_dump(exclude_unset=True)
    for k in ("check_in", "check_out", "cancellation_deadline"):
        if k in updates and isinstance(updates[k], date):
            updates[k] = updates[k].isoformat()

    # Effective range revalidation
    eff_in = updates.get("check_in", existing["check_in"])
    eff_out = updates.get("check_out", existing["check_out"])
    if isinstance(eff_in, str): eff_in = date.fromisoformat(eff_in)
    if isinstance(eff_out, str): eff_out = date.fromisoformat(eff_out)
    if eff_out < eff_in:
        raise HTTPException(status_code=422, detail="check_out must be >= check_in")

    updates["updated_at"] = utcnow().isoformat()
    await db.hotels.update_one({"hotel_id": hotel_id}, {"$set": updates})
    doc = await db.hotels.find_one({"hotel_id": hotel_id}, {"_id": 0})
    return Hotel(**_serialize(doc))


@trip_router.delete("/hotels/{hotel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hotel(
    trip_id: str,
    hotel_id: str,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    result = await db.hotels.delete_one({"hotel_id": hotel_id, "trip_id": trip_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return None
