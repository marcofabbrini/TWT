"""Final Polish Task 2 — GET /api/trips per-trip `summary` object."""
import os

import httpx
import pytest
from dotenv import dotenv_values

_fe = dotenv_values("/app/frontend/.env")
API_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")


def _client(email):
    c = httpx.Client(base_url=API_URL, timeout=60)
    r = c.post("/api/auth/dev-login", json={"email": email, "name": email.split("@")[0]})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def alice():
    c = _client("alice@twt.app")
    yield c
    c.close()


@pytest.fixture(scope="module")
def bob():
    c = _client("bob@twt.app")
    yield c
    c.close()


def _mk_trip(c, title, cur="EUR", start="2026-09-01", end="2026-09-20"):
    r = c.post("/api/trips", json={
        "title": title, "home_currency": cur,
        "start_date": start, "end_date": end})
    assert r.status_code == 201, r.text
    return r.json()["trip_id"]


def _find(c, tid):
    r = c.get("/api/trips")
    assert r.status_code == 200, r.text
    for t in r.json():
        if t["trip_id"] == tid:
            return t
    return None


# ── summary shape on a fresh trip ────────────────────────────────
def test_fresh_trip_summary_defaults(alice):
    tid = _mk_trip(alice, "TEST_SUM_fresh")
    try:
        t = _find(alice, tid)
        assert t is not None
        s = t.get("summary")
        assert s is not None, t
        assert set(["total_km", "total_cost_home_currency", "home_currency",
                    "has_missing_rates"]).issubset(s.keys())
        assert s["total_km"] is None
        assert s["total_cost_home_currency"] == 0.0
        assert isinstance(s["total_cost_home_currency"], float)
        assert s["home_currency"] == "EUR"
        assert s["has_missing_rates"] is False
        assert "_id" not in t
    finally:
        alice.delete(f"/api/trips/{tid}")


# ── total_km aggregation ─────────────────────────────────────────
def test_total_km_sums_stops(alice):
    tid = _mk_trip(alice, "TEST_SUM_km")
    try:
        for i, (title, loc, km) in enumerate([("A", "Roma", 100), ("B", "Milano", 50.5)]):
            r = alice.post(f"/api/trips/{tid}/stops", json={
                "title": title, "location": loc,
                "start_date": f"2026-09-0{i+1}", "end_date": f"2026-09-0{i+1}",
                "transport_mode": "car"})
            assert r.status_code == 201, r.text
            sid = r.json()["stop_id"]
            r2 = alice.patch(f"/api/trips/{tid}/stops/{sid}",
                             json={"km_from_prev": km, "km_manual_override": True})
            assert r2.status_code == 200, r2.text
            assert r2.json()["km_from_prev"] == km

        s = _find(alice, tid)["summary"]
        assert s["total_km"] == 150.5, s
    finally:
        alice.delete(f"/api/trips/{tid}")


# ── cost aggregation + conversion ────────────────────────────────
def test_total_cost_with_conversion(alice):
    tid = _mk_trip(alice, "TEST_SUM_cost")
    try:
        r = alice.post(f"/api/trips/{tid}/stops", json={
            "title": "S1", "location": "Roma",
            "start_date": "2026-09-01", "end_date": "2026-09-03",
            "transport_mode": "car"})
        sid = r.json()["stop_id"]
        r = alice.post(f"/api/trips/{tid}/stops/{sid}/hotels", json={
            "name": "TEST_H", "check_in": "2026-09-01", "check_out": "2026-09-03",
            "cost": 200, "currency": "EUR"})
        assert r.status_code == 201, r.text
        r = alice.put(f"/api/trips/{tid}/exchange-rates", json={
            "from_currency": "USD", "to_currency": "EUR", "rate": 0.9})
        assert r.status_code == 200, r.text
        r = alice.post(f"/api/trips/{tid}/expenses", json={
            "label": "TEST_E", "cost": 50, "currency": "USD"})
        assert r.status_code == 201, r.text

        s = _find(alice, tid)["summary"]
        assert s["total_cost_home_currency"] == 245.0, s
        assert s["has_missing_rates"] is False, s
    finally:
        alice.delete(f"/api/trips/{tid}")


