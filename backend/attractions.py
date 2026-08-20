"""Attractions routes (Phase 2)."""
import logging
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
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


def _to_date(v) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return None


async def _resolve_stop_for_date(trip_id: str, when: date) -> Optional[dict]:
    """Return the stop that best covers `when`. If multiple overlap, prefer the
    one with the largest start_date (the most-recently entered one).
    """
    stops = await db.stops.find(
        {"trip_id": trip_id},
        {"_id": 0, "stop_id": 1, "start_date": 1, "end_date": 1, "order": 1, "title": 1},
    ).to_list(2000)
    best = None
    best_start = None
    for s in stops:
        sd = _to_date(s.get("start_date"))
        ed = _to_date(s.get("end_date"))
        if sd is None or ed is None:
            continue
        if sd <= when <= ed:
            if best_start is None or sd > best_start:
                best = s
                best_start = sd
    return best


def _validate_scheduled_date_against_stop(stop: dict, when: Optional[date]) -> None:
    if when is None:
        return
    sd = _to_date(stop.get("start_date"))
    ed = _to_date(stop.get("end_date"))
    if sd is None or ed is None:
        return
    if when < sd or when > ed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"scheduled_date must be within stop range "
                f"({sd.isoformat()} → {ed.isoformat()})"
            ),
        )


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, str):
            out[k] = datetime.fromisoformat(v)
    v = out.get("scheduled_date")
    if isinstance(v, str):
        out["scheduled_date"] = date.fromisoformat(v[:10])
    elif isinstance(v, datetime):
        out["scheduled_date"] = v.date()
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

    # Validate scheduled_date (if provided) is within THIS stop's range.
    stop_doc = await _get_stop_or_404(trip_id, stop_id)
    _validate_scheduled_date_against_stop(stop_doc, body.scheduled_date)

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
        "scheduled_date": body.scheduled_date.isoformat() if body.scheduled_date else None,
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
    if "scheduled_date" in updates and updates["scheduled_date"] is not None:
        # Validate against current stop's range.
        stop_doc = await _get_stop_or_404(trip_id, att["stop_id"])
        _validate_scheduled_date_against_stop(stop_doc, _to_date(updates["scheduled_date"]))
        updates["scheduled_date"] = _to_date(updates["scheduled_date"]).isoformat()
    updates["updated_at"] = utcnow().isoformat()
    await db.attractions.update_one({"attraction_id": attraction_id}, {"$set": updates})
    await bump_version(trip_id, current_user["user_id"])
    doc = await db.attractions.find_one({"attraction_id": attraction_id}, {"_id": 0})
    return Attraction(**_serialize(doc))


# ────────────────────────────────────────────────────────────────
# Day-centric schedule endpoint (Sprint C).
# ────────────────────────────────────────────────────────────────
class ScheduleBody(BaseModel):
    """Body for PATCH .../attractions/{id}/schedule."""
    scheduled_date: Optional[date] = None
    target_stop_id: Optional[str] = None
    new_order: Optional[int] = Field(default=None, ge=0)


@trip_router.patch("/attractions/{attraction_id}/schedule", response_model=Attraction)
async def schedule_attraction(
    trip_id: str,
    attraction_id: str,
    body: ScheduleBody,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    att = await db.attractions.find_one(
        {"attraction_id": attraction_id, "trip_id": trip_id}, {"_id": 0}
    )
    if not att:
        raise HTTPException(status_code=404, detail="Attraction not found")

    # Resolve final (stop_id, scheduled_date).
    when = body.scheduled_date  # may be None → means "unschedule"
    new_stop_id: Optional[str] = None

    if body.target_stop_id:
        target_stop = await _get_stop_or_404(trip_id, body.target_stop_id)
        _validate_scheduled_date_against_stop(target_stop, when)
        new_stop_id = target_stop["stop_id"]
    elif when is not None:
        # Derive stop from date.
        derived = await _resolve_stop_for_date(trip_id, when)
        if not derived:
            raise HTTPException(
                status_code=422,
                detail=f"No stop covers {when.isoformat()} — assign a target_stop_id or pick another date.",
            )
        new_stop_id = derived["stop_id"]
    else:
        # scheduled_date=null and no target_stop_id → just clear the date.
        new_stop_id = att["stop_id"]

    old_stop_id = att["stop_id"]
    updates = {
        "stop_id": new_stop_id,
        "scheduled_date": when.isoformat() if when else None,
        "updated_at": utcnow().isoformat(),
    }

    # If we're moving to a different stop, compute a natural order.
    if new_stop_id != old_stop_id:
        if body.new_order is not None:
            updates["order"] = body.new_order
        else:
            # Append to the tail of the target stop.
            last = await db.attractions.find(
                {"trip_id": trip_id, "stop_id": new_stop_id},
                {"order": 1},
            ).sort("order", -1).limit(1).to_list(1)
            updates["order"] = (last[0]["order"] + 1) if last else 0
    elif body.new_order is not None:
        updates["order"] = body.new_order

    await db.attractions.update_one({"attraction_id": attraction_id}, {"$set": updates})

    # Renormalize both source and target when the stop changed.
    if new_stop_id != old_stop_id:
        await _renormalize_stop_attractions(trip_id, old_stop_id)
        await _renormalize_stop_attractions(
            trip_id, new_stop_id, moved_ids={attraction_id}
        )
    elif body.new_order is not None:
        await _renormalize_stop_attractions(
            trip_id, new_stop_id, moved_ids={attraction_id}
        )

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
    # Optional per-move scheduled_date carry-through.
    date_ops = []
    for m in body.moves:
        if "scheduled_date" not in m.model_fields_set:
            continue
        target_stop = next((s for s in stops if s["stop_id"] == m.target_stop_id), None)
        if m.scheduled_date is not None:
            # Validate against target stop.
            full_stop = await db.stops.find_one(
                {"trip_id": trip_id, "stop_id": m.target_stop_id},
                {"_id": 0, "start_date": 1, "end_date": 1},
            )
            _validate_scheduled_date_against_stop(full_stop or {}, m.scheduled_date)
        date_ops.append(
            UpdateOne(
                {"attraction_id": m.attraction_id, "trip_id": trip_id},
                {"$set": {
                    "scheduled_date": m.scheduled_date.isoformat() if m.scheduled_date else None,
                    "updated_at": now_iso,
                }},
            )
        )
    if ops:
        result = await db.attractions.bulk_write(ops, ordered=True)
        if result.matched_count != len(ops):
            raise HTTPException(status_code=500, detail="Partial reorder failure")
    if date_ops:
        await db.attractions.bulk_write(date_ops, ordered=False)

    await bump_version(trip_id, current_user["user_id"])
    docs = await db.attractions.find({"trip_id": trip_id}, {"_id": 0}).sort("order", ASCENDING).to_list(2000)
    return [Attraction(**_serialize(d)) for d in docs]
