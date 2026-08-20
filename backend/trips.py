"""Trips + Trip Members routes (Phase 1)."""
import asyncio
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
    home_location = (body.home_location or "").strip() or None
    trip_doc = {
        "trip_id": trip_id,
        "owner_id": current_user["user_id"],
        "title": body.title.strip(),
        "home_currency": body.home_currency,
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "cover_image_url": body.cover_image_url,
        "home_location": home_location,
        "has_return": bool(body.has_return),
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


@router.get("")
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

    # Batch-fetch all children in 5 queries total (not N*5).
    stops_docs, hotels_docs, atts_docs, exps_docs, rates_docs = await asyncio.gather(
        db.stops.find(
            {"trip_id": {"$in": trip_ids}},
            {"_id": 0, "trip_id": 1, "km_from_prev": 1},
        ).to_list(20000),
        db.hotels.find(
            {"trip_id": {"$in": trip_ids}},
            {"_id": 0, "trip_id": 1, "cost": 1, "currency": 1},
        ).to_list(20000),
        db.attractions.find(
            {"trip_id": {"$in": trip_ids}, "cost": {"$ne": None, "$gt": 0}},
            {"_id": 0, "trip_id": 1, "cost": 1, "currency": 1},
        ).to_list(20000),
        db.expenses.find(
            {"trip_id": {"$in": trip_ids}},
            {"_id": 0, "trip_id": 1, "cost": 1, "currency": 1},
        ).to_list(20000),
        db.exchange_rates.find(
            {"trip_id": {"$in": trip_ids}},
            {"_id": 0, "trip_id": 1, "from_currency": 1, "to_currency": 1, "rate": 1},
        ).to_list(20000),
    )

    from collections import defaultdict
    km_by = defaultdict(list)
    for s in stops_docs:
        if s.get("km_from_prev") is not None:
            km_by[s["trip_id"]].append(s["km_from_prev"])

    items_by = defaultdict(list)  # trip_id -> [(cost, currency)]
    for h in hotels_docs:
        items_by[h["trip_id"]].append((h.get("cost") or 0.0, h.get("currency")))
    for a in atts_docs:
        items_by[a["trip_id"]].append((a["cost"], a.get("currency")))
    for e in exps_docs:
        items_by[e["trip_id"]].append((e.get("cost") or 0.0, e.get("currency")))

    rates_by = defaultdict(dict)
    for r in rates_docs:
        rates_by[r["trip_id"]][(r["from_currency"], r["to_currency"])] = r["rate"]

    result = []
    for d in trip_docs:
        s = _serialize_trip(d)
        tid = d["trip_id"]
        s["role"] = role_by_trip.get(tid, "viewer")

        home = d["home_currency"]
        total_cost = 0.0
        has_missing = False
        for cost, cur in items_by.get(tid, []):
            if cost is None:
                continue
            cur = cur or home
            if cur == home:
                total_cost += float(cost)
                continue
            r = rates_by[tid].get((cur, home))
            if r is None:
                has_missing = True
                continue
            total_cost += float(cost) * r

        kms = km_by.get(tid, [])
        total_km = round(sum(kms), 1) if kms else None

        item = TripWithRole(**s).model_dump()
        # Convert start_date/end_date to ISO strings for the response.
        for k in ("start_date", "end_date"):
            if hasattr(item.get(k), "isoformat"):
                item[k] = item[k].isoformat()
        for k in ("created_at", "updated_at"):
            if hasattr(item.get(k), "isoformat"):
                item[k] = item[k].isoformat()
        item["summary"] = {
            "total_km": total_km,
            "total_cost_home_currency": round(total_cost, 2),
            "home_currency": home,
            "has_missing_rates": has_missing,
        }
        result.append(item)

    result.sort(key=lambda t: t["start_date"], reverse=True)
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

    # ── home_location / has_return coherence ─────────────────────────
    if "home_location" in updates:
        hl = updates["home_location"]
        updates["home_location"] = (hl or "").strip() or None
    # effective values after this patch
    eff_has_return = updates.get("has_return") if "has_return" in updates else trip.get("has_return", False)
    eff_home_location = (
        updates["home_location"] if "home_location" in updates else trip.get("home_location")
    )
    if eff_has_return and not eff_home_location:
        raise HTTPException(
            status_code=422,
            detail="home_location is required when has_return=true",
        )

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
