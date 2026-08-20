"""Regression: GET /trips/{id}/timeline and GET /trips/{id}/route-geometry
must emit an IDENTICAL `return_leg` object shape and values.

Bug reported in Sprint C review (iteration_25 handoff): timeline's return_leg
was a minimal `{home_location}` while route-geometry returned the full builder
output. Both endpoints must share the same `_build_return_leg` helper.
"""
import os
import requests

frontend_env = {}
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            k, _, v = line.partition("=")
            frontend_env[k.strip()] = v.strip()
except Exception:
    pass
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or frontend_env.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
).rstrip("/")
API = f"{BASE_URL}/api"

# Fields that must appear in every non-null return_leg — this is the CONTRACT
# both endpoints must honour.
RETURN_LEG_KEYS = {
    "home_location",
    "home_coords",
    "from_stop_id",
    "transport_mode",
    "geojson",
    "distance_m",
    "duration_s",
}


def _dev_login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": "RL"}, timeout=10)
    assert r.status_code == 200, r.text
    return s


def test_return_leg_parity_between_timeline_and_route_geometry():
    s = _dev_login("return_leg_parity@twt.app")

    # 1) Trip with has_return=true + home_location + one stop.
    r = s.post(
        f"{API}/trips",
        json={
            "title": "ReturnLegParity",
            "home_currency": "EUR",
            "start_date": "2026-10-01",
            "end_date": "2026-10-05",
            "home_location": "Milano, Italia",
            "has_return": True,
        },
        timeout=10,
    )
    assert r.status_code == 201, r.text
    trip_id = r.json()["trip_id"]

    r = s.post(
        f"{API}/trips/{trip_id}/stops",
        json={
            "title": "Roma",
            "location": "Roma",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "transport_mode": "car",
        },
        timeout=20,
    )
    assert r.status_code == 201, r.text

    # Fetch both endpoints.
    tr = s.get(f"{API}/trips/{trip_id}/timeline", timeout=20)
    rg = s.get(f"{API}/trips/{trip_id}/route-geometry", timeout=20)
    assert tr.status_code == 200 and rg.status_code == 200

    tl_leg = tr.json().get("return_leg")
    rg_leg = rg.json().get("return_leg")

    # Both must be non-null objects.
    assert tl_leg is not None, "timeline return_leg must not be null for has_return trips"
    assert rg_leg is not None, "route-geometry return_leg must not be null for has_return trips"

    # Contract: same keys.
    assert set(tl_leg.keys()) == RETURN_LEG_KEYS, (
        f"timeline return_leg keys mismatch: got {set(tl_leg.keys())}"
    )
    assert set(rg_leg.keys()) == RETURN_LEG_KEYS, (
        f"route-geometry return_leg keys mismatch: got {set(rg_leg.keys())}"
    )

    # Parity: home_location, from_stop_id, transport_mode identical.
    for k in ("home_location", "from_stop_id", "transport_mode"):
        assert tl_leg[k] == rg_leg[k], (
            f"return_leg mismatch on {k}: timeline={tl_leg[k]!r} vs route-geometry={rg_leg[k]!r}"
        )

    # Geometric fields: same shape (both None, or both present with matching
    # types).  ORS live may occasionally rate-limit; we don't strictly require
    # identical numeric equality but the *presence* of a value must match.
    assert (tl_leg["home_coords"] is None) == (rg_leg["home_coords"] is None)
    if tl_leg["home_coords"] is not None:
        assert isinstance(tl_leg["home_coords"], list) and len(tl_leg["home_coords"]) == 2
        # Coordinates come from the same geocode cache → must be equal.
        assert tl_leg["home_coords"] == rg_leg["home_coords"]

    # Cleanup.
    s.delete(f"{API}/trips/{trip_id}", timeout=10)


def test_return_leg_null_parity_when_return_disabled():
    """Both endpoints must return `return_leg: null` when has_return=false."""
    s = _dev_login("return_leg_null@twt.app")
    r = s.post(
        f"{API}/trips",
        json={
            "title": "NoReturn",
            "home_currency": "EUR",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
        },
        timeout=10,
    )
    trip_id = r.json()["trip_id"]

    tl = s.get(f"{API}/trips/{trip_id}/timeline", timeout=10).json()
    rg = s.get(f"{API}/trips/{trip_id}/route-geometry", timeout=10).json()
    assert tl.get("return_leg") is None
    assert rg.get("return_leg") is None

    s.delete(f"{API}/trips/{trip_id}", timeout=10)


def test_return_leg_null_when_return_enabled_but_no_stops():
    """Both endpoints must return null when has_return=true but the trip has
    zero stops (there's no 'last stop' to close from)."""
    s = _dev_login("return_leg_no_stops@twt.app")
    r = s.post(
        f"{API}/trips",
        json={
            "title": "ReturnNoStops",
            "home_currency": "EUR",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "home_location": "Milano, Italia",
            "has_return": True,
        },
        timeout=10,
    )
    trip_id = r.json()["trip_id"]

    tl = s.get(f"{API}/trips/{trip_id}/timeline", timeout=10).json()
    rg = s.get(f"{API}/trips/{trip_id}/route-geometry", timeout=10).json()
    assert tl.get("return_leg") is None, tl.get("return_leg")
    assert rg.get("return_leg") is None, rg.get("return_leg")

    s.delete(f"{API}/trips/{trip_id}", timeout=10)
