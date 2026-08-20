"""Trips + Trip Members routes (Phase 1)."""
import logging
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from db import db
from models import Trip, TripCreate, TripUpdate, TripWithRole, utcnow, new_id
from auth import require_auth
from versioning import bump_version

logger = logging.getLogger("twt.trips")
router = APIRouter(prefix="/trips", tags=["trips"])


def _serialize_trip(doc: dict) -> dict:
    """Convert stored dates/datetimes for Pydantic parsing."""
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


async def _get_membership(trip_id: str, user_id: str) -> Optional[dict]:
    return await db.trip_members.find_one(
        {"trip_id": trip_id, "user_id": user_id, "status": "accepted"},
        {"_id": 0},
    )


@router.post("", response_model=Trip, status_code=status.HTTP_201_CREATED)
async def create_trip(body: TripCreate, current_user: dict = Depends(require_auth)):
    trip_id = new_id("trip_")
    trip_doc = {
        "trip_id": trip_id,
        "owner_id": current_user["user_id"],
        "title": body.title.strip(),
        "home_currency": body.home_currency,
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "cover_image_url": body.cover_image_url,
        "created_at": utcnow().isoformat(),
        "updated_at": utcnow().isoformat(),
        "version": 0,
    }
    await db.trips.insert_one(trip_doc)

    member_doc = {
        "member_id": new_id("mem_"),
        "trip_id": trip_id,
        "user_id": current_user["user_id"],
        "invited_email": current_user["email"],
        "role": "owner",
        "status": "accepted",
        "created_at": utcnow().isoformat(),
    }
    await db.trip_members.insert_one(member_doc)

    logger.info("trips.create trip_id=%s owner=%s", trip_id, current_user["user_id"])
    return Trip(**_serialize_trip(trip_doc))


@router.get("", response_model=List[TripWithRole])
async def list_trips(current_user: dict = Depends(require_auth)):
    memberships = await db.trip_members.find(
        {"user_id": current_user["user_id"], "status": "accepted"},
        {"_id": 0},
    ).to_list(500)
    if not memberships:
        return []

    role_by_trip = {m["trip_id"]: m["role"] for m in memberships}
    trip_ids = list(role_by_trip.keys())
    trip_docs = await db.trips.find({"trip_id": {"$in": trip_ids}}, {"_id": 0}).to_list(500)

    result = []
    for d in trip_docs:
        s = _serialize_trip(d)
        s["role"] = role_by_trip.get(d["trip_id"], "viewer")
        result.append(TripWithRole(**s))
    # Sort by start_date desc
    result.sort(key=lambda t: t.start_date, reverse=True)
    return result


@router.get("/{trip_id}", response_model=TripWithRole)
async def get_trip(trip_id: str, current_user: dict = Depends(require_auth)):
    membership = await _get_membership(trip_id, current_user["user_id"])
    if not membership:
        raise HTTPException(status_code=404, detail="Trip not found")

    trip_doc = await db.trips.find_one({"trip_id": trip_id}, {"_id": 0})
    if not trip_doc:
        raise HTTPException(status_code=404, detail="Trip not found")

    s = _serialize_trip(trip_doc)
    s["role"] = membership["role"]
    return TripWithRole(**s)


@router.patch("/{trip_id}", response_model=Trip)
async def update_trip(
    trip_id: str,
    body: TripUpdate,
    current_user: dict = Depends(require_auth),
):
    trip = await db.trips.find_one({"trip_id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip["owner_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the owner can edit the trip")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return Trip(**_serialize_trip(trip))

    # Effective start/end for validation.
    from datetime import date as _date
    def _to_date(v):
        return _date.fromisoformat(v) if isinstance(v, str) else v

    eff_start = _to_date(updates.get("start_date") or trip["start_date"])
    eff_end = _to_date(updates.get("end_date") or trip["end_date"])
    if eff_end < eff_start:
        raise HTTPException(status_code=422, detail="end_date must be >= start_date")

    # If dates changed, ensure no stop falls outside the new range.
    if "start_date" in updates or "end_date" in updates:
        stops = await db.stops.find(
            {"trip_id": trip_id},
            {"_id": 0, "stop_id": 1, "title": 1, "start_date": 1, "end_date": 1},
        ).to_list(2000)
        out_of_range = []
        for s in stops:
            ss = _to_date(s["start_date"])
            se = _to_date(s["end_date"])
            if ss < eff_start or se > eff_end:
                out_of_range.append({"stop_id": s["stop_id"], "title": s["title"]})
        if out_of_range:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Some stops fall outside the new trip range",
                    "stops_out_of_range": out_of_range,
                    "new_range": {"start": eff_start.isoformat(), "end": eff_end.isoformat()},
                },
            )

    # Serialize dates for storage.
    for k in ("start_date", "end_date"):
        if k in updates and hasattr(updates[k], "isoformat"):
            updates[k] = updates[k].isoformat()
    updates["updated_at"] = utcnow().isoformat()
    if "title" in updates and updates["title"]:
        updates["title"] = updates["title"].strip()

    await db.trips.update_one({"trip_id": trip_id}, {"$set": updates})
    await bump_version(trip_id, current_user["user_id"])
    logger.info("trips.update trip_id=%s by=%s fields=%s", trip_id, current_user["user_id"], list(updates.keys()))
    doc = await db.trips.find_one({"trip_id": trip_id}, {"_id": 0})
    return Trip(**_serialize_trip(doc))



@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(trip_id: str, current_user: dict = Depends(require_auth)):
    trip_doc = await db.trips.find_one({"trip_id": trip_id}, {"_id": 0})
    if not trip_doc:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip_doc["owner_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the owner can delete this trip")

    # Cascade: attractions → stops → hotels → expenses → exchange_rates → trip_members → trip.
    await db.attractions.delete_many({"trip_id": trip_id})
    await db.stops.delete_many({"trip_id": trip_id})
    await db.hotels.delete_many({"trip_id": trip_id})
    await db.expenses.delete_many({"trip_id": trip_id})
    await db.exchange_rates.delete_many({"trip_id": trip_id})
    await db.trip_members.delete_many({"trip_id": trip_id})
    await db.trips.delete_one({"trip_id": trip_id})
    logger.info("trips.delete trip_id=%s by=%s (cascade)", trip_id, current_user["user_id"])
    return None
