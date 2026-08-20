"""TWT Phase 1 backend tests — health, auth (dev-login/me/logout), trips CRUD + isolation."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

ALICE = "alice@twt.app"
BOB = "bob@twt.app"


def dev_login(email, name=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name or email.split("@")[0]})
    return s, r


@pytest.fixture(scope="module")
def alice():
    s, r = dev_login(ALICE, "Alice")
    assert r.status_code == 200, r.text
    return s, r.json()


@pytest.fixture(scope="module")
def bob():
    s, r = dev_login(BOB, "Bob")
    assert r.status_code == 200, r.text
    return s, r.json()


@pytest.fixture(scope="module")
def created_trip_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(created_trip_ids):
    yield
    s, r = dev_login(ALICE, "Alice")
    for tid in created_trip_ids:
        s.delete(f"{API}/trips/{tid}")


# ── Health / meta ────────────────────────────────────────────
class TestHealth:
    def test_health(self):
        r = requests.get(f"{API}/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "env": "dev"}

    def test_openapi(self):
        r = requests.get(f"{API}/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/api/trips" in paths
        # currency immutability: PATCH exists since Phase 5 but never accepts home_currency
        trip_path = paths.get("/api/trips/{trip_id}", {})
        assert "patch" in trip_path
        assert "put" not in trip_path
        patch_props = (r.json()["components"]["schemas"]["TripUpdate"]["properties"])
        assert "home_currency" not in patch_props

    def test_root(self):
        r = requests.get(f"{API}/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── Auth ─────────────────────────────────────────────────────
class TestAuth:
    def test_dev_login_returns_user_cookie_and_token(self):
        s, r = dev_login(ALICE, "Alice")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["email"] == ALICE
        assert isinstance(data["user"]["user_id"], str)
        assert isinstance(data["session_token"], str) and data["session_token"]
        assert "twt_session" in s.cookies.get_dict()
        # httpOnly flag present in Set-Cookie header
        assert "httponly" in r.headers.get("set-cookie", "").lower()

    def test_me_unauthenticated_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_cookie(self, alice):
        s, data = alice
        r = s.get(f"{API}/auth/me")
        assert r.status_code == 200, r.text
        assert r.json()["email"] == ALICE
        assert r.json()["user_id"] == data["user"]["user_id"]

    def test_me_with_bearer(self):
        s, r = dev_login("carol@twt.app", "Carol")
        token = r.json()["session_token"]
        r2 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["email"] == "carol@twt.app"

    def test_me_invalid_token_401(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer nope-invalid"})
        assert r.status_code == 401

    def test_logout_invalidates_session(self):
        s, r = dev_login("dave@twt.app", "Dave")
        token = r.json()["session_token"]
        assert s.get(f"{API}/auth/me").status_code == 200
        out = s.post(f"{API}/auth/logout")
        assert out.status_code == 200
        assert out.json()["ok"] is True
        # bearer token also dead
        r2 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 401

    def test_dev_login_upsert_same_user(self):
        _, r1 = dev_login(ALICE, "Alice")
        _, r2 = dev_login(ALICE, "Alice")
        assert r1.json()["user"]["user_id"] == r2.json()["user"]["user_id"]

    def test_dev_login_invalid_email_422(self):
        r = requests.post(f"{API}/auth/dev-login", json={"email": "not-an-email"})
        assert r.status_code == 422

    def test_google_login_redirect(self):
        r = requests.get(f"{API}/auth/google/login", params={"redirect": f"{BASE_URL}/dashboard"},
                         allow_redirects=False)
        assert r.status_code == 302
        assert "auth.emergentagent.com" in r.headers["location"]

    def test_google_login_missing_redirect_400(self):
        r = requests.get(f"{API}/auth/google/login", allow_redirects=False)
        assert r.status_code == 400


# ── Trips ────────────────────────────────────────────────────
class TestTrips:
    def test_trips_require_auth(self):
        assert requests.get(f"{API}/trips").status_code == 401
        assert requests.post(f"{API}/trips", json={}).status_code == 401

    def test_create_trip_and_persistence(self, alice, created_trip_ids):
        s, data = alice
        payload = {
            "title": f"TEST_Trip {uuid.uuid4().hex[:6]}",
            "home_currency": "EUR",
            "start_date": "2026-05-01",
            "end_date": "2026-05-10",
        }
        r = s.post(f"{API}/trips", json=payload)
        assert r.status_code == 201, r.text
        t = r.json()
        created_trip_ids.append(t["trip_id"])
        assert t["owner_id"] == data["user"]["user_id"]
        assert t["title"] == payload["title"]
        assert t["home_currency"] == "EUR"
        assert t["start_date"] == "2026-05-01"
        assert "_id" not in t

        g = s.get(f"{API}/trips/{t['trip_id']}")
        assert g.status_code == 200
        gd = g.json()
        assert gd["title"] == payload["title"]
        assert gd["role"] == "owner"

    def test_create_trip_end_before_start_422(self, alice):
        s, _ = alice
        r = s.post(f"{API}/trips", json={
            "title": "TEST_bad", "home_currency": "EUR",
            "start_date": "2026-05-10", "end_date": "2026-05-01"})
        assert r.status_code == 422
        assert "end_date must be greater than or equal to start_date" in r.text

    def test_create_trip_bad_currency_422(self, alice):
        s, _ = alice
        r = s.post(f"{API}/trips", json={
            "title": "TEST_cur", "home_currency": "XXX",
            "start_date": "2026-05-01", "end_date": "2026-05-02"})
        assert r.status_code == 422

    def test_create_trip_empty_title_422(self, alice):
        s, _ = alice
        r = s.post(f"{API}/trips", json={
            "title": "", "home_currency": "EUR",
            "start_date": "2026-05-01", "end_date": "2026-05-02"})
        assert r.status_code == 422

    def test_list_trips_ordering_desc(self, alice, created_trip_ids):
        s, _ = alice
        for sd, ed in [("2026-01-05", "2026-01-09"), ("2026-09-05", "2026-09-09")]:
            r = s.post(f"{API}/trips", json={
                "title": f"TEST_order {sd}", "home_currency": "USD",
                "start_date": sd, "end_date": ed})
            assert r.status_code == 201
            created_trip_ids.append(r.json()["trip_id"])
        r = s.get(f"{API}/trips")
        assert r.status_code == 200
        dates = [t["start_date"] for t in r.json()]
        assert dates == sorted(dates, reverse=True)
        assert all(t["role"] in ("owner", "editor", "viewer") for t in r.json())

    def test_isolation_bob_cannot_see_alice_trips(self, alice, bob, created_trip_ids):
        sa, _ = alice
        sb, _ = bob
        r = sa.post(f"{API}/trips", json={
            "title": "TEST_isolation", "home_currency": "GBP",
            "start_date": "2026-06-01", "end_date": "2026-06-05"})
        assert r.status_code == 201
        tid = r.json()["trip_id"]
        created_trip_ids.append(tid)

        bob_trips = sb.get(f"{API}/trips")
        assert bob_trips.status_code == 200
        assert tid not in [t["trip_id"] for t in bob_trips.json()]
        # non-member detail -> 404
        assert sb.get(f"{API}/trips/{tid}").status_code == 404
        # non-member delete -> 403/404
        assert sb.delete(f"{API}/trips/{tid}").status_code in (403, 404)
        # still exists for alice
        assert sa.get(f"{API}/trips/{tid}").status_code == 200

    def test_get_nonexistent_trip_404(self, alice):
        s, _ = alice
        assert s.get(f"{API}/trips/trip_doesnotexist").status_code == 404

    def test_delete_trip_cascade(self, alice):
        s, _ = alice
        r = s.post(f"{API}/trips", json={
            "title": "TEST_delete", "home_currency": "CHF",
            "start_date": "2026-07-01", "end_date": "2026-07-03"})
        tid = r.json()["trip_id"]
        d = s.delete(f"{API}/trips/{tid}")
        assert d.status_code == 204
        assert s.get(f"{API}/trips/{tid}").status_code == 404
        assert tid not in [t["trip_id"] for t in s.get(f"{API}/trips").json()]

    def test_no_patch_route(self, alice, created_trip_ids):
        s, _ = alice
        r = s.post(f"{API}/trips", json={
            "title": "TEST_patch", "home_currency": "JPY",
            "start_date": "2026-08-01", "end_date": "2026-08-03"})
        tid = r.json()["trip_id"]
        created_trip_ids.append(tid)
        # Phase 5: PATCH exists (owner-only) but home_currency stays immutable
        # because TripUpdate has no home_currency field (extra keys ignored).
        p = s.patch(f"{API}/trips/{tid}", json={"home_currency": "USD"})
        assert p.status_code == 200, f"{p.status_code} {p.text[:200]}"
        assert p.json()["home_currency"] == "JPY"
        assert s.get(f"{API}/trips/{tid}").json()["home_currency"] == "JPY"
        assert s.get(f"{API}/trips/{tid}").json()["home_currency"] == "JPY"
