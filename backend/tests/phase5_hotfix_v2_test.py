"""Phase 5 hotfix v2: recompute-km idempotency (no-op does not bump version)."""
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


def _login(email: str) -> httpx.Client:
    c = httpx.Client(base_url=_get_api_url(), timeout=15)
    r = c.post("/api/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def owner():
    c = _login("p5idem_owner@twt.app")
    yield c
    c.close()


@pytest.fixture()
def trip(owner):
    r = owner.post("/api/trips", json={
        "title": "P5-idem",
        "home_currency": "EUR",
        "start_date": "2026-07-01",
        "end_date": "2026-07-30",
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


def _v(owner, trip):
    return owner.get(f"/api/trips/{trip}/version").json()["version"]


def test_second_recompute_is_noop(owner, trip):
    """3 stops already fully computed → 2nd recompute updated_count=0 and version stays."""
    _stop(owner, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    _stop(owner, trip, "B", "Milano", "2026-07-03", "2026-07-04")
    _stop(owner, trip, "C", "Firenze", "2026-07-05", "2026-07-06")

    # First recompute may or may not change anything (create-time recompute already ran).
    owner.post(f"/api/trips/{trip}/recompute-km")

    v0 = _v(owner, trip)
    r = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert r["updated_count"] == 0, r
    v1 = _v(owner, trip)
    assert v1 == v0, f"version must not bump on no-op: {v0} -> {v1}"


def test_location_change_bumps_only_first_time(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    b = _stop(owner, trip, "B", "Milano", "2026-07-03", "2026-07-04")
    owner.post(f"/api/trips/{trip}/recompute-km")

    # Patch B's location — km changes on next recompute.
    r = owner.patch(f"/api/trips/{trip}/stops/{b['stop_id']}", json={"location": "Napoli"})
    assert r.status_code == 200

    v0 = _v(owner, trip)
    r1 = owner.post(f"/api/trips/{trip}/recompute-km").json()
    # Now the trip already reflects the new value (patch triggered recompute inline),
    # so the explicit recompute is a no-op. Version must NOT bump.
    assert r1["updated_count"] == 0
    assert _v(owner, trip) == v0

    # Sanity: km_from_prev for B is now Roma→Napoli.
    stops = owner.get(f"/api/trips/{trip}/stops").json()
    b_now = next(s for s in stops if s["stop_id"] == b["stop_id"])
    assert b_now["km_from_prev"] == 225.0


def test_manual_override_never_marked_changed(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-07-01", "2026-07-02")
    b = _stop(owner, trip, "B", "Milano", "2026-07-03", "2026-07-04")
    owner.patch(f"/api/trips/{trip}/stops/{b['stop_id']}",
                json={"km_from_prev": 999, "km_manual_override": True})
    owner.post(f"/api/trips/{trip}/recompute-km")
    v0 = _v(owner, trip)
    r = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert r["updated_count"] == 0
    assert _v(owner, trip) == v0
    stops = owner.get(f"/api/trips/{trip}/stops").json()
    b_now = next(s for s in stops if s["stop_id"] == b["stop_id"])
    assert b_now["km_from_prev"] == 999
