"""Sprint A+B tests — Trip.home_location / has_return + Expense.expense_date."""
import os
from datetime import date, timedelta

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "sprint_ab@twt.app"
EDITOR_EMAIL = "sprint_ab_editor@twt.app"


def _login(email, name="Sprint AB"):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name}, timeout=30)
    assert r.status_code == 200, f"dev-login failed {r.status_code} {r.text[:300]}"
    tok = r.json().get("session_token")
    assert tok
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def owner():
    return _login(OWNER_EMAIL)


@pytest.fixture(scope="module")
def created_trip_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(owner, created_trip_ids):
    yield
    for tid in created_trip_ids:
        try:
            owner.delete(f"{API}/trips/{tid}", timeout=30)
        except Exception:
            pass


TODAY = date.today()
T_START = (TODAY - timedelta(days=2)).isoformat()
T_END = (TODAY + timedelta(days=5)).isoformat()


def _mk_trip(owner, created_trip_ids, **extra):
    payload = {
        "title": "TEST_SprintAB Trip",
        "home_currency": "EUR",
        "start_date": T_START,
        "end_date": T_END,
    }
    payload.update(extra)
    r = owner.post(f"{API}/trips", json=payload, timeout=30)
    if r.status_code == 201:
        created_trip_ids.append(r.json()["trip_id"])
    return r


