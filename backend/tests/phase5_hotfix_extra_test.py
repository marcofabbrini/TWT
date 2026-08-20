"""Phase 5 hotfix — extra coverage added by testing agent (iteration 14).

Covers gaps not in phase5_hotfix_test.py:
  FIX #1: version must NOT bump when updated_count == 0 (trip with zero stops);
          last_updated_by == caller user_id and last_updated_at moves forward.
  FIX #2: 'other' counted in updated_count; multiple 'other' stops; mixed trip.
"""
import time

import httpx
import pytest

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


def _login(email: str):
    c = httpx.Client(base_url=_get_api_url(), timeout=20)
    r = c.post("/api/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return c, r.json()["user"]["user_id"] if "user" in r.json() else None


@pytest.fixture()
def owner():
    c, uid = _login("p5hotx_owner@twt.app")
    yield c, uid
    c.close()


@pytest.fixture()
def trip(owner):
    c, _ = owner
    r = c.post("/api/trips", json={
        "title": "TEST_P5-hotfix-extra",
        "home_currency": "EUR",
        "start_date": "2026-07-01",
        "end_date": "2026-07-30",
    })
    assert r.status_code == 201, r.text
    tid = r.json()["trip_id"]
    yield tid
    c.delete(f"/api/trips/{tid}")


def _stop(c, trip, title, location, start, end, transport="car"):
    r = c.post(f"/api/trips/{trip}/stops", json={
        "title": title, "location": location,
        "start_date": start, "end_date": end,
        "transport_mode": transport,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _version(c, trip):
    r = c.get(f"/api/trips/{trip}/version")
    assert r.status_code == 200, r.text
    return r.json()


# ── FIX #1 ───────────────────────────────────────────────
def test_no_version_bump_when_zero_stops(owner, trip):
    c, _ = owner
    v0 = _version(c, trip)
    r = c.post(f"/api/trips/{trip}/recompute-km")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated_count"] == 0, body
    assert body["errors"] == [], body
    v1 = _version(c, trip)
    assert v1["version"] == v0["version"], f"version must not bump: {v0} -> {v1}"
    assert v1["last_updated_at"] == v0["last_updated_at"]


def test_version_bump_sets_last_updated_by_and_at(owner, trip):
    c, uid = owner
    _stop(c, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    _stop(c, trip, "B", "Firenze", "2026-07-03", "2026-07-04")
    v0 = _version(c, trip)
    time.sleep(1.1)
    r = c.post(f"/api/trips/{trip}/recompute-km")
    assert r.status_code == 200
    assert r.json()["updated_count"] == 2, r.json()
    v1 = _version(c, trip)
    assert v1["version"] == v0["version"] + 1, (v0, v1)
    assert v1["last_updated_by"] == uid, v1
    assert v1["last_updated_at"] > v0["last_updated_at"], (v0, v1)


def test_repeated_recompute_bumps_each_time(owner, trip):
    c, _ = owner
    _stop(c, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    _stop(c, trip, "B", "Napoli", "2026-07-03", "2026-07-04")
    v0 = _version(c, trip)["version"]
    for i in range(1, 4):
        assert c.post(f"/api/trips/{trip}/recompute-km").status_code == 200
        assert _version(c, trip)["version"] == v0 + i


# ── FIX #2 ───────────────────────────────────────────────
def test_other_counted_in_updated_count_and_km_totals(owner, trip):
    c, _ = owner
    _stop(c, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    o1 = _stop(c, trip, "B", "Anywhere", "2026-07-03", "2026-07-04", transport="other")
    o2 = _stop(c, trip, "C", "Elsewhere", "2026-07-05", "2026-07-06", transport="other")
    assert o1["km_calc_error"] is False and o1["km_from_prev"] is None
    assert o2["km_calc_error"] is False and o2["km_from_prev"] is None

    body = c.post(f"/api/trips/{trip}/recompute-km").json()
    assert body["errors"] == [], body
    assert body["updated_count"] == 3, body

    stops = c.get(f"/api/trips/{trip}/stops").json()
    for sid in (o1["stop_id"], o2["stop_id"]):
        s = next(x for x in stops if x["stop_id"] == sid)
        assert s["km_calc_error"] is False, s
        assert s["km_from_prev"] is None, s


def test_mixed_trip_only_real_errors_reported(owner, trip):
    c, _ = owner
    _stop(c, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    good = _stop(c, trip, "B", "Milano", "2026-07-03", "2026-07-04", transport="car")
    other = _stop(c, trip, "C", "Nowhere-other", "2026-07-05", "2026-07-06", transport="other")
    bad = _stop(c, trip, "D", "Qqqq-unknown-city", "2026-07-07", "2026-07-08", transport="train")

    body = c.post(f"/api/trips/{trip}/recompute-km").json()
    assert bad["stop_id"] in body["errors"], body
    assert other["stop_id"] not in body["errors"], body
    assert good["stop_id"] not in body["errors"], body
    assert body["updated_count"] == 3, body

    stops = {s["stop_id"]: s for s in c.get(f"/api/trips/{trip}/stops").json()}
    assert stops[good["stop_id"]]["km_from_prev"] == 574.0
    assert stops[good["stop_id"]]["km_calc_error"] is False
    assert stops[other["stop_id"]]["km_calc_error"] is False
    assert stops[bad["stop_id"]]["km_calc_error"] is True


def test_other_transport_survives_change_to_car(owner, trip):
    """Switching 'other' -> 'car' with an unknown city must flip error back to true."""
    c, _ = owner
    _stop(c, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    s = _stop(c, trip, "B", "Zzz-unknown", "2026-07-03", "2026-07-04", transport="other")
    assert s["km_calc_error"] is False

    r = c.patch(f"/api/trips/{trip}/stops/{s['stop_id']}", json={"transport_mode": "car"})
    assert r.status_code == 200, r.text
    body = c.post(f"/api/trips/{trip}/recompute-km").json()
    assert s["stop_id"] in body["errors"], body
    stops = {x["stop_id"]: x for x in c.get(f"/api/trips/{trip}/stops").json()}
    assert stops[s["stop_id"]]["km_calc_error"] is True
