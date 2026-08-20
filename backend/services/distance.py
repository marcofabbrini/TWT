"""
Distance service — geocoding + routing via OpenRouteService.
Falls back gracefully to None if ORS_API_KEY is missing or the API errors.

ORS_MOCK=1 → deterministic distances for a fixed set of location pairs.
Used by the tester to verify the flow without a real key.
"""
import logging
import math
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

import httpx

from db import db
from models import utcnow

logger = logging.getLogger("twt.distance")

ORS_BASE = "https://api.openrouteservice.org"
GEOCODE_TTL_DAYS = 30

# Transport → ORS profile mapping.
_PROFILES = {
    "car": "driving-car",
    "walk": "foot-walking",
    "train": "driving-car",  # ORS has no train profile; driving as documented fallback
}

# Mock coordinates (lng, lat) for known cities — used when ORS_MOCK=1.
_MOCK_COORDS = {
    "roma": (12.4964, 41.9028), "rome": (12.4964, 41.9028),
    "milano": (9.19, 45.4642), "milan": (9.19, 45.4642),
    "firenze": (11.2558, 43.7696), "florence": (11.2558, 43.7696),
    "bologna": (11.3426, 44.4949),
    "napoli": (14.2681, 40.8518), "naples": (14.2681, 40.8518),
    "venezia": (12.3155, 45.4408), "venice": (12.3155, 45.4408),
    "london": (-0.1276, 51.5074),
    "paris": (2.3522, 48.8566),
    "amsterdam": (4.9041, 52.3676),
    "lisbon": (-9.1393, 38.7223), "lisbona": (-9.1393, 38.7223),
    "sintra": (-9.3811, 38.7972),
}

# Deterministic driving-distance pairs (undirected) in km.
_MOCK_ROADS = {
    frozenset(["roma", "milano"]): 574.0,
    frozenset(["milano", "firenze"]): 305.0,
    frozenset(["roma", "firenze"]): 275.0,
    frozenset(["firenze", "bologna"]): 106.0,
    frozenset(["roma", "napoli"]): 225.0,
    frozenset(["milano", "venezia"]): 275.0,
    frozenset(["london", "paris"]): 460.0,
    frozenset(["paris", "amsterdam"]): 500.0,
    frozenset(["lisbon", "sintra"]): 30.0,
}
# Aliases so we can look up both "Roma" and "Rome".
_MOCK_ROAD_ALIASES = {"rome": "roma", "milan": "milano", "florence": "firenze",
                       "naples": "napoli", "venice": "venezia", "lisbona": "lisbon"}


def _norm(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return s.strip().lower().split(",")[0].strip()


def _is_mock() -> bool:
    return os.environ.get("ORS_MOCK") == "1"


def _api_key() -> Optional[str]:
    v = os.environ.get("ORS_API_KEY")
    return v.strip() if v else None


# ── Geocoding ─────────────────────────────────────────
async def geocode(location: str) -> Optional[Tuple[float, float]]:
    """Return (lng, lat) for `location`, or None on failure. Cached 30 days."""
    key = _norm(location)
    if not key:
        return None

    cached = await db.geocode_cache.find_one({"key": key}, {"_id": 0})
    if cached:
        return (cached["lng"], cached["lat"])

    coords: Optional[Tuple[float, float]] = None

    if _is_mock():
        # Look up mock coords by primary name or alias.
        canonical = _MOCK_ROAD_ALIASES.get(key, key)
        if canonical in _MOCK_COORDS:
            coords = _MOCK_COORDS[canonical]
        elif key in _MOCK_COORDS:
            coords = _MOCK_COORDS[key]
    else:
        api_key = _api_key()
        if not api_key:
            logger.info("distance.geocode skipped (no key) location=%s", key)
            return None
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(
                    f"{ORS_BASE}/geocode/search",
                    params={"api_key": api_key, "text": location, "size": 1},
                )
            if r.status_code == 200:
                feats = r.json().get("features") or []
                if feats:
                    lng, lat = feats[0]["geometry"]["coordinates"][:2]
                    coords = (float(lng), float(lat))
        except Exception as e:
            logger.warning("distance.geocode error location=%s err=%s", key, e)

    if coords:
        await db.geocode_cache.update_one(
            {"key": key},
            {"$set": {
                "key": key,
                "location_raw": location,
                "lng": coords[0],
                "lat": coords[1],
                "cached_at": utcnow(),
            }},
            upsert=True,
        )
    return coords


# ── Haversine (plane / air line) ──────────────────────
def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """a, b are (lng, lat)."""
    lng1, lat1 = a
    lng2, lat2 = b
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(x)), 1)


