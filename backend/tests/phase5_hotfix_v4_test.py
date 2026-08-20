"""Phase 5 hotfix v4: turning manual override OFF must restore the real error state."""
import os

import httpx
import pytest
from dotenv import dotenv_values

_fe = dotenv_values("/app/frontend/.env")
API_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")


@pytest.fixture()
def owner():
    c = httpx.Client(base_url=API_URL, timeout=30)
    r = c.post("/api/auth/dev-login", json={"email": "p5v4@twt.app"})
    assert r.status_code == 200, r.text
    yield c
    c.close()


@pytest.fixture()
def trip(owner):
    r = owner.post("/api/trips", json={
        "title": "TEST_P5v4", "home_currency": "EUR",
        "start_date": "2026-11-01", "end_date": "2026-11-30"})
    assert r.status_code == 201, r.text
    tid = r.json()["trip_id"]
    yield tid
    owner.delete(f"/api/trips/{tid}")


def test_override_off_restores_error_state(owner, trip):
    owner.post(f"/api/trips/{trip}/stops", json={
        "title": "A", "location": "Roma", "start_date": "2026-11-01",
        "end_date": "2026-11-02", "transport_mode": "car"})
    r = owner.post(f"/api/trips/{trip}/stops", json={
        "title": "B", "location": "Qqx-Unknown-City", "start_date": "2026-11-03",
        "end_date": "2026-11-04", "transport_mode": "car"})
    b = r.json()
    assert b["km_calc_error"] is True

    # ON -> clean
    r = owner.patch(f"/api/trips/{trip}/stops/{b['stop_id']}",
                    json={"km_from_prev": 123, "km_manual_override": True})
    assert r.json()["km_calc_error"] is False

    # OFF -> error must come back (auto-calc still fails for unknown city)
    r = owner.patch(f"/api/trips/{trip}/stops/{b['stop_id']}",
                    json={"km_manual_override": False})
    assert r.status_code == 200, r.text
    assert r.json()["km_calc_error"] is True, r.json()

    body = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert body["updated_count"] == 0, body
    assert b["stop_id"] in body["errors"], body
