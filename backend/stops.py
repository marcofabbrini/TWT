"""Stops routes (Phase 2)."""
import logging
from datetime import date, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import UpdateOne, ASCENDING

from db import db
from auth import require_auth
from models import Stop, StopCreate, StopUpdate, ReorderStops, utcnow, new_id
from permissions import get_trip_or_404, require_role, trip_date_range

logger = logging.getLogger("twt.stops")
router = APIRouter(prefix="/trips/{trip_id}/stops", tags=["stops"])


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("start_date", "end_date"):
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


def _check_within_trip_range(trip: dict, start: date, end: date) -> None:
    ts, te = trip_date_range(trip)
    if start < ts or end > te:
        raise HTTPException(
            status_code=422,
            detail=f"Stop dates must fall within trip range {ts.isoformat()} – {te.isoformat()}",
        )


@router.get("", response_model=List[Stop])
async def list_stops(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    docs = await db.stops.find({"trip_id": trip_id}, {"_id": 0}).sort("order", ASCENDING).to_list(500)
    return [Stop(**_serialize(d)) for d in docs]


@router.post("", response_model=Stop, status_code=status.HTTP_201_CREATED)
async def create_stop(trip_id: str, body: StopCreate, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "editor")
    trip = await get_trip_or_404(trip_id)
    _check_within_trip_range(trip, body.start_date, body.end_date)

    last = await db.stops.find({"trip_id": trip_id}, {"order": 1}).sort("order", -1).limit(1).to_list(1)
    next_order = (last[0]["order"] + 1) if last else 0

    doc = {
        "stop_id": new_id("stop_"),
        "trip_id": trip_id,
        "order": next_order,
        "title": body.title.strip(),
        "location": body.location.strip(),
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "transport_mode": body.transport_mode,
        "departure_time": body.departure_time,
        "arrival_time": body.arrival_time,
        "km_from_prev": body.km_from_prev,
        "notes": body.notes,
        "created_at": utcnow().isoformat(),
        "updated_at": utcnow().isoformat(),
    }
    await db.stops.insert_one(doc)
    logger.info("stops.create trip=%s stop=%s", trip_id, doc["stop_id"])
    return Stop(**_serialize(doc))


@router.patch("/{stop_id}", response_model=Stop)
async def update_stop(
    trip_id: str,
    stop_id: str,
    body: StopUpdate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    stop = await db.stops.find_one({"stop_id": stop_id, "trip_id": trip_id}, {"_id": 0})
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found")

    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k in body.model_fields_set}
    # Convert dates to isoformat for storage.
    for k in ("start_date", "end_date"):
        if k in updates and isinstance(updates[k], date):
            updates[k] = updates[k].isoformat()

    # Recompute effective start/end for range validation.
    def _pick(field: str) -> date:
        v = updates.get(field, stop[field])
        return date.fromisoformat(v) if isinstance(v, str) else v

    if "start_date" in updates or "end_date" in updates:
        eff_start = _pick("start_date")
        eff_end = _pick("end_date")
        if eff_end < eff_start:
            raise HTTPException(status_code=422, detail="end_date must be >= start_date")
        trip = await get_trip_or_404(trip_id)
        _check_within_trip_range(trip, eff_start, eff_end)

    updates["updated_at"] = utcnow().isoformat()
    await db.stops.update_one({"stop_id": stop_id}, {"$set": updates})
    doc = await db.stops.find_one({"stop_id": stop_id}, {"_id": 0})
    return Stop(**_serialize(doc))


@router.delete("/{stop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stop(trip_id: str, stop_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "editor")
    stop = await db.stops.find_one({"stop_id": stop_id, "trip_id": trip_id}, {"_id": 0})
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found")
    await db.attractions.delete_many({"trip_id": trip_id, "stop_id": stop_id})
    await db.stops.delete_one({"stop_id": stop_id})

    # Renormalize remaining stops.order to 0..N-1 (tie-break on created_at).
    remaining = await db.stops.find(
        {"trip_id": trip_id},
        {"_id": 0, "stop_id": 1, "order": 1, "created_at": 1},
    ).sort([("order", ASCENDING), ("created_at", ASCENDING)]).to_list(1000)
    ops = [
        UpdateOne(
            {"stop_id": d["stop_id"], "trip_id": trip_id},
            {"$set": {"order": i}},
        )
        for i, d in enumerate(remaining)
        if d.get("order") != i
    ]
    if ops:
        await db.stops.bulk_write(ops, ordered=False)

    logger.info("stops.delete trip=%s stop=%s", trip_id, stop_id)
    return None


@router.post("/reorder", response_model=List[Stop])
async def reorder_stops(
    trip_id: str,
    body: ReorderStops,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")

    # Pre-validate: stop_ids MUST be a full permutation of every stop in the trip.
    all_trip_stops = await db.stops.find(
        {"trip_id": trip_id}, {"_id": 0, "stop_id": 1}
    ).to_list(1000)
    trip_ids = {d["stop_id"] for d in all_trip_stops}
    body_ids = set(body.stop_ids)
    if len(body.stop_ids) != len(body_ids):
        raise HTTPException(status_code=422, detail="stop_ids contains duplicates")
    if body_ids != trip_ids:
        raise HTTPException(
            status_code=422,
            detail="stop_ids must be a full permutation of the trip's stops",
        )

    ops = [
        UpdateOne(
            {"stop_id": sid, "trip_id": trip_id},
            {"$set": {"order": i, "updated_at": utcnow().isoformat()}},
        )
        for i, sid in enumerate(body.stop_ids)
    ]
    result = await db.stops.bulk_write(ops, ordered=True)
    if result.matched_count != len(body.stop_ids):
        raise HTTPException(status_code=500, detail="Partial reorder failure")

    docs = await db.stops.find({"trip_id": trip_id}, {"_id": 0}).sort("order", ASCENDING).to_list(500)
    return [Stop(**_serialize(d)) for d in docs]
