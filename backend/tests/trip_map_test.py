"""Trip Map feature tests — GET /api/trips/{trip_id}/route-geometry + route_cache."""
import os
import time

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = backend_env.get("MONGO_URL") or os.environ.get("MONGO_URL")
DB_NAME = backend_env.get("DB_NAME") or os.environ.get("DB_NAME")


# ── fixtures ────────────────────────────────────────────
@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def _login(email, name):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name})
    assert r.status_code == 200, f"dev-login failed {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def owner():
    return _login("mapowner@twt.app", "Map Owner")


@pytest.fixture(scope="module")
def outsider():
    return _login("mapoutsider@twt.app", "Map Outsider")


@pytest.fixture(scope="module")
def created_trip_ids():
    return []


def _mk_trip(sess, title, created_trip_ids):
    r = sess.post(f"{API}/trips", json={
        "title": title, "home_currency": "EUR",
        "start_date": "2026-09-01", "end_date": "2026-09-20",
    })
    assert r.status_code == 201, r.text[:300]
    tid = r.json()["trip_id"]
    created_trip_ids.append((sess, tid))
    return tid


def _mk_stop(sess, tid, title, location, mode="car", sd="2026-09-01", ed="2026-09-03"):
    r = sess.post(f"{API}/trips/{tid}/stops", json={
        "title": title, "location": location, "start_date": sd, "end_date": ed,
        "transport_mode": mode,
    })
    assert r.status_code == 201, r.text[:300]
    return r.json()["stop_id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup(created_trip_ids):
    yield
    for sess, tid in created_trip_ids:
        sess.delete(f"{API}/trips/{tid}")


# ── auth / permissions ──────────────────────────────────
class TestRouteGeometryAuth:
    def test_401_without_cookie(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_auth", created_trip_ids)
        r = requests.get(f"{API}/trips/{tid}/route-geometry")
        assert r.status_code == 401, r.status_code

    def test_404_for_non_member(self, owner, outsider, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_auth2", created_trip_ids)
        r = outsider.get(f"{API}/trips/{tid}/route-geometry")
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_200_for_owner(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_auth3", created_trip_ids)
        r = owner.get(f"{API}/trips/{tid}/route-geometry")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"stops", "routes"}

    def test_200_for_editor_and_viewer(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_roles", created_trip_ids)
        _mk_stop(owner, tid, "TEST_Roma", "Roma")
        for email, role in [("mapeditor@twt.app", "editor"), ("mapviewer@twt.app", "viewer")]:
            s = requests.Session()
            r = s.post(f"{API}/auth/dev-login-as", json={
                "email": email, "trip_id": tid, "role": role})
            assert r.status_code == 200, r.text[:300]
            g = s.get(f"{API}/trips/{tid}/route-geometry")
            assert g.status_code == 200, f"{role}: {g.status_code} {g.text[:200]}"
            assert len(g.json()["stops"]) == 1

    def test_404_unknown_trip(self, owner):
        r = owner.get(f"{API}/trips/trip_doesnotexist/route-geometry")
        assert r.status_code == 404


# ── payload shape ───────────────────────────────────────
class TestRouteGeometryShape:
    def test_zero_stops(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_empty", created_trip_ids)
        b = owner.get(f"{API}/trips/{tid}/route-geometry").json()
        assert b["stops"] == []
        assert b["routes"] == []

    def test_one_stop(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_one", created_trip_ids)
        sid = _mk_stop(owner, tid, "TEST_Roma", "Roma")
        b = owner.get(f"{API}/trips/{tid}/route-geometry").json()
        assert len(b["stops"]) == 1
        assert b["routes"] == []
        s = b["stops"][0]
        for k in ("stop_id", "order", "title", "location", "transport_mode",
                  "coords", "start_date", "end_date", "km_from_prev"):
            assert k in s, f"missing key {k}"
        assert s["stop_id"] == sid
        assert s["order"] == 0
        assert s["coords"] is not None and len(s["coords"]) == 2
        assert abs(s["coords"][0] - 12.4964) < 0.5 and abs(s["coords"][1] - 41.9028) < 0.5
        assert "_id" not in s

    def test_ungeocodable_stop_coords_null(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_nogeo", created_trip_ids)
        _mk_stop(owner, tid, "TEST_Nowhere", "Zzqxwvblorpland 99999")
        b = owner.get(f"{API}/trips/{tid}/route-geometry").json()
        assert b["stops"][0]["coords"] is None


class TestRouteModes:
    def test_car_two_stops(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_car", created_trip_ids)
        _mk_stop(owner, tid, "TEST_Roma", "Roma", "car")
        _mk_stop(owner, tid, "TEST_Milano", "Milano", "car", "2026-09-04", "2026-09-06")
        b = owner.get(f"{API}/trips/{tid}/route-geometry").json()
        assert len(b["routes"]) == 1
        r = b["routes"][0]
        assert r["transport_mode"] == "car"
        assert set(r.keys()) == {"from_stop_id", "to_stop_id", "transport_mode",
                                 "geojson", "distance_m", "duration_s"}
        if r["geojson"] is not None:
            assert r["geojson"]["type"] == "LineString"
            assert len(r["geojson"]["coordinates"]) > 2
            assert r["distance_m"] > 0
            assert r["duration_s"] > 0

    def test_plane_haversine_no_ors_cache(self, owner, created_trip_ids, mongo):
        tid = _mk_trip(owner, "TEST_MAP_plane", created_trip_ids)
        _mk_stop(owner, tid, "TEST_Roma", "Roma", "car")
        _mk_stop(owner, tid, "TEST_London", "London", "plane", "2026-09-05", "2026-09-08")
        b = owner.get(f"{API}/trips/{tid}/route-geometry").json()
        planes = [r for r in b["routes"] if r["transport_mode"] == "plane"]
        assert len(planes) == 1
        p = planes[0]
        assert p["geojson"] is None
        assert p["distance_m"] and p["distance_m"] > 0
        # Roma→London great circle ≈ 1430 km
        assert 1_300_000 < p["distance_m"] < 1_600_000, p["distance_m"]
        assert p["duration_s"] is None
        assert mongo.route_cache.count_documents({"transport_mode": "plane"}) == 0

    def test_other_all_null(self, owner, created_trip_ids, mongo):
        tid = _mk_trip(owner, "TEST_MAP_other", created_trip_ids)
        _mk_stop(owner, tid, "TEST_Roma", "Roma", "car")
        _mk_stop(owner, tid, "TEST_Napoli", "Napoli", "other", "2026-09-05", "2026-09-08")
        b = owner.get(f"{API}/trips/{tid}/route-geometry").json()
        o = [r for r in b["routes"] if r["transport_mode"] == "other"]
        assert len(o) == 1
        assert o[0]["geojson"] is None
        assert o[0]["distance_m"] is None
        assert o[0]["duration_s"] is None
        assert mongo.route_cache.count_documents({"transport_mode": "other"}) == 0


class TestRouteCache:
    def test_cache_write_and_hit(self, owner, created_trip_ids, mongo):
        mongo.route_cache.delete_many({"transport_mode": "train"})
        tid = _mk_trip(owner, "TEST_MAP_cache", created_trip_ids)
        _mk_stop(owner, tid, "TEST_Firenze", "Firenze", "car")
        _mk_stop(owner, tid, "TEST_Bologna", "Bologna", "train", "2026-09-05", "2026-09-08")

        t0 = time.time()
        r1 = owner.get(f"{API}/trips/{tid}/route-geometry")
        d1 = time.time() - t0
        assert r1.status_code == 200
        route1 = [r for r in r1.json()["routes"] if r["transport_mode"] == "train"][0]

        docs = list(mongo.route_cache.find({"transport_mode": "train"}))
        if route1["geojson"] is None:
            pytest.skip("ORS unavailable/mock — no cache record expected (graceful fallback)")
        assert len(docs) >= 1, "no route_cache record written after ORS success"
        doc = docs[0]
        for k in ("geojson", "distance_m", "duration_s", "cached_at",
                  "from_lng", "from_lat", "to_lng", "to_lat", "transport_mode"):
            assert k in doc, f"cache doc missing {k}"
        assert round(doc["from_lng"], 4) == doc["from_lng"]

        t0 = time.time()
        r2 = owner.get(f"{API}/trips/{tid}/route-geometry")
        d2 = time.time() - t0
        assert r2.status_code == 200
        route2 = [r for r in r2.json()["routes"] if r["transport_mode"] == "train"][0]
        assert route2["distance_m"] == route1["distance_m"]
        print(f"first={d1:.3f}s cached={d2:.3f}s")
        assert d2 < max(1.5, d1), f"cache hit not faster: first={d1:.3f} second={d2:.3f}"
        assert mongo.route_cache.count_documents({"transport_mode": "train"}) == len(docs)


# ── regression on existing endpoints ────────────────────
class TestRegression:
    def test_existing_endpoints(self, owner, created_trip_ids):
        tid = _mk_trip(owner, "TEST_MAP_reg", created_trip_ids)
        sid = _mk_stop(owner, tid, "TEST_Roma", "Roma")
        checks = [
            ("/trips", 200),
            (f"/trips/{tid}", 200),
            (f"/trips/{tid}/stops", 200),
            (f"/trips/{tid}/stops/{sid}/attractions", 200),
            (f"/trips/{tid}/stops/{sid}/hotels", 200),
            (f"/trips/{tid}/expenses", 200),
            (f"/trips/{tid}/members", 200),
            (f"/trips/{tid}/summary", 200),
            (f"/trips/{tid}/exchange-rates", 200),
            (f"/trips/{tid}/debts", 200),
            (f"/trips/{tid}/version", 200),
            ("/notifications/cancellation-alerts", 200),
        ]
        failures = []
        for path, exp in checks:
            r = owner.get(f"{API}{path}")
            if r.status_code != exp:
                failures.append((path, r.status_code, r.text[:120]))
        assert not failures, failures

    def test_openapi_contains_route_geometry(self):
        r = requests.get(f"{API}/openapi.json")
        assert r.status_code == 200
        assert "/api/trips/{trip_id}/route-geometry" in r.json()["paths"]
