"""Day-centric aggregated timeline (Sprint C).

Returns everything the frontend `TripDayView` needs to render the day tabs
in a single request, in one round-trip to Mongo (5 batched find() calls that
run in parallel via asyncio.gather).

Perf target from the sprint brief: <1s for a 30-day trip with ~100
attractions. In practice the payload is dominated by the days array; all
Mongo I/O runs concurrently.
"""
import asyncio
from datetime import date, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from db import db
from auth import require_auth
from permissions import require_role, get_trip_or_404
from services.distance import geocode
from map_routes import _build_return_leg

router = APIRouter(prefix="/trips/{trip_id}", tags=["timeline"])


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _to_date(v) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return None


def _drop_id(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_id"}


def _stop_position(day_iso: str, stop: Optional[dict]) -> str:
    if not stop:
        return "none"
    s = stop["start_date"][:10] if isinstance(stop["start_date"], str) else stop["start_date"].isoformat()
    e = stop["end_date"][:10] if isinstance(stop["end_date"], str) else stop["end_date"].isoformat()
    if s == e:
        return "only"
    if day_iso == s:
        return "first"
    if day_iso == e:
        return "last"
    return "middle"


def _find_stop_for_day(stops: List[dict], day: date) -> Optional[dict]:
    """Return the stop covering `day`. If multiple overlap, prefer the one with
    the largest start_date (most recently entered)."""
    best = None
    best_start = None
    for s in stops:
        sd = _to_date(s.get("start_date"))
        ed = _to_date(s.get("end_date"))
        if sd is None or ed is None:
            continue
        if sd <= day <= ed:
            if best_start is None or sd > best_start:
                best = s
                best_start = sd
    return best


@router.get("/timeline")
async def get_timeline(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    trip = await get_trip_or_404(trip_id)

    start = _to_date(trip["start_date"])
    end = _to_date(trip["end_date"])
    if start is None or end is None:
        raise HTTPException(status_code=500, detail="Trip dates malformed")

    # Batch fetch all children in parallel.
    stops_task = db.stops.find({"trip_id": trip_id}, {"_id": 0}).sort("order", 1).to_list(2000)
    atts_task = db.attractions.find({"trip_id": trip_id}, {"_id": 0}).sort("order", 1).to_list(5000)
    hotels_task = db.hotels.find({"trip_id": trip_id}, {"_id": 0}).to_list(2000)
    exps_task = db.expenses.find({"trip_id": trip_id}, {"_id": 0}).to_list(5000)
    stops, attractions, hotels, expenses = await asyncio.gather(
        stops_task, atts_task, hotels_task, exps_task
    )
    stop_by_id = {s["stop_id"]: s for s in stops}

    # ── unscheduled attractions grouped-friendly ──────────────────────
    unscheduled: List[dict] = []
    for a in attractions:
        if a.get("scheduled_date"):
            continue
        entry = _drop_id(a)
        stop_ctx = stop_by_id.get(a["stop_id"], {})
        entry["stop_title"] = stop_ctx.get("title")
        unscheduled.append(entry)

    # ── index by day ISO ─────────────────────────────────────────────
    atts_by_date: Dict[str, List[dict]] = {}
    for a in attractions:
        sd = a.get("scheduled_date")
        if not sd:
            continue
        key = sd if isinstance(sd, str) else sd.isoformat()
        atts_by_date.setdefault(key[:10], []).append(a)

    exps_by_date: Dict[str, List[dict]] = {}
    for e in expenses:
        d = e.get("expense_date")
        if not d:
            continue
        key = d if isinstance(d, str) else d.isoformat()
        exps_by_date.setdefault(key[:10], []).append(e)

    # Hotels: active on a night if check_in <= day < check_out.
    def _hotels_on(day: date) -> List[dict]:
        out = []
        for h in hotels:
            ci = _to_date(h.get("check_in"))
            co = _to_date(h.get("check_out"))
            if ci is None or co is None:
                continue
            if ci <= day < co:
                out.append(h)
        return out

    # ── walk days ────────────────────────────────────────────────────
    days_out: List[dict] = []
    day = start
    idx = 0
    while day <= end:
        day_iso = day.isoformat()
        stop = _find_stop_for_day(stops, day)
        position = _stop_position(day_iso, stop)

        # Determine incoming route info for arrival days (first of a stop AND
        # not the very first stop of the trip).
        route_in = None
        if stop and position in ("first", "only") and stops:
            # Find previous stop by (order, start_date).
            idx_in_stops = next(
                (i for i, s in enumerate(stops) if s["stop_id"] == stop["stop_id"]),
                None,
            )
            if idx_in_stops is not None and idx_in_stops > 0:
                prev = stops[idx_in_stops - 1]
                route_in = {
                    "from_stop_id": prev["stop_id"],
                    "from_title": prev.get("title"),
                    "transport_mode": stop.get("transport_mode", "car"),
                    "distance_m": (
                        stop.get("km_from_prev") * 1000.0
                        if stop.get("km_from_prev") is not None
                        else None
                    ),
                }

        is_return_home_day = (
            bool(trip.get("has_return"))
            and bool(trip.get("home_location"))
            and day == end
        )

        days_out.append({
            "date": day_iso,
            "weekday": WEEKDAYS[day.weekday()],
            "day_index": idx,
            "stop_id": stop["stop_id"] if stop else None,
            "stop_title": stop.get("title") if stop else None,
            "stop_location": stop.get("location") if stop else None,
            "stop_transport_mode": stop.get("transport_mode") if stop else None,
            "stop_position": position,
            "is_transit_day": stop is None,
            "is_return_home_day": is_return_home_day,
            "route_in": route_in,
            "attractions": [_drop_id(a) for a in atts_by_date.get(day_iso, [])],
            "hotels_active": [_drop_id(h) for h in _hotels_on(day)],
            "expenses": [_drop_id(e) for e in exps_by_date.get(day_iso, [])],
        })
        day += timedelta(days=1)
        idx += 1

    return_leg = None
    if trip.get("has_return") and trip.get("home_location") and stops:
        # Reuse the exact builder used by GET /route-geometry so both endpoints
        # emit an identical return_leg shape. Only the last stop's coords are
        # needed to compute the closing leg → geocode just that one.
        last_coords = await geocode(stops[-1].get("location"))
        coords_list = [None] * (len(stops) - 1) + [last_coords]
        return_leg = await _build_return_leg(trip, stops, coords_list)

    return {
        "trip_id": trip_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": days_out,
        "unscheduled_attractions": unscheduled,
        "return_leg": return_leg,
    }
