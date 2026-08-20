"""Attractions routes (Phase 2)."""
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import UpdateOne, ASCENDING

from db import db
from auth import require_auth
from models import (
    Attraction,
    AttractionCreate,
    AttractionUpdate,
    ReorderAttractions,
    utcnow,
    new_id,
)
from permissions import get_trip_or_404, require_role

logger = logging.getLogger("twt.attractions")

# Two routers so we can nest under /stops/{stop_id} for list/create,
# and hang PATCH/DELETE/reorder off the trip root.
stop_router = APIRouter(prefix="/trips/{trip_id}/stops/{stop_id}/attractions", tags=["attractions"])
trip_router = APIRouter(prefix="/trips/{trip_id}", tags=["attractions"])


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
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


@stop_router.get("", response_model=List[Attraction])
async def list_attractions(trip_id: str, stop_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    await _get_stop_or_404(trip_id, stop_id)
    docs = await db.attractions.find(
        {"trip_id": trip_id, "stop_id": stop_id}, {"_id": 0}
    ).sort("order", ASCENDING).to_list(1000)
    return [Attraction(**_serialize(d)) for d in docs]


@stop_router.post("", response_model=Attraction, status_code=status.HTTP_201_CREATED)
async def create_attraction(
    trip_id: str,
    stop_id: str,
    body: AttractionCreate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    await _get_stop_or_404(trip_id, stop_id)
    trip = await get_trip_or_404(trip_id)

    currency = body.currency or trip["home_currency"]

    last = await db.attractions.find(
        {"trip_id": trip_id, "stop_id": stop_id}, {"order": 1}
    ).sort("order", -1).limit(1).to_list(1)
    next_order = (last[0]["order"] + 1) if last else 0

    doc = {
        "attraction_id": new_id("att_"),
        "trip_id": trip_id,
        "stop_id": stop_id,
        "order": next_order,
        "name": body.name.strip(),
        "cost": body.cost,
        "currency": currency,
        "booking_link": body.booking_link,
        "scheduled_time": body.scheduled_time,
        "duration_min": body.duration_min,
        "notes": body.notes,
        "created_at": utcnow().isoformat(),
        "updated_at": utcnow().isoformat(),
    }
    await db.attractions.insert_one(doc)
    logger.info("attractions.create trip=%s stop=%s att=%s", trip_id, stop_id, doc["attraction_id"])
    return Attraction(**_serialize(doc))


@trip_router.patch("/attractions/{attraction_id}", response_model=Attraction)
async def update_attraction(
    trip_id: str,
    attraction_id: str,
    body: AttractionUpdate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    att = await db.attractions.find_one(
        {"attraction_id": attraction_id, "trip_id": trip_id}, {"_id": 0}
    )
    if not att:
        raise HTTPException(status_code=404, detail="Attraction not found")

    updates = body.model_dump(exclude_unset=True)
    updates["updated_at"] = utcnow().isoformat()
    await db.attractions.update_one({"attraction_id": attraction_id}, {"$set": updates})
    doc = await db.attractions.find_one({"attraction_id": attraction_id}, {"_id": 0})
    return Attraction(**_serialize(doc))


@trip_router.delete("/attractions/{attraction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attraction(
    trip_id: str,
    attraction_id: str,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    result = await db.attractions.delete_one({"attraction_id": attraction_id, "trip_id": trip_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Attraction not found")
    return None


@trip_router.post("/attractions/reorder", response_model=List[Attraction])
async def reorder_attractions(
    trip_id: str,
    body: ReorderAttractions,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")

    att_ids = [m.attraction_id for m in body.moves]
    stop_ids = list({m.target_stop_id for m in body.moves})

    # Pre-validate: attractions belong to this trip and target stops exist in this trip.
    atts = await db.attractions.find(
        {"trip_id": trip_id, "attraction_id": {"$in": att_ids}},
        {"_id": 0, "attraction_id": 1},
    ).to_list(1000)
    if {a["attraction_id"] for a in atts} != set(att_ids):
        raise HTTPException(status_code=422, detail="Unknown attraction_id in moves")

    stops = await db.stops.find(
        {"trip_id": trip_id, "stop_id": {"$in": stop_ids}},
        {"_id": 0, "stop_id": 1},
    ).to_list(1000)
    if {s["stop_id"] for s in stops} != set(stop_ids):
        raise HTTPException(status_code=422, detail="Unknown target_stop_id in moves")

    ops = [
        UpdateOne(
            {"attraction_id": m.attraction_id, "trip_id": trip_id},
            {"$set": {
                "stop_id": m.target_stop_id,
                "order": m.new_order,
                "updated_at": utcnow().isoformat(),
            }},
        )
        for m in body.moves
    ]
    result = await db.attractions.bulk_write(ops, ordered=True)
    if result.matched_count != len(body.moves):
        raise HTTPException(status_code=500, detail="Partial reorder failure")

    docs = await db.attractions.find({"trip_id": trip_id}, {"_id": 0}).sort("order", ASCENDING).to_list(2000)
    return [Attraction(**_serialize(d)) for d in docs]
