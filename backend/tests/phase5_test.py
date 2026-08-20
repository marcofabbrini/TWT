"""Phase 5 tests — Trip PATCH, KM auto-calc (ORS_MOCK), recompute-km, cancellation alerts."""
import os
import uuid
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
TODAY = date.today()


def _uniq(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}@twt.app"


def dev_login(email, name=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name or email.split("@")[0]}, timeout=30)
    assert r.status_code == 200, f"dev-login failed {r.status_code} {r.text[:300]}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['session_token']}"})
    return s, data["user"]


def dev_login_as(email, trip_id, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login-as", json={"email": email, "trip_id": trip_id, "role": role}, timeout=30)
    assert r.status_code == 200, f"dev-login-as failed {r.status_code} {r.text[:300]}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['session_token']}"})
    return s, data["user"]


def create_trip(sess, title="TEST_P5 Trip", home="EUR", start="2026-05-01", end="2026-05-15"):
    r = sess.post(f"{API}/trips", json={
        "title": title, "start_date": start, "end_date": end, "home_currency": home,
    }, timeout=30)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    return r.json()


def create_stop(sess, trip_id, title, location, start, end, mode="car", **extra):
    payload = {"title": title, "location": location, "start_date": start,
               "end_date": end, "transport_mode": mode}
    payload.update(extra)
    r = sess.post(f"{API}/trips/{trip_id}/stops", json=payload, timeout=60)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    return r.json()