# ── Routing ───────────────────────────────────────────
async def _mock_route_km(a_key: str, b_key: str) -> Optional[float]:
    ka = _MOCK_ROAD_ALIASES.get(a_key, a_key)
    kb = _MOCK_ROAD_ALIASES.get(b_key, b_key)
    if ka == kb:
        return 0.0
    return _MOCK_ROADS.get(frozenset([ka, kb]))


async def compute_km(
    from_location: Optional[str],
    to_location: Optional[str],
    transport_mode: str,
) -> Optional[float]:
    """Best-effort km distance. Returns None on any failure or unsupported mode."""
    if not from_location or not to_location:
        return None
    if transport_mode == "other":
        return None

    # For plane we compute great-circle from coordinates (no ORS route call).
    if transport_mode == "plane":
        a = await geocode(from_location)
        b = await geocode(to_location)
        if not a or not b:
            return None
        return haversine_km(a, b)

    profile = _PROFILES.get(transport_mode, "driving-car")

    if _is_mock():
        km = await _mock_route_km(_norm(from_location), _norm(to_location))
        if km is not None:
            return km
        # Mock fallback to haversine if the pair isn't in the table.
        a = await geocode(from_location)
        b = await geocode(to_location)
        if a and b:
            return haversine_km(a, b)
        return None

    api_key = _api_key()
    if not api_key:
        return None

    a = await geocode(from_location)
    b = await geocode(to_location)
    if not a or not b:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{ORS_BASE}/v2/directions/{profile}",
                headers={"Authorization": api_key},
                params={"start": f"{a[0]},{a[1]}", "end": f"{b[0]},{b[1]}"},
            )
        if r.status_code == 200:
            data = r.json()
            feats = data.get("features") or []
            if feats:
                dist_m = feats[0]["properties"]["segments"][0]["distance"]
                return round(dist_m / 1000.0, 1)
    except Exception as e:
        logger.warning("distance.route error err=%s", e)
    return None


# ── High-level recompute for a trip ───────────────────
async def recompute_stop_km(trip_id: str, stop_id: str) -> Tuple[Optional[float], bool]:
    """Recompute km_from_prev for a single stop (respects manual_override).
    Returns (km, error_flag)."""
    stop = await db.stops.find_one({"stop_id": stop_id, "trip_id": trip_id}, {"_id": 0})
    if not stop:
        return None, False
    if stop.get("km_manual_override"):
        return stop.get("km_from_prev"), False

    # Find the previous stop by order.
    prev = await db.stops.find_one(
        {"trip_id": trip_id, "order": {"$lt": stop["order"]}},
        {"_id": 0, "location": 1, "order": 1},
        sort=[("order", -1)],
    )
    if not prev:
        # First stop of the trip has no "from" — km is null.
        await db.stops.update_one(
            {"stop_id": stop_id}, {"$set": {"km_from_prev": None, "km_calc_error": False}}
        )
        return None, False

    km = await compute_km(prev["location"], stop["location"], stop.get("transport_mode", "car"))
    await db.stops.update_one(
        {"stop_id": stop_id},
        {"$set": {"km_from_prev": km, "km_calc_error": km is None}},
    )
    return km, km is None


async def recompute_trip_km(trip_id: str) -> dict:
    """Recompute km for every stop of the trip. Returns {updated_count, errors:[stop_id]}."""
    stops = await db.stops.find(
        {"trip_id": trip_id}, {"_id": 0, "stop_id": 1}
    ).sort("order", 1).to_list(2000)
    updated = 0
    errors = []
    for s in stops:
        km, err = await recompute_stop_km(trip_id, s["stop_id"])
        if err:
            errors.append(s["stop_id"])
        else:
            updated += 1
    return {"updated_count": updated, "errors": errors}
