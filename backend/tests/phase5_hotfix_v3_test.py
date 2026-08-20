"""Phase 5 hotfix v2 — independent verification of recompute-km idempotency.

Covers:
  * repeated no-op recomputes (updated_count=0, no version bump)
  * POSITIVE change path via direct Mongo write (stale km) -> updated_count>=1 + version bump
  * manual override never counted as changed
  * transport='other' regression
  * unknown-city stays in errors[] without bumping version
  * reorder trick: reorder-triggered recompute + follow-up explicit no-op
"""
import asyncio
import os

import httpx
import pytest
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

_fe = dotenv_values("/app/frontend/.env")
API_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not API_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

_be = dotenv_values("/app/backend/.env")
MONGO_URL = (os.environ.get("MONGO_URL") or _be.get("MONGO_URL") or "").strip('"')
DB_NAME = (os.environ.get("DB_NAME") or _be.get("DB_NAME") or "").strip('"')


def _login(email):
    c = httpx.Client(base_url=API_URL, timeout=30)
    r = c.post("/api/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def owner():
    c = _login("p5v3_owner@twt.app")
    yield c
    c.close()


@pytest.fixture()
def trip(owner):
    r = owner.post("/api/trips", json={
        "title": "TEST_P5v3",
        "home_currency": "EUR",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    })
    assert r.status_code == 201, r.text
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
    r = owner.get(f"/api/trips/{trip}/version")
    assert r.status_code == 200, r.text
    return r.json()["version"]


def _stops(owner, trip):
    r = owner.get(f"/api/trips/{trip}/stops")
    assert r.status_code == 200, r.text
    return r.json()


def _mongo_set(stop_id, fields):
    async def _run():
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            res = await cli[DB_NAME].stops.update_one({"stop_id": stop_id}, {"$set": fields})
            return res.matched_count
        finally:
            cli.close()
    return asyncio.run(_run())


def _mongo_get(stop_id):
    async def _run():
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            return await cli[DB_NAME].stops.find_one({"stop_id": stop_id}, {"_id": 0})
        finally:
            cli.close()
    return asyncio.run(_run())


# ── PRIMARY: idempotency over 3 consecutive recomputes ────────────────
def test_three_consecutive_recomputes_are_noop(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-09-01", "2026-09-02")
    _stop(owner, trip, "B", "Milano", "2026-09-03", "2026-09-04")
    _stop(owner, trip, "C", "Firenze", "2026-09-05", "2026-09-06")

    st = _stops(owner, trip)
    kms = {s["title"]: s["km_from_prev"] for s in st}
    assert kms["A"] is None
    assert kms["B"] == 574.0
    assert kms["C"] == 305.0

    v0 = _v(owner, trip)
    for i in range(3):
        r = owner.post(f"/api/trips/{trip}/recompute-km")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated_count"] == 0, f"call {i+1}: {body}"
        assert body["errors"] == [], body
    assert _v(owner, trip) == v0, "version bumped on no-op recompute"

    # km values unchanged
    st2 = _stops(owner, trip)
    assert {s["title"]: s["km_from_prev"] for s in st2} == kms


# ── POSITIVE change path via direct Mongo stale write ─────────────────
def test_stale_mongo_state_is_repaired_and_bumps_version_once(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-09-01", "2026-09-02")
    b = _stop(owner, trip, "B", "Milano", "2026-09-03", "2026-09-04")
    owner.post(f"/api/trips/{trip}/recompute-km")

    assert _mongo_set(b["stop_id"], {"km_from_prev": None, "km_calc_error": True}) == 1
    assert _mongo_get(b["stop_id"])["km_from_prev"] is None

    v0 = _v(owner, trip)
    r = owner.post(f"/api/trips/{trip}/recompute-km")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated_count"] >= 1, body
    assert body["errors"] == [], body
    v1 = _v(owner, trip)
    assert v1 != v0, "version must bump when a value actually changed"

    b_now = next(s for s in _stops(owner, trip) if s["stop_id"] == b["stop_id"])
    assert b_now["km_from_prev"] == 574.0
    assert b_now["km_calc_error"] is False

    # immediate follow-up is a no-op again
    body2 = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert body2["updated_count"] == 0, body2
    assert _v(owner, trip) == v1


def test_stale_wrong_value_is_overwritten(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-09-01", "2026-09-02")
    b = _stop(owner, trip, "B", "Napoli", "2026-09-03", "2026-09-04")
    owner.post(f"/api/trips/{trip}/recompute-km")

    _mongo_set(b["stop_id"], {"km_from_prev": 1.0, "km_calc_error": False})
    v0 = _v(owner, trip)
    body = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert body["updated_count"] == 1, body
    assert _v(owner, trip) != v0
    b_now = next(s for s in _stops(owner, trip) if s["stop_id"] == b["stop_id"])
    assert b_now["km_from_prev"] == 225.0


# ── Manual override ───────────────────────────────────────────────────
def test_manual_override_stays_and_never_changes(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-09-01", "2026-09-02")
    b = _stop(owner, trip, "B", "Milano", "2026-09-03", "2026-09-04")
    r = owner.patch(f"/api/trips/{trip}/stops/{b['stop_id']}",
                    json={"km_from_prev": 999, "km_manual_override": True})
    assert r.status_code == 200, r.text

    v0 = _v(owner, trip)
    for _ in range(2):
        body = owner.post(f"/api/trips/{trip}/recompute-km").json()
        assert body["updated_count"] == 0, body
    assert _v(owner, trip) == v0
    b_now = next(s for s in _stops(owner, trip) if s["stop_id"] == b["stop_id"])
    assert b_now["km_from_prev"] == 999
    assert b_now["km_manual_override"] is True


# ── transport='other' regression ──────────────────────────────────────
def test_transport_other_never_error_never_changed(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-09-01", "2026-09-02")
    b = _stop(owner, trip, "B", "Somewhere-Nowhere", "2026-09-03", "2026-09-04", transport="other")
    assert b["km_calc_error"] is False
    owner.post(f"/api/trips/{trip}/recompute-km")

    v0 = _v(owner, trip)
    for _ in range(2):
        body = owner.post(f"/api/trips/{trip}/recompute-km").json()
        assert body["updated_count"] == 0, body
        assert b["stop_id"] not in body["errors"], body
    assert _v(owner, trip) == v0
    b_now = next(s for s in _stops(owner, trip) if s["stop_id"] == b["stop_id"])
    assert b_now["km_calc_error"] is False
    assert b_now["km_from_prev"] is None


# ── unknown city stays in errors, no bump ─────────────────────────────
def test_unknown_city_error_is_sticky_without_version_bump(owner, trip):
    _stop(owner, trip, "A", "Roma", "2026-09-01", "2026-09-02")
    b = _stop(owner, trip, "B", "Zzqqx-Nonexistent", "2026-09-03", "2026-09-04")
    assert b["km_calc_error"] is True
    owner.post(f"/api/trips/{trip}/recompute-km")

    v0 = _v(owner, trip)
    for _ in range(3):
        body = owner.post(f"/api/trips/{trip}/recompute-km").json()
        assert b["stop_id"] in body["errors"], body
        assert body["updated_count"] == 0, body
    assert _v(owner, trip) == v0

    # Flip error -> computed: must count as changed and bump once.
    r = owner.patch(f"/api/trips/{trip}/stops/{b['stop_id']}", json={"location": "Firenze"})
    assert r.status_code == 200, r.text
    _mongo_set(b["stop_id"], {"km_from_prev": None, "km_calc_error": True})
    v1 = _v(owner, trip)
    body = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert body["updated_count"] == 1, body
    assert body["errors"] == [], body
    assert _v(owner, trip) != v1


# ── reorder trick ─────────────────────────────────────────────────────
def test_reorder_recompute_then_explicit_noop(owner, trip):
    a = _stop(owner, trip, "A", "Roma", "2026-09-01", "2026-09-02")
    b = _stop(owner, trip, "B", "Firenze", "2026-09-03", "2026-09-04")
    c = _stop(owner, trip, "C", "Napoli", "2026-09-05", "2026-09-06")

    v0 = _v(owner, trip)
    r = owner.post(f"/api/trips/{trip}/stops/reorder",
                   json={"stop_ids": [a["stop_id"], c["stop_id"], b["stop_id"]]})
    assert r.status_code == 200, r.text
    assert _v(owner, trip) != v0, "reorder must bump version"

    st = {s["stop_id"]: s for s in _stops(owner, trip)}
    # New order A(Roma) -> C(Napoli) -> B(Firenze)
    assert st[a["stop_id"]]["km_from_prev"] is None
    assert st[c["stop_id"]]["km_from_prev"] == 225.0          # Roma->Napoli
    assert st[b["stop_id"]]["km_from_prev"] is not None       # Napoli->Firenze (haversine fallback)
    napoli_firenze = st[b["stop_id"]]["km_from_prev"]

    v1 = _v(owner, trip)
    body = owner.post(f"/api/trips/{trip}/recompute-km").json()
    assert body["updated_count"] == 0, body
    assert _v(owner, trip) == v1
    st2 = {s["stop_id"]: s for s in _stops(owner, trip)}
    assert st2[b["stop_id"]]["km_from_prev"] == napoli_firenze