# ── (A) Trip home_location / has_return ─────────────────────────────
class TestTripReturnFields:
    def test_create_baseline_defaults(self, owner, created_trip_ids):
        r = _mk_trip(owner, created_trip_ids)
        assert r.status_code == 201, r.text[:400]
        d = r.json()
        assert d["home_location"] is None
        assert d["has_return"] is False

    def test_create_has_return_without_home_422(self, owner, created_trip_ids):
        r = _mk_trip(owner, created_trip_ids, has_return=True)
        assert r.status_code == 422, f"expected 422, got {r.status_code} {r.text[:300]}"
        assert "home_location is required when has_return=true" in r.text

    def test_create_with_both_fields(self, owner, created_trip_ids):
        r = _mk_trip(owner, created_trip_ids, home_location="Roma, Italy", has_return=True)
        assert r.status_code == 201, r.text[:400]
        d = r.json()
        assert d["home_location"] == "Roma, Italy"
        assert d["has_return"] is True
        # GET by id echoes
        g = owner.get(f"{API}/trips/{d['trip_id']}", timeout=30)
        assert g.status_code == 200
        gd = g.json()
        assert gd["home_location"] == "Roma, Italy" and gd["has_return"] is True

    def test_patch_home_location_alone(self, owner, created_trip_ids):
        tid = _mk_trip(owner, created_trip_ids).json()["trip_id"]
        r = owner.patch(f"{API}/trips/{tid}", json={"home_location": "Milano"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["home_location"] == "Milano"
        assert r.json()["has_return"] is False

    def test_patch_enable_return_without_home_422(self, owner, created_trip_ids):
        tid = _mk_trip(owner, created_trip_ids).json()["trip_id"]
        r = owner.patch(f"{API}/trips/{tid}", json={"has_return": True}, timeout=30)
        assert r.status_code == 422, r.text[:300]
        assert "home_location is required when has_return=true" in r.text

    def test_patch_enable_return_with_home_in_one_call(self, owner, created_trip_ids):
        tid = _mk_trip(owner, created_trip_ids).json()["trip_id"]
        r = owner.patch(
            f"{API}/trips/{tid}",
            json={"has_return": True, "home_location": "Firenze"},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["has_return"] is True and r.json()["home_location"] == "Firenze"

    def test_patch_editor_forbidden(self, owner, created_trip_ids):
        tid = _mk_trip(owner, created_trip_ids).json()["trip_id"]
        s = requests.Session()
        r = s.post(
            f"{API}/auth/dev-login-as",
            json={"email": EDITOR_EMAIL, "trip_id": tid, "role": "editor"},
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text[:300]
        s.headers.update({"Authorization": f"Bearer {r.json()['session_token']}"})
        pr = s.patch(f"{API}/trips/{tid}", json={"home_location": "X"}, timeout=30)
        assert pr.status_code == 403, f"expected 403 got {pr.status_code} {pr.text[:200]}"

    def test_list_trips_contains_fields(self, owner, created_trip_ids):
        _mk_trip(owner, created_trip_ids)
        r = owner.get(f"{API}/trips", timeout=30)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list) and len(arr) > 0
        for t in arr:
            assert "home_location" in t, t
            assert "has_return" in t, t
            assert isinstance(t["has_return"], bool)


# ── route-geometry return_leg ───────────────────────────────────────
class TestReturnLeg:
    def _add_stop(self, owner, tid, title, location, order, sd, ed):
        return owner.post(
            f"{API}/trips/{tid}/stops",
            json={
                "title": title,
                "location": location,
                "order": order,
                "start_date": sd,
                "end_date": ed,
                "transport_mode": "car",
            },
            timeout=60,
        )

    def test_return_leg_present(self, owner, created_trip_ids):
        tid = _mk_trip(
            owner, created_trip_ids, home_location="Roma, Italy", has_return=True
        ).json()["trip_id"]
        r1 = self._add_stop(owner, tid, "TEST_Milano", "Milano, Italy", 0, T_START, T_START)
        assert r1.status_code == 201, r1.text[:300]
        r2 = self._add_stop(owner, tid, "TEST_Firenze", "Firenze, Italy", 1, T_END, T_END)
        assert r2.status_code == 201, r2.text[:300]
        last_stop_id = r2.json()["stop_id"]

        g = owner.get(f"{API}/trips/{tid}/route-geometry", timeout=60)
        assert g.status_code == 200, g.text[:400]
        leg = g.json().get("return_leg")
        assert leg is not None, "return_leg should not be null"
        assert leg["home_location"] == "Roma, Italy"
        assert leg["transport_mode"] == "car"
        assert leg["from_stop_id"] == last_stop_id
        assert leg["home_coords"] is None or (
            isinstance(leg["home_coords"], list) and len(leg["home_coords"]) == 2
        )
        # distance must be present (ORS or haversine fallback)
        assert leg["distance_m"] is not None and leg["distance_m"] > 0, leg
        if leg["geojson"] is not None:
            assert leg["geojson"]["type"] == "LineString"
            assert leg["duration_s"] is None or leg["duration_s"] > 0

    def test_return_leg_null_when_no_stops(self, owner, created_trip_ids):
        tid = _mk_trip(
            owner, created_trip_ids, home_location="Roma", has_return=True
        ).json()["trip_id"]
        g = owner.get(f"{API}/trips/{tid}/route-geometry", timeout=60)
        assert g.status_code == 200
        assert g.json()["return_leg"] is None

    def test_return_leg_null_when_has_return_false(self, owner, created_trip_ids):
        tid = _mk_trip(owner, created_trip_ids, home_location="Roma").json()["trip_id"]
        assert self._add_stop(
            owner, tid, "TEST_Napoli", "Napoli, Italy", 0, T_START, T_START
        ).status_code == 201
        g = owner.get(f"{API}/trips/{tid}/route-geometry", timeout=60)
        assert g.status_code == 200
        assert g.json()["return_leg"] is None


# ── (B) Expense.expense_date ────────────────────────────────────────
class TestExpenseDate:
    @pytest.fixture(scope="class")
    def trip_in_range(self, owner, created_trip_ids):
        return _mk_trip(owner, created_trip_ids).json()["trip_id"]

    @pytest.fixture(scope="class")
    def trip_future(self, owner, created_trip_ids):
        fs = (TODAY + timedelta(days=30)).isoformat()
        fe = (TODAY + timedelta(days=40)).isoformat()
        r = _mk_trip(owner, created_trip_ids, start_date=fs, end_date=fe)
        assert r.status_code == 201, r.text[:300]
        return r.json()["trip_id"], fs, fe

    def test_default_today_when_in_range(self, owner, trip_in_range):
        r = owner.post(
            f"{API}/trips/{trip_in_range}/expenses",
            json={"label": "TEST_default", "cost": 10},
            timeout=30,
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["expense_date"] == TODAY.isoformat()

    def test_default_trip_start_when_today_outside(self, owner, trip_future):
        tid, fs, _ = trip_future
        r = owner.post(
            f"{API}/trips/{tid}/expenses", json={"label": "TEST_defaultf", "cost": 5}, timeout=30
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["expense_date"] == fs

    def test_create_within_range(self, owner, trip_in_range):
        r = owner.post(
            f"{API}/trips/{trip_in_range}/expenses",
            json={"label": "TEST_in", "cost": 1, "expense_date": T_START},
            timeout=30,
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["expense_date"] == T_START

    def test_create_outside_range_422(self, owner, trip_in_range):
        bad = (TODAY + timedelta(days=90)).isoformat()
        r = owner.post(
            f"{API}/trips/{trip_in_range}/expenses",
            json={"label": "TEST_out", "cost": 1, "expense_date": bad},
            timeout=30,
        )
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
        assert "Expense date must be within trip range" in r.text

    def test_patch_expense_date(self, owner, trip_in_range):
        c = owner.post(
            f"{API}/trips/{trip_in_range}/expenses",
            json={"label": "TEST_patch", "cost": 2},
            timeout=30,
        )
        eid = c.json()["expense_id"]
        good = (TODAY + timedelta(days=1)).isoformat()
        r = owner.patch(
            f"{API}/trips/{trip_in_range}/expenses/{eid}",
            json={"expense_date": good},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["expense_date"] == good

        bad = (TODAY - timedelta(days=60)).isoformat()
        rb = owner.patch(
            f"{API}/trips/{trip_in_range}/expenses/{eid}",
            json={"expense_date": bad},
            timeout=30,
        )
        assert rb.status_code == 422, rb.text[:300]
        assert "Expense date must be within trip range" in rb.text

        # other fields update independently
        ro = owner.patch(
            f"{API}/trips/{trip_in_range}/expenses/{eid}",
            json={"label": "TEST_patched", "cost": 33.5},
            timeout=30,
        )
        assert ro.status_code == 200, ro.text[:300]
        assert ro.json()["label"] == "TEST_patched" and ro.json()["cost"] == 33.5
        assert ro.json()["expense_date"] == good  # unchanged

    def test_list_sorted_by_date_desc(self, owner, created_trip_ids):
        tid = _mk_trip(owner, created_trip_ids).json()["trip_id"]
        dates = [
            (TODAY + timedelta(days=1)).isoformat(),
            (TODAY - timedelta(days=2)).isoformat(),
            (TODAY + timedelta(days=4)).isoformat(),
        ]
        for i, d in enumerate(dates):
            r = owner.post(
                f"{API}/trips/{tid}/expenses",
                json={"label": f"TEST_s{i}", "cost": 1, "expense_date": d},
                timeout=30,
            )
            assert r.status_code == 201, r.text[:300]
        g = owner.get(f"{API}/trips/{tid}/expenses", timeout=30)
        assert g.status_code == 200
        got = [e["expense_date"] for e in g.json()]
        assert got == sorted(dates, reverse=True), got


# ── REGRESSION ──────────────────────────────────────────────────────
class TestRegression:
    def test_core_endpoints(self, owner, created_trip_ids):
        tid = _mk_trip(owner, created_trip_ids).json()["trip_id"]
        st = owner.post(
            f"{API}/trips/{tid}/stops",
            json={
                "title": "TEST_reg",
                "location": "Bologna, Italy",
                "order": 0,
                "start_date": T_START,
                "end_date": T_START,
                "transport_mode": "car",
            },
            timeout=60,
        )
        assert st.status_code == 201, st.text[:300]
        sid = st.json()["stop_id"]
        checks = {
            f"{API}/trips/{tid}/stops": None,
            f"{API}/trips/{tid}/stops/{sid}/attractions": None,
            f"{API}/trips/{tid}/stops/{sid}/hotels": None,
            f"{API}/trips/{tid}/expenses": None,
            f"{API}/trips/{tid}/members": None,
            f"{API}/trips/{tid}/exchange-rates": None,
            f"{API}/notifications/cancellation-alerts": None,
            f"{API}/trips/{tid}/route-geometry": None,
        }
        failures = []
        for url in checks:
            r = owner.get(url, timeout=60)
            if r.status_code != 200:
                failures.append((url, r.status_code, r.text[:120]))
        assert not failures, failures

    def test_openapi(self):
        r = requests.get(f"{API}/openapi.json", timeout=30)
        if r.status_code != 200:
            r = requests.get(f"{BASE_URL}/openapi.json", timeout=30)
        assert r.status_code == 200, r.status_code
