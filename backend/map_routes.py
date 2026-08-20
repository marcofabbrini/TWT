"""Map / route geometry endpoint.

Returns per-trip stop coordinates + inter-stop route geometries (GeoJSON) for the
frontend map. Persists route geometries in `route_cache` (30-day TTL) so we don't
hit OpenRouteService on every dashboard open.

Design contract (agreed with product):
  • car / walk / train → ORS Directions (train uses driving-car profile).
  • plane / other → NO ORS call. Frontend draws the arc / dashed line locally.
  • ORS timeout: 4s. On failure / 429 → cache miss returns `geojson=null` and
    we degrade gracefully; the endpoint never fails as a whole.
"""
import asyncio
import logging
import os
from typing import List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException

from db import db
from auth import require_auth
from permissions import require_role
from services.distance import (
    ORS_BASE,
    geocode,
    haversine_km,
    _api_key,
    _is_mock,
    _norm,
    _PROFILES,
)
from models import utcnow

logger = logging.getLogger("twt.map")
router = APIRouter(prefix="/trips/{trip_id}", tags=["map"])

_COORD_QUANT = 4  # 4 decimal places ≈ 11m — enough to invalidate on real edits.


def _q(v: float) -> float:
    return round(float(v), _COORD_QUANT)


def _cache_key(a: Tuple[float, float], b: Tuple[float, float], mode: str) -> dict:
    return {
        "from_lng": _q(a[0]),
        "from_lat": _q(a[1]),
        "to_lng": _q(b[0]),
        "to_lat": _q(b[1]),
        "transport_mode": mode,
    }


async def _ors_route(
    a: Tuple[float, float], b: Tuple[float, float], mode: str
) -> Optional[dict]:
    """Call ORS Directions with 4s timeout. Return {geojson, distance_m, duration_s}
    or None on any failure (rate-limit, network, missing key, mock mode without pair).
    """
    profile = _PROFILES.get(mode, "driving-car")
    api_key = _api_key()
    if not api_key or _is_mock():
        # In mock mode we don't have real polylines; fall back to straight line.
        return None
    try:
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(
                f"{ORS_BASE}/v2/directions/{profile}",
                headers={"Authorization": api_key},
                params={"start": f"{a[0]},{a[1]}", "end": f"{b[0]},{b[1]}"},
            )
        if r.status_code != 200:
            logger.info("map.ors status=%s mode=%s", r.status_code, mode)
            return None
        data = r.json()
        feats = data.get("features") or []
        if not feats:
            return None
        feat = feats[0]
        seg = feat["properties"]["segments"][0]
        return {
            "geojson": feat.get("geometry"),
            "distance_m": seg.get("distance"),
            "duration_s": seg.get("duration"),
        }
    except Exception as e:
        logger.warning("map.ors err=%s mode=%s", e, mode)
        return None


async def _get_or_fetch_route(
    a: Tuple[float, float], b: Tuple[float, float], mode: str
) -> Optional[dict]:
    """Look up route in cache; on miss, call ORS and persist. None on graceful failure."""
    key = _cache_key(a, b, mode)
    cached = await db.route_cache.find_one(key, {"_id": 0})
    if cached:
        return {
            "geojson": cached.get("geojson"),
            "distance_m": cached.get("distance_m"),
            "duration_s": cached.get("duration_s"),
        }

    result = await _ors_route(a, b, mode)
    if result is None:
        return None
    # Persist. Duplicate races are fine — same key → same value.
    try:
        await db.route_cache.update_one(
            key,
            {"$set": {**key, **result, "cached_at": utcnow()}},
            upsert=True,
        )
    except Exception as e:
        logger.info("map.cache write err=%s", e)
    return result


def _serialize_stop_for_map(s: dict, coords: Optional[Tuple[float, float]]) -> dict:
    return {
        "stop_id": s["stop_id"],
        "order": s["order"],
        "title": s.get("title"),
        "location": s.get("location"),
        "transport_mode": s.get("transport_mode", "car"),
        "start_date": s.get("start_date"),
        "end_date": s.get("end_date"),
        "km_from_prev": s.get("km_from_prev"),
        "coords": [coords[0], coords[1]] if coords else None,
    }


@router.get("/route-geometry")
async def route_geometry(trip_id: str, current_user: dict = Depends(require_auth)):
    """Return stops (with cached coords) + per-segment route geometry."""
    await require_role(trip_id, current_user["user_id"], "viewer")

    stops = await db.stops.find(
        {"trip_id": trip_id},
        {"_id": 0},
    ).sort("order", 1).to_list(2000)

    # Resolve coords for every stop in parallel (geocode() uses cache internally).
    coords_list: List[Optional[Tuple[float, float]]] = await asyncio.gather(
        *(geocode(s.get("location")) for s in stops)
    )

    stops_out = [_serialize_stop_for_map(s, c) for s, c in zip(stops, coords_list)]

    # Build route requests for consecutive stops that have both coords.
    route_tasks = []
    route_meta = []  # parallel list: (from_stop, to_stop, mode)
    for i in range(1, len(stops)):
        prev_stop = stops[i - 1]
        stop = stops[i]
        a = coords_list[i - 1]
        b = coords_list[i]
        mode = stop.get("transport_mode", "car")

        if a is None or b is None:
            route_tasks.append(asyncio.sleep(0, result=None))
            route_meta.append((prev_stop, stop, mode, a, b))
            continue

        if mode == "other":
            route_tasks.append(asyncio.sleep(0, result={"skip": True}))
            route_meta.append((prev_stop, stop, mode, a, b))
            continue

        if mode == "plane":
            # Haversine distance, no ORS call — frontend draws the arc.
            dist_km = haversine_km(a, b)
            route_tasks.append(
                asyncio.sleep(0, result={
                    "geojson": None,
                    "distance_m": dist_km * 1000.0,
                    "duration_s": None,
                })
            )
            route_meta.append((prev_stop, stop, mode, a, b))
            continue

        route_tasks.append(_get_or_fetch_route(a, b, mode))
        route_meta.append((prev_stop, stop, mode, a, b))

    resolved = await asyncio.gather(*route_tasks) if route_tasks else []

    routes_out = []
    for res, (prev_stop, stop, mode, a, b) in zip(resolved, route_meta):
        if res and res.get("skip"):
            # transport=other: emit an entry with all null → frontend renders nothing
            # (or a dashed grey line if it wants); no distance to display.
            routes_out.append({
                "from_stop_id": prev_stop["stop_id"],
                "to_stop_id": stop["stop_id"],
                "transport_mode": mode,
                "geojson": None,
                "distance_m": None,
                "duration_s": None,
            })
            continue

        if res is None:
            # ORS failure or missing coords → graceful fallback.
            # If we have a persisted km_from_prev use it as distance for the popup.
            dm = None
            km = stop.get("km_from_prev")
            if km is not None:
                dm = float(km) * 1000.0
            routes_out.append({
                "from_stop_id": prev_stop["stop_id"],
                "to_stop_id": stop["stop_id"],
                "transport_mode": mode,
                "geojson": None,
                "distance_m": dm,
                "duration_s": None,
            })
            continue

        routes_out.append({
            "from_stop_id": prev_stop["stop_id"],
            "to_stop_id": stop["stop_id"],
            "transport_mode": mode,
            "geojson": res.get("geojson"),
            "distance_m": res.get("distance_m"),
            "duration_s": res.get("duration_s"),
        })

    return {"stops": stops_out, "routes": routes_out}
