"""Edge case: manual override applied to a stop that was previously in km error state."""
import os

import httpx
import pytest
from dotenv import dotenv_values

_fe = dotenv_values("/app/frontend/.env")
API_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")


@pytest.fixture()
def owner():
    c = httpx.Client(base_url=API_URL, timeout=30)
    r = c.post("/api/auth/dev-login", json={"email": "p5v3edge@twt.app"})
    assert r.status_code == 200, r.text
    yield c
    c.close()


@pytest.fixture()
def trip(owner):
    r = owner.post("/api/trips", json={
        "title": "TEST_P5v3edge", "home_currency": "EUR",
        "start_date": "2026-10-01", "end_date": "2026-10-30"})
    assert r.status_code == 201, r.text
    tid = r.json()["trip_id"]
    yield tid
    owner.delete(f"/api/trips/{tid}")


def test_manual_override_on_errored_stop_clears_from_errors(owner, trip):
    owner.post(f"/api/trips/{trip}/stops", json={
        "title": "A", "location": "Roma", "start_date": "2026-10-01",
        "end_date": "2026-10-02", "transport_mode": "car"})
    r = owner.post(f"/api/trips/{trip}/stops", json={
        "title": "B", "location": "Qqx-Unknown-City", "start_date": "2026-10-03",
        "end_date": "2026-10-04", "transport_mode": "car"})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["km_calc_error"] is True

    # User resolves it manually.
    r = owner.patch(f"/api/trips/{trip}/stops/{b['stop_id']}",
                    json={"km_from_prev": 123, "km_manual_override": True})
    assert r.status_code == 200, r.text

    patched = r.json()
    assert patched["km_from_prev"] == 123
    assert patched["km_calc_error"] is False
    assert patched["km_manual_override"] is True

    # (a) GET /stops must show the clean state synchronously.
    stops = owner.get(f"/api/trips/{trip}/stops").json()
    bdoc = next(s for s in stops if s["stop_id"] == b["stop_id"])
    assert bdoc["km_calc_error"] is False, bdoc
    assert bdoc["km_from_prev"] == 123, bdoc

    # (b) recompute must not report B in errors[].
    body = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert b["stop_id"] not in body["errors"], (
        "manually-overridden stop should not be reported as a km error anymore: %s" % body)

    # (c) subsequent no-op recomputes are idempotent and do not bump version.
    v0 = owner.get(f"/api/trips/{trip}/version").json()["version"]
    for _ in range(2):
        body = owner.post(f"/api/trips/{trip}/recompute-km").json()
        assert body["updated_count"] == 0, body
        assert b["stop_id"] not in body["errors"], body
    v1 = owner.get(f"/api/trips/{trip}/version").json()["version"]
    assert v0 == v1, (v0, v1)
