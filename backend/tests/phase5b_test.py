"""Phase 5 retest — km_calc_error exposure, POST/PATCH km in response, summary.total_km."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

TRIP_START = "2030-06-01"
TRIP_END = "2030-06-30"


def _client(email):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": "P5B"})
    assert r.status_code in (200, 201), r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['session_token']}"})
    return s


@pytest.fixture(scope="module")
def owner():
    return _client(f"p5b_{uuid.uuid4().hex[:6]}@twt.app")


@pytest.fixture(scope="module")
def trip(owner):
    r = owner.post(f"{API}/trips", json={
        "title": f"TEST_P5B_{uuid.uuid4().hex[:6]}",
        "home_currency": "EUR",
        "start_date": TRIP_START,
        "end_date": TRIP_END,
    })
    assert r.status_code in (200, 201), r.text
    t = r.json()
    yield t
    owner.delete(f"{API}/trips/{t['trip_id']}")


def _mk(owner, tid, title, location, mode="car", **kw):
    body = {
        "title": title, "location": location,
        "start_date": TRIP_START, "end_date": TRIP_START,
        "transport_mode": mode,
    }
    body.update(kw)
    return owner.post(f"{API}/trips/{tid}/stops", json=body)


# ── Fix #2/#3/#4 ───────────────────────────────────────────
class TestPhase5Fixes:
    def test_seed_and_create_response_km(self, owner, trip):
        tid = trip["trip_id"]
        r0 = _mk(owner, tid, "TEST_Roma", "Roma, IT")
        assert r0.status_code == 201, r0.text
        d0 = r0.json()
        assert d0["km_from_prev"] is None  # first stop, no prev
        assert d0["km_calc_error"] is False

        # Fix #3: create response must carry the recomputed km
        r1 = _mk(owner, tid, "TEST_Milano", "Milano, IT")
        assert r1.status_code == 201, r1.text
        d1 = r1.json()
        assert d1["km_from_prev"] == 574.0, d1
        assert d1["km_calc_error"] is False

        # plane leg Milano -> Firenze (haversine 249.5)
        r2 = _mk(owner, tid, "TEST_Firenze", "Firenze, IT", mode="plane")
        assert r2.status_code == 201, r2.text
        assert r2.json()["km_from_prev"] == 249.5, r2.text

    def test_summary_total_km(self, owner, trip):
        tid = trip["trip_id"]
        r = owner.get(f"{API}/trips/{tid}/summary")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body["total_km"], (int, float)), body
        assert abs(body["total_km"] - 823.5) < 0.05, body

    def test_km_calc_error_unknown_city(self, owner, trip):
        tid = trip["trip_id"]
        r = _mk(owner, tid, "TEST_Xyzzy", "Xyzzy")
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["km_from_prev"] is None, d
        assert d["km_calc_error"] is True, d
        # persisted via GET
        lst = owner.get(f"{API}/trips/{tid}/stops").json()
        got = [s for s in lst if s["stop_id"] == d["stop_id"]][0]
        assert got["km_calc_error"] is True
        # total_km unchanged (null leg excluded)
        s = owner.get(f"{API}/trips/{tid}/summary").json()
        assert abs(s["total_km"] - 823.5) < 0.05, s
        owner.delete(f"{API}/trips/{tid}/stops/{d['stop_id']}")

    def test_patch_location_response_has_fresh_km(self, owner, trip):
        tid = trip["trip_id"]
        lst = owner.get(f"{API}/trips/{tid}/stops").json()
        milano = [s for s in lst if s["title"] == "TEST_Milano"][0]
        r = owner.patch(f"{API}/trips/{tid}/stops/{milano['stop_id']}",
                        json={"location": "Napoli, IT"})
        assert r.status_code == 200, r.text
        assert r.json()["km_from_prev"] == 225.0, r.text  # Roma->Napoli
        assert r.json()["km_calc_error"] is False
        # patch to unknown city -> error flag true in the response
        r2 = owner.patch(f"{API}/trips/{tid}/stops/{milano['stop_id']}",
                         json={"location": "Zzzznowhere"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["km_from_prev"] is None
        assert r2.json()["km_calc_error"] is True
        # restore
        owner.patch(f"{API}/trips/{tid}/stops/{milano['stop_id']}",
                    json={"location": "Milano, IT"})

    def test_summary_total_km_none_when_no_km(self, owner):
        r = owner.post(f"{API}/trips", json={
            "title": f"TEST_P5B_EMPTY_{uuid.uuid4().hex[:6]}",
            "home_currency": "EUR", "start_date": TRIP_START, "end_date": TRIP_END})
        tid = r.json()["trip_id"]
        try:
            assert _mk(owner, tid, "TEST_Only", "Roma, IT").status_code == 201
            s = owner.get(f"{API}/trips/{tid}/summary").json()
            assert s["total_km"] is None, s
        finally:
            owner.delete(f"{API}/trips/{tid}")

    def test_manual_override_counted_in_total(self, owner, trip):
        tid = trip["trip_id"]
        r = _mk(owner, tid, "TEST_Manual", "Bologna, IT",
                km_from_prev=100.0, km_manual_override=True)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["km_from_prev"] == 100.0, d
        s = owner.get(f"{API}/trips/{tid}/summary").json()
        assert abs(s["total_km"] - 923.5) < 0.05, s
        owner.delete(f"{API}/trips/{tid}/stops/{d['stop_id']}")