def test_missing_rate_excluded_and_flagged(alice):
    tid = _mk_trip(alice, "TEST_SUM_missing")
    try:
        r = alice.post(f"/api/trips/{tid}/stops", json={
            "title": "S1", "location": "Roma",
            "start_date": "2026-09-01", "end_date": "2026-09-03",
            "transport_mode": "car"})
        sid = r.json()["stop_id"]
        r = alice.post(f"/api/trips/{tid}/stops/{sid}/hotels", json={
            "name": "TEST_H2", "check_in": "2026-09-01", "check_out": "2026-09-02",
            "cost": 100, "currency": "EUR"})
        assert r.status_code == 201, r.text
        r = alice.post(f"/api/trips/{tid}/expenses", json={
            "label": "TEST_GBP", "cost": 30, "currency": "GBP"})
        assert r.status_code == 201, r.text

        s = _find(alice, tid)["summary"]
        assert s["total_cost_home_currency"] == 100.0, s
        assert s["has_missing_rates"] is True, s
    finally:
        alice.delete(f"/api/trips/{tid}")


def test_attraction_costs_included(alice):
    tid = _mk_trip(alice, "TEST_SUM_attr")
    try:
        r = alice.post(f"/api/trips/{tid}/stops", json={
            "title": "S1", "location": "Roma",
            "start_date": "2026-09-01", "end_date": "2026-09-03",
            "transport_mode": "car"})
        sid = r.json()["stop_id"]
        r = alice.post(f"/api/trips/{tid}/stops/{sid}/attractions", json={
            "name": "TEST_A", "cost": 25.5, "currency": "EUR"})
        assert r.status_code == 201, r.text
        # zero-cost attraction must not break anything
        r = alice.post(f"/api/trips/{tid}/stops/{sid}/attractions", json={
            "name": "TEST_A0", "cost": 0, "currency": "EUR"})
        assert r.status_code == 201, r.text
        s = _find(alice, tid)["summary"]
        assert s["total_cost_home_currency"] == 25.5, s
        assert s["has_missing_rates"] is False, s
    finally:
        alice.delete(f"/api/trips/{tid}")


# ── isolation ────────────────────────────────────────────────────
def test_isolation_between_users(alice, bob):
    tid = _mk_trip(alice, "TEST_SUM_iso")
    try:
        assert _find(bob, tid) is None
        assert _find(alice, tid) is not None
    finally:
        alice.delete(f"/api/trips/{tid}")


# ── multiple trips / no N+1 explosion ────────────────────────────
def test_multiple_trips_all_have_summary(alice):
    tids = [_mk_trip(alice, f"TEST_SUM_multi_{i}") for i in range(3)]
    try:
        r = alice.get("/api/trips")
        assert r.status_code == 200
        found = [t for t in r.json() if t["trip_id"] in tids]
        assert len(found) == 3
        for t in found:
            assert "summary" in t and t["summary"]["home_currency"] == "EUR"
    finally:
        for tid in tids:
            alice.delete(f"/api/trips/{tid}")


# ── regression: other trip endpoints untouched ───────────────────
def test_get_single_trip_regression(alice):
    tid = _mk_trip(alice, "TEST_SUM_single")
    try:
        r = alice.get(f"/api/trips/{tid}")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["trip_id"] == tid and b["role"] == "owner"
        r = alice.patch(f"/api/trips/{tid}", json={"title": "TEST_SUM_single2"})
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "TEST_SUM_single2"
        r = alice.get(f"/api/trips/{tid}/summary")
        assert r.status_code == 200, r.text
    finally:
        alice.delete(f"/api/trips/{tid}")


def test_unauthenticated_list_trips():
    c = httpx.Client(base_url=API_URL, timeout=30)
    r = c.get("/api/trips")
    assert r.status_code in (401, 403), r.status_code
    c.close()
