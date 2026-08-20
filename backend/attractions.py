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
from versioning import bump_version

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


async def _renormalize_stop_attractions(
    trip_id: str,
    stop_id: str,
    moved_ids: set | None = None,
) -> None:
    """Reassign order = 0..N-1 within (trip_id, stop_id).

    Sort key: (order asc, moved-first, created_at asc). Moved items win ties on
    order so a "drop at position N" over an existing item keeps the intended slot.
    """
    moved_ids = moved_ids or set()
    docs = await db.attractions.find(
        {"trip_id": trip_id, "stop_id": stop_id},
        {"_id": 0, "attraction_id": 1, "order": 1, "created_at": 1},
    ).to_list(2000)
    if not docs:
        return
    docs.sort(key=lambda d: (
        d.get("order", 0),
        0 if d["attraction_id"] in moved_ids else 1,
        d.get("created_at") or "",
    ))
    ops = [
        UpdateOne(
            {"attraction_id": d["attraction_id"], "trip_id": trip_id},
            {"$set": {"order": i}},
        )
        for i, d in enumerate(docs)
        if d.get("order") != i
    ]
    if ops:
        await db.attractions.bulk_write(ops, ordered=False)


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
    await bump_version(trip_id, current_user["user_id"])
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
    await bump_version(trip_id, current_user["user_id"])
    doc = await db.attractions.find_one({"attraction_id": attraction_id}, {"_id": 0})
    return Attraction(**_serialize(doc))


@trip_router.delete("/attractions/{attraction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attraction(
    trip_id: str,
    attraction_id: str,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    existing = await db.attractions.find_one(
        {"attraction_id": attraction_id, "trip_id": trip_id}, {"_id": 0, "stop_id": 1}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Attraction not found")
    await db.attractions.delete_one({"attraction_id": attraction_id, "trip_id": trip_id})
    await _renormalize_stop_attractions(trip_id, existing["stop_id"])
    await bump_version(trip_id, current_user["user_id"])
    return None


@trip_router.post("/attractions/reorder", response_model=List[Attraction])
async def reorder_attractions(
    trip_id: str,
    body: ReorderAttractions,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")

    att_ids = [m.attraction_id for m in body.moves]
    target_stop_ids = list({m.target_stop_id for m in body.moves})

    # Pre-validate: attractions belong to this trip and target stops exist in this trip.
    atts = await db.attractions.find(
        {"trip_id": trip_id, "attraction_id": {"$in": att_ids}},
        {"_id": 0},
    ).to_list(1000)
    if {a["attraction_id"] for a in atts} != set(att_ids):
        raise HTTPException(status_code=422, detail="Unknown attraction_id in moves")

    source_stop_ids = {a["stop_id"] for a in atts}

    stops = await db.stops.find(
        {"trip_id": trip_id, "stop_id": {"$in": target_stop_ids}},
        {"_id": 0, "stop_id": 1},
    ).to_list(1000)
    if {s["stop_id"] for s in stops} != set(target_stop_ids):
        raise HTTPException(status_code=422, detail="Unknown target_stop_id in moves")

    # Compute the FINAL canonical layout in Python across every touched stop.
    # This handles single moves, multi-item batches into the same stop, and
    # same-stop reorders — the drop position is always honoured and orders
    # come out contiguous 0..N-1 without a separate normalization pass.
    touched_stops = source_stop_ids | set(target_stop_ids)
    all_docs = await db.attractions.find(
        {"trip_id": trip_id, "stop_id": {"$in": list(touched_stops)}},
        {"_id": 0},
    ).sort([("order", ASCENDING), ("created_at", ASCENDING)]).to_list(5000)
    doc_by_id = {d["attraction_id"]: d for d in all_docs}
    moves_by_id = {m.attraction_id: m for m in body.moves}

    now_iso = utcnow().isoformat()
    final_updates = []  # (attraction_id, new_stop_id, new_order)

    for target_sid in touched_stops:
        # Items that STAY in this stop (never appear in moves).
        stay = [
            d for d in all_docs
            if d["stop_id"] == target_sid and d["attraction_id"] not in moves_by_id
        ]
        stay.sort(key=lambda d: (d.get("order", 0), d.get("created_at") or ""))

        # Items landing IN this stop via a move (includes same-stop reorders).
        inbound = sorted(
            [m for m in body.moves if m.target_stop_id == target_sid],
            key=lambda m: (m.new_order, m.attraction_id),
        )

        # Insert each inbound at its requested position — later inserts shift
        # earlier inbound entries, keeping the moved block contiguous when
        # multiple items are dropped at consecutive positions.
        final_list = list(stay)
        for m in inbound:
            insert_at = max(0, min(m.new_order, len(final_list)))
            final_list.insert(insert_at, doc_by_id[m.attraction_id])

        for i, d in enumerate(final_list):
            final_updates.append((d["attraction_id"], target_sid, i))

    # Also renormalize any SOURCE stops that lost items (target_stop != source).
    depleted_sources = source_stop_ids - set(target_stop_ids)
    for src_sid in depleted_sources:
        remaining = [
            d for d in all_docs
            if d["stop_id"] == src_sid and d["attraction_id"] not in moves_by_id
        ]
        remaining.sort(key=lambda d: (d.get("order", 0), d.get("created_at") or ""))
        for i, d in enumerate(remaining):
            final_updates.append((d["attraction_id"], src_sid, i))

    ops = [
        UpdateOne(
            {"attraction_id": aid, "trip_id": trip_id},
            {"$set": {"stop_id": sid, "order": i, "updated_at": now_iso}},
        )
        for aid, sid, i in final_updates
    ]
    if ops:
        result = await db.attractions.bulk_write(ops, ordered=True)
        if result.matched_count != len(ops):
            raise HTTPException(status_code=500, detail="Partial reorder failure")

    await bump_version(trip_id, current_user["user_id"])
    docs = await db.attractions.find({"trip_id": trip_id}, {"_id": 0}).sort("order", ASCENDING).to_list(2000)
    return [Attraction(**_serialize(d)) for d in docs]