def list_stops(sess, trip_id):
    r = sess.get(f"{API}/trips/{trip_id}/stops", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


def get_version(sess, trip_id):
    r = sess.get(f"{API}/trips/{trip_id}/version", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()["version"]


@pytest.fixture(scope="module")
def owner():
    return dev_login(_uniq("p5owner_"))


# ── PATCH /api/trips/{id} ────────────────────────────────
class TestTripPatch:
    def test_patch_title_and_dates(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 Patch")
        r = sess.patch(f"{API}/trips/{trip['trip_id']}", json={
            "title": "  TEST_P5 Renamed  ", "start_date": "2026-05-02", "end_date": "2026-05-20",
            "cover_image_url": "https://example.com/x.jpg",
        }, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert d["title"] == "TEST_P5 Renamed"
        assert d["start_date"] == "2026-05-02"
        assert d["end_date"] == "2026-05-20"
        assert d["cover_image_url"] == "https://example.com/x.jpg"
        # GET to verify persistence
        g = sess.get(f"{API}/trips/{trip['trip_id']}", timeout=30).json()
        assert g["title"] == "TEST_P5 Renamed"
        assert g["start_date"] == "2026-05-02"
        assert g["end_date"] == "2026-05-20"

    def test_patch_home_currency_ignored(self, owner):
        sess, _ = owner
        trip = create_trip(sess, home="EUR")
        r = sess.patch(f"{API}/trips/{trip['trip_id']}", json={"home_currency": "USD", "title": "TEST_P5 cur"}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json()["home_currency"] == "EUR"
        g = sess.get(f"{API}/trips/{trip['trip_id']}", timeout=30).json()
        assert g["home_currency"] == "EUR", "home_currency must be immutable"

    def test_patch_bumps_version(self, owner):
        sess, _ = owner
        trip = create_trip(sess)
        v0 = get_version(sess, trip["trip_id"])
        r = sess.patch(f"{API}/trips/{trip['trip_id']}", json={"title": "TEST_P5 v"}, timeout=30)
        assert r.status_code == 200
        assert get_version(sess, trip["trip_id"]) > v0

    def test_patch_end_before_start_422(self, owner):
        sess, _ = owner
        trip = create_trip(sess)
        r = sess.patch(f"{API}/trips/{trip['trip_id']}", json={"end_date": "2026-04-01"}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"

    def test_patch_stops_out_of_range_422(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 OOR", start="2026-05-01", end="2026-05-15")
        stop = create_stop(sess, trip["trip_id"], "TEST_Roma", "Roma, IT", "2026-05-08", "2026-05-10")
        r = sess.patch(f"{API}/trips/{trip['trip_id']}", json={"start_date": "2026-05-12"}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict), f"detail should be object: {detail}"
        assert "message" in detail
        ids = [s["stop_id"] for s in detail["stops_out_of_range"]]
        titles = [s["title"] for s in detail["stops_out_of_range"]]
        assert stop["stop_id"] in ids
        assert "TEST_Roma" in titles
        assert detail["new_range"] == {"start": "2026-05-12", "end": "2026-05-15"}
        # unchanged
        g = sess.get(f"{API}/trips/{trip['trip_id']}", timeout=30).json()
        assert g["start_date"] == "2026-05-01"

        # A narrowing PATCH that keeps the stop inside the range succeeds.
        ok = sess.patch(f"{API}/trips/{trip['trip_id']}", json={
            "start_date": "2026-05-05", "end_date": "2026-05-12"}, timeout=30)
        assert ok.status_code == 200, f"{ok.status_code} {ok.text[:300]}"
        assert ok.json()["start_date"] == "2026-05-05"

    def test_patch_role_permissions(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 Roles")
        ed, _ = dev_login_as(_uniq("p5ed_"), trip["trip_id"], "editor")
        vw, _ = dev_login_as(_uniq("p5vw_"), trip["trip_id"], "viewer")
        for s, role in ((ed, "editor"), (vw, "viewer")):
            r = s.patch(f"{API}/trips/{trip['trip_id']}", json={"title": f"TEST_hack_{role}"}, timeout=30)
            assert r.status_code == 403, f"{role} got {r.status_code} {r.text[:200]}"

    def test_patch_unauthenticated_401(self, owner):
        sess, _ = owner
        trip = create_trip(sess)
        r = requests.patch(f"{API}/trips/{trip['trip_id']}", json={"title": "TEST_x"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_patch_unknown_trip_404(self, owner):
        sess, _ = owner
        r = sess.patch(f"{API}/trips/trip_doesnotexist", json={"title": "TEST_x"}, timeout=30)
        assert r.status_code == 404


# ── KM auto-calc with ORS_MOCK=1 ────────────────────────
class TestKmMock:
    def test_km_seed_trip(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 KM")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_Roma", "Roma, IT", "2026-05-01", "2026-05-03")
        create_stop(sess, tid, "TEST_Milano", "Milano, IT", "2026-05-03", "2026-05-06", mode="car")
        create_stop(sess, tid, "TEST_Firenze", "Firenze, IT", "2026-05-06", "2026-05-08", mode="plane")
        stops = list_stops(sess, tid)
        kms = [s["km_from_prev"] for s in stops]
        assert kms[0] is None, kms
        assert kms[1] == 574.0, kms
        assert kms[2] == pytest.approx(249.5, abs=1.0), kms

    def test_stop_response_exposes_km_calc_error_field(self, owner):
        """SPEC: km_calc_error must be part of the Stop API payload (models.Stop)."""
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 calcerrfield")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_Roma", "Roma, IT", "2026-05-01", "2026-05-02")
        stops = list_stops(sess, tid)
        assert "km_calc_error" in stops[0], f"km_calc_error absent from Stop payload: {stops[0].keys()}"

    def test_create_stop_response_returns_computed_km(self, owner):
        """SPEC: km auto-calc on create — the POST response should carry the computed km."""
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 createkm")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_Roma", "Roma, IT", "2026-05-01", "2026-05-02")
        b = create_stop(sess, tid, "TEST_Milano", "Milano, IT", "2026-05-02", "2026-05-03", mode="car")
        assert b["km_from_prev"] == 574.0, f"stale POST response: {b['km_from_prev']}"

    @pytest.mark.parametrize("a,b,expected", [
        ("Roma, IT", "Napoli, IT", 225.0),
        ("London, UK", "Paris, FR", 460.0),
        ("Lisbon, PT", "Sintra, PT", 30.0),
    ])
    def test_km_pairs_car(self, owner, a, b, expected):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 pair")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_A", a, "2026-05-01", "2026-05-02")
        create_stop(sess, tid, "TEST_B", b, "2026-05-02", "2026-05-03", mode="car")
        stops = list_stops(sess, tid)
        assert stops[1]["km_from_prev"] == expected, stops

    def test_km_unknown_city_error_flag(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 unknown")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_A", "Roma, IT", "2026-05-01", "2026-05-02")
        create_stop(sess, tid, "TEST_B", "Zzyzxville, XX", "2026-05-02", "2026-05-03", mode="car")
        stops = list_stops(sess, tid)
        assert stops[1]["km_from_prev"] is None, stops
        assert stops[1].get("km_calc_error") is True, f"km_calc_error not exposed/true: {stops[1]}"

    def test_km_transport_other_is_null(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 other")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_A", "Roma, IT", "2026-05-01", "2026-05-02")
        create_stop(sess, tid, "TEST_B", "Milano, IT", "2026-05-02", "2026-05-03", mode="other")
        stops = list_stops(sess, tid)
        assert stops[1]["km_from_prev"] is None, stops

    def test_km_recalc_on_patch_location_and_mode(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 patchkm")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_A", "Roma, IT", "2026-05-01", "2026-05-02")
        b = create_stop(sess, tid, "TEST_B", "Milano, IT", "2026-05-02", "2026-05-03", mode="car")
        assert list_stops(sess, tid)[1]["km_from_prev"] == 574.0
        # change location → Napoli (car) = 225
        r = sess.patch(f"{API}/trips/{tid}/stops/{b['stop_id']}", json={"location": "Napoli, IT"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["km_from_prev"] == 225.0, r.json()
        # change transport_mode → plane (haversine Roma-Napoli ≈ 188)
        r2 = sess.patch(f"{API}/trips/{tid}/stops/{b['stop_id']}", json={"transport_mode": "plane"}, timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        assert r2.json()["km_from_prev"] == pytest.approx(188.0, abs=3.0), r2.json()

    def test_km_recalc_on_reorder(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 reorder")
        tid = trip["trip_id"]
        a = create_stop(sess, tid, "TEST_Roma", "Roma, IT", "2026-05-01", "2026-05-02")
        b = create_stop(sess, tid, "TEST_Milano", "Milano, IT", "2026-05-02", "2026-05-03", mode="car")
        c = create_stop(sess, tid, "TEST_Firenze", "Firenze, IT", "2026-05-03", "2026-05-04", mode="car")
        pre = [s["km_from_prev"] for s in list_stops(sess, tid)]
        assert pre == [None, 574.0, 305.0], pre
        r = sess.post(f"{API}/trips/{tid}/stops/reorder",
                      json={"stop_ids": [a["stop_id"], c["stop_id"], b["stop_id"]]}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        post = [(s["title"], s["km_from_prev"]) for s in list_stops(sess, tid)]
        assert post == [("TEST_Roma", None), ("TEST_Firenze", 275.0), ("TEST_Milano", 305.0)], post

    def test_manual_override_survives_reorder(self, owner):
        sess, _ = owner
        trip = create_trip(sess, title="TEST_P5 manual")
        tid = trip["trip_id"]
        a = create_stop(sess, tid, "TEST_Roma", "Roma, IT", "2026-05-01", "2026-05-02")
        b = create_stop(sess, tid, "TEST_Milano", "Milano, IT", "2026-05-02", "2026-05-03", mode="car")
        c = create_stop(sess, tid, "TEST_Firenze", "Firenze, IT", "2026-05-03", "2026-05-04", mode="car")
        r = sess.patch(f"{API}/trips/{tid}/stops/{b['stop_id']}",
                       json={"km_from_prev": 999, "km_manual_override": True}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["km_from_prev"] == 999
        assert r.json()["km_manual_override"] is True
        # reorder must not overwrite manual value
        rr = sess.post(f"{API}/trips/{tid}/stops/reorder",
                       json={"stop_ids": [a["stop_id"], c["stop_id"], b["stop_id"]]}, timeout=60)
        assert rr.status_code == 200, rr.text[:300]
        by_id = {s["stop_id"]: s for s in list_stops(sess, tid)}
        assert by_id[b["stop_id"]]["km_from_prev"] == 999, by_id[b["stop_id"]]
        # recompute-km also must not overwrite it
        rc = sess.post(f"{API}/trips/{tid}/recompute-km", timeout=60)
        assert rc.status_code == 200, rc.text[:300]
        by_id2 = {s["stop_id"]: s for s in list_stops(sess, tid)}
        assert by_id2[b["stop_id"]]["km_from_prev"] == 999


# ── POST /trips/{id}/recompute-km ───────────────────────
class TestRecomputeKm:
    def test_recompute_roles_and_payload(self):
        sess, _ = dev_login(_uniq("p5rc_"))
        trip = create_trip(sess, title="TEST_P5 recompute")
        tid = trip["trip_id"]
        create_stop(sess, tid, "TEST_Roma", "Roma, IT", "2026-05-01", "2026-05-02")
        create_stop(sess, tid, "TEST_Milano", "Milano, IT", "2026-05-02", "2026-05-03", mode="car")
        create_stop(sess, tid, "TEST_Bad", "Nowherecity, ZZ", "2026-05-03", "2026-05-04", mode="car")

        r = sess.post(f"{API}/trips/{tid}/recompute-km", timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert set(data.keys()) == {"updated_count", "errors"}
        # Hotfix v2 semantics: create-time inline recompute already persisted the
        # correct values, so an explicit recompute changes nothing → 0.
        assert data["updated_count"] == 0, data
        assert len(data["errors"]) == 1, data

        ed, _ = dev_login_as(_uniq("p5rced_"), tid, "editor")
        assert ed.post(f"{API}/trips/{tid}/recompute-km", timeout=60).status_code == 200
        vw, _ = dev_login_as(_uniq("p5rcvw_"), tid, "viewer")
        assert vw.post(f"{API}/trips/{tid}/recompute-km", timeout=60).status_code == 403
        assert requests.post(f"{API}/trips/{tid}/recompute-km", timeout=30).status_code in (401, 403)


# ── GET /api/notifications/cancellation-alerts ──────────
class TestCancellationAlerts:
    @pytest.fixture(scope="class")
    def alert_setup(self):
        sess, user = dev_login(_uniq("p5alert_"))
        start = TODAY - timedelta(days=5)
        end = TODAY + timedelta(days=60)
        trip = create_trip(sess, title="TEST_P5 Alerts", start=start.isoformat(), end=end.isoformat())
        tid = trip["trip_id"]
        stop = create_stop(sess, tid, "TEST_AlertStop", "Roma, IT",
                           start.isoformat(), (start + timedelta(days=2)).isoformat())
        hotels = {}
        specs = {
            "past": -3, "red0": 0, "red3": 3, "yellow5": 5, "yellow7": 7, "outside": 20,
        }
        for key, delta in specs.items():
            r = sess.post(f"{API}/trips/{tid}/stops/{stop['stop_id']}/hotels", json={
                "name": f"TEST_Hotel_{key}",
                "check_in": start.isoformat(),
                "check_out": (start + timedelta(days=1)).isoformat(),
                "cost": 100,
                "cancellation_deadline": (TODAY + timedelta(days=delta)).isoformat(),
            }, timeout=30)
            assert r.status_code in (200, 201), f"{key}: {r.status_code} {r.text[:300]}"
            hotels[key] = r.json()
        # hotel with no deadline must not appear
        r = sess.post(f"{API}/trips/{tid}/stops/{stop['stop_id']}/hotels", json={
            "name": "TEST_Hotel_nodeadline", "check_in": start.isoformat(),
            "check_out": (start + timedelta(days=1)).isoformat(), "cost": 50,
        }, timeout=30)
        assert r.status_code in (200, 201)
        hotels["nodeadline"] = r.json()
        return sess, user, trip, stop, hotels

    def test_requires_auth(self):
        r = requests.get(f"{API}/notifications/cancellation-alerts", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_alerts_window_severity_sort(self, alert_setup):
        sess, _, trip, stop, hotels = alert_setup
        r = sess.get(f"{API}/notifications/cancellation-alerts", timeout=30)
        assert r.status_code == 200, r.text[:300]
        alerts = r.json()
        assert isinstance(alerts, list)
        mine = [a for a in alerts if a["trip_id"] == trip["trip_id"]]
        by_hotel = {a["hotel_id"]: a for a in mine}

        included = ["past", "red0", "red3", "yellow5", "yellow7"]
        for k in included:
            assert hotels[k]["hotel_id"] in by_hotel, f"{k} missing from alerts"
        for k in ("outside", "nodeadline"):
            assert hotels[k]["hotel_id"] not in by_hotel, f"{k} should be excluded"

        # severity + fields
        assert by_hotel[hotels["past"]["hotel_id"]]["days_until"] == -3
        assert by_hotel[hotels["past"]["hotel_id"]]["severity"] == "red"
        assert by_hotel[hotels["red0"]["hotel_id"]]["severity"] == "red"
        assert by_hotel[hotels["red3"]["hotel_id"]]["severity"] == "red"
        assert by_hotel[hotels["yellow5"]["hotel_id"]]["severity"] == "yellow"
        assert by_hotel[hotels["yellow7"]["hotel_id"]]["severity"] == "yellow"

        a = by_hotel[hotels["red3"]["hotel_id"]]
        assert a["trip_title"] == "TEST_P5 Alerts"
        assert a["hotel_name"] == "TEST_Hotel_red3"
        assert a["stop_title"] == "TEST_AlertStop"
        assert a["cancellation_deadline"] == (TODAY + timedelta(days=3)).isoformat()
        assert a["days_until"] == 3
        assert "_id" not in a

        days = [x["days_until"] for x in alerts]
        assert days == sorted(days), f"not sorted asc: {days}"

    def test_alerts_isolation_and_membership(self, alert_setup):
        sess, _, trip, _, hotels = alert_setup
        # a stranger sees none of this trip's alerts
        other, _ = dev_login(_uniq("p5stranger_"))
        r = other.get(f"{API}/notifications/cancellation-alerts", timeout=30)
        assert r.status_code == 200
        assert all(a["trip_id"] != trip["trip_id"] for a in r.json())
        # an accepted viewer member does see them (aggregated across memberships)
        vw, _ = dev_login_as(_uniq("p5alertvw_"), trip["trip_id"], "viewer")
        r2 = vw.get(f"{API}/notifications/cancellation-alerts", timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        ids = {a["hotel_id"] for a in r2.json()}
        assert hotels["red3"]["hotel_id"] in ids


# ── OpenAPI ─────────────────────────────────────────────
def test_openapi_lists_phase5_routes():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=30)
    assert r.status_code == 200, r.status_code
    paths = r.json()["paths"]
    assert "patch" in paths["/api/trips/{trip_id}"]
    assert "/api/trips/{trip_id}/recompute-km" in paths
    assert "/api/notifications/cancellation-alerts" in paths
