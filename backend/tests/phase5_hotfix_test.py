"""Phase 5 hotfix regression: recompute-km version bump + transport=other not errored."""
import httpx
import pytest
import os
from urllib.parse import urlparse

API_URL = None


def _get_api_url():
    global API_URL
    if API_URL:
        return API_URL
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                API_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break
    return API_URL


def _login(email: str) -> httpx.Client:
    c = httpx.Client(base_url=_get_api_url(), timeout=15)
    r = c.post("/api/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def owner():
    c = _login("p5hot_owner@twt.app")
    yield c
    c.close()


@pytest.fixture()
def trip(owner):
    r = owner.post("/api/trips", json={
        "title": "P5-hotfix",
        "home_currency": "EUR",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
    })
    assert r.status_code == 201
    tid = r.json()["trip_id"]
    yield tid
    owner.delete(f"/api/trips/{tid}")


def _stop(owner, trip, title, location, start, end, transport="car"):
    r = owner.post(f"/api/trips/{trip}/stops", json={
        "title": title, "location": location,
        "start_date": start, "end_date": end,
        "transport_mode": transport,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_recompute_km_bumps_version_when_updates(owner, trip):
    """After the initial inline recompute (from POST /stops), an explicit
    /recompute-km is a no-op AND MUST NOT bump the version. This asserts the
    version-bump path is guarded by 'something actually changed'."""
    _stop(owner, trip, "A", "Roma", "2026-06-01", "2026-06-02")
    _stop(owner, trip, "B", "Milano", "2026-06-03", "2026-06-04")

    v0 = owner.get(f"/api/trips/{trip}/version").json()["version"]
    r = owner.post(f"/api/trips/{trip}/recompute-km")
    assert r.status_code == 200
    body = r.json()
    assert body["updated_count"] == 0, body
    v1 = owner.get(f"/api/trips/{trip}/version").json()["version"]
    assert v1 == v0, f"version must not bump when nothing changed: {v0} -> {v1}"


def test_transport_other_is_not_an_error(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-06-01", "2026-06-02")
    s2 = _stop(owner, trip, "B", "Somewhere", "2026-06-03", "2026-06-04", transport="other")

    # Stop create should already return km_calc_error=False for other.
    assert s2["transport_mode"] == "other"
    assert s2["km_from_prev"] is None
    assert s2["km_calc_error"] is False, s2

    # Recompute should not include this stop in errors[].
    r = owner.post(f"/api/trips/{trip}/recompute-km")
    assert r.status_code == 200
    body = r.json()
    assert s2["stop_id"] not in body["errors"], body

    # And GET reflects km_calc_error=False persisted.
    stops = owner.get(f"/api/trips/{trip}/stops").json()
    b = next(x for x in stops if x["stop_id"] == s2["stop_id"])
    assert b["km_calc_error"] is False
    assert b["km_from_prev"] is None


def test_unknown_city_still_reported_as_error(owner, trip):
    """Regression guard: unknown city with normal transport still errors."""
    _stop(owner, trip, "A", "Roma", "2026-06-01", "2026-06-02")
    s2 = _stop(owner, trip, "B", "Xyzzy-unknown", "2026-06-03", "2026-06-04", transport="car")
    assert s2["km_from_prev"] is None
    assert s2["km_calc_error"] is True
    r = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert s2["stop_id"] in r["errors"]
