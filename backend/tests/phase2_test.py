"""TWT Phase 2 backend tests — stops, attractions, reorder (atomic), permissions."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")

ALICE = "alice@twt.app"
BOB = "bob@twt.app"

TRIP_START = "2030-06-01"
TRIP_END = "2030-06-30"


def dev_login(email, name=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name or email.split("@")[0]})
    assert r.status_code == 200, r.text
    return s, r.json()


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def alice():
    s, j = dev_login(ALICE, "Alice")
    return s


@pytest.fixture(scope="module")
def bob():
    s, j = dev_login(BOB, "Bob")
    return s


@pytest.fixture(scope="module")
def bob_id(bob):
    r = bob.get(f"{API}/auth/me")
    assert r.status_code == 200
    return r.json()["user_id"]


@pytest.fixture(scope="module")
def trip(alice):
    r = alice.post(f"{API}/trips", json={
        "title": f"TEST_P2_{uuid.uuid4().hex[:6]}",
        "home_currency": "EUR",
        "start_date": TRIP_START,
        "end_date": TRIP_END,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def cleanup(alice, trip):
    yield
    alice.delete(f"{API}/trips/{trip['trip_id']}")


def mk_stop(session, trip_id, title="TEST_Stop", start=TRIP_START, end=TRIP_START, **kw):
    body = {"title": title, "location": "Somewhere", "start_date": start,
            "end_date": end, "transport_mode": "car"}
    body.update(kw)
    return session.post(f"{API}/trips/{trip_id}/stops", json=body)


def mk_att(session, trip_id, stop_id, name="TEST_Att", **kw):
    body = {"name": name}
    body.update(kw)
    return session.post(f"{API}/trips/{trip_id}/stops/{stop_id}/attractions", json=body)


# ── OpenAPI exposes new routes ───────────────────────────────
class TestOpenAPI:
    def test_openapi_lists_phase2_routes(self):
        r = requests.get(f"{API}/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/api/trips/{trip_id}/stops" in paths
        assert "/api/trips/{trip_id}/stops/{stop_id}" in paths
        assert "/api/trips/{trip_id}/stops/reorder" in paths
        assert "/api/trips/{trip_id}/stops/{stop_id}/attractions" in paths
        assert "/api/trips/{trip_id}/attractions/{attraction_id}" in paths
        assert "/api/trips/{trip_id}/attractions/reorder" in paths


# ── Stops: list gating ───────────────────────────────────────
class TestStopsAccess:
    def test_list_empty_initially(self, alice):
        r = alice.post(f"{API}/trips", json={
            "title": f"TEST_P2_EMPTY_{uuid.uuid4().hex[:6]}",
            "home_currency": "EUR", "start_date": TRIP_START, "end_date": TRIP_END})
        assert r.status_code in (200, 201), r.text
        tid = r.json()["trip_id"]
        try:
            g = alice.get(f"{API}/trips/{tid}/stops")
            assert g.status_code == 200, g.text
            assert g.json() == []
        finally:
            alice.delete(f"{API}/trips/{tid}")

    def test_list_unauth_401(self, trip):
        r = requests.get(f"{API}/trips/{trip['trip_id']}/stops")
        assert r.status_code == 401

    def test_list_non_member_404(self, bob, trip):
        r = bob.get(f"{API}/trips/{trip['trip_id']}/stops")
        assert r.status_code == 404


# ── Stops: create + order ────────────────────────────────────
class TestStopsCreate:
    def test_create_stop_fields_and_order(self, alice, trip):
        tid = trip["trip_id"]
        r1 = mk_stop(alice, tid, "TEST_S1", TRIP_START, "2030-06-03",
                     departure_time="08:30", km_from_prev=12.5, notes="n1")
        assert r1.status_code == 201, r1.text
        s1 = r1.json()
        assert s1["stop_id"].startswith("stop_")
        assert s1["trip_id"] == tid
        assert s1["title"] == "TEST_S1"
        assert s1["location"] == "Somewhere"
        assert s1["start_date"] == TRIP_START
        assert s1["end_date"] == "2030-06-03"
        assert s1["transport_mode"] == "car"
        assert s1["departure_time"] == "08:30"
        assert s1["km_from_prev"] == 12.5
        assert s1["notes"] == "n1"
        base_order = s1["order"]

        r2 = mk_stop(alice, tid, "TEST_S2", "2030-06-04", "2030-06-06", transport_mode="train")
        assert r2.status_code == 201, r2.text
        assert r2.json()["order"] == base_order + 1

        # persistence
        lst = alice.get(f"{API}/trips/{tid}/stops").json()
        titles = [s["title"] for s in lst]
        assert "TEST_S1" in titles and "TEST_S2" in titles
        orders = [s["order"] for s in lst]
        assert orders == sorted(orders)

    def test_create_unauth_401(self, trip):
        r = requests.post(f"{API}/trips/{trip['trip_id']}/stops", json={
            "title": "x", "location": "y", "start_date": TRIP_START, "end_date": TRIP_START})
        assert r.status_code == 401


# ── Stops: validations ───────────────────────────────────────
class TestStopsValidation:
    def test_end_before_start_422(self, alice, trip):
        r = mk_stop(alice, trip["trip_id"], "TEST_bad", "2030-06-05", "2030-06-04")
        assert r.status_code == 422, r.text

    def test_dates_outside_trip_range_422(self, alice, trip):
        r = mk_stop(alice, trip["trip_id"], "TEST_out", "2030-05-01", "2030-05-02")
        assert r.status_code == 422, r.text
        detail = str(r.json().get("detail"))
        assert TRIP_START in detail and TRIP_END in detail, detail

    def test_end_after_trip_end_422(self, alice, trip):
        r = mk_stop(alice, trip["trip_id"], "TEST_out2", "2030-06-29", "2030-07-05")
        assert r.status_code == 422

    def test_invalid_transport_mode_422(self, alice, trip):
        r = mk_stop(alice, trip["trip_id"], "TEST_tm", transport_mode="rocket")
        assert r.status_code == 422

    def test_negative_km_422(self, alice, trip):
        r = mk_stop(alice, trip["trip_id"], "TEST_km", km_from_prev=-5)
        assert r.status_code == 422

    def test_bad_time_422(self, alice, trip):
        r = mk_stop(alice, trip["trip_id"], "TEST_time", departure_time="25:00")
        assert r.status_code == 422

    def test_empty_title_422(self, alice, trip):
        r = mk_stop(alice, trip["trip_id"], "")
        assert r.status_code == 422


# ── Stops: patch ─────────────────────────────────────────────
class TestStopsPatch:
    def test_partial_update_persists(self, alice, trip):
        tid = trip["trip_id"]
        sid = mk_stop(alice, tid, "TEST_patch", "2030-06-10", "2030-06-12").json()["stop_id"]
        r = alice.patch(f"{API}/trips/{tid}/stops/{sid}", json={"title": "TEST_patched", "notes": "hello"})
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "TEST_patched"
        assert r.json()["notes"] == "hello"
        assert r.json()["start_date"] == "2030-06-10"
        lst = alice.get(f"{API}/trips/{tid}/stops").json()
        got = [s for s in lst if s["stop_id"] == sid][0]
        assert got["title"] == "TEST_patched" and got["notes"] == "hello"

    def test_start_only_update_range_validated(self, alice, trip):
        tid = trip["trip_id"]
        sid = mk_stop(alice, tid, "TEST_patch2", "2030-06-10", "2030-06-12").json()["stop_id"]
        # start after end -> 422
        r = alice.patch(f"{API}/trips/{tid}/stops/{sid}", json={"start_date": "2030-06-20"})
        assert r.status_code == 422, r.text
        # start outside trip range -> 422
        r2 = alice.patch(f"{API}/trips/{tid}/stops/{sid}", json={"start_date": "2030-05-20"})
        assert r2.status_code == 422, r2.text
        # unchanged
        got = alice.get(f"{API}/trips/{tid}/stops").json()
        got = [s for s in got if s["stop_id"] == sid][0]
        assert got["start_date"] == "2030-06-10"

    def test_patch_unknown_stop_404(self, alice, trip):
        r = alice.patch(f"{API}/trips/{trip['trip_id']}/stops/stop_nope", json={"title": "x"})
        assert r.status_code == 404


# ── Stops: delete + cascade ──────────────────────────────────
class TestStopsDelete:
    def test_delete_cascades_attractions(self, alice, trip, mongo):
        tid = trip["trip_id"]
        sid = mk_stop(alice, tid, "TEST_del", "2030-06-15", "2030-06-16").json()["stop_id"]
        a1 = mk_att(alice, tid, sid, "TEST_A1").json()["attraction_id"]
        a2 = mk_att(alice, tid, sid, "TEST_A2").json()["attraction_id"]
        assert mongo.attractions.count_documents({"stop_id": sid}) == 2

        r = alice.delete(f"{API}/trips/{tid}/stops/{sid}")
        assert r.status_code == 204, r.text
        assert mongo.attractions.count_documents({"stop_id": sid}) == 0
        assert mongo.stops.count_documents({"stop_id": sid}) == 0
        r2 = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions")
        assert r2.status_code == 404

    def test_delete_unknown_404(self, alice, trip):
        r = alice.delete(f"{API}/trips/{trip['trip_id']}/stops/stop_nope")
        assert r.status_code == 404


# ── Stops: reorder ───────────────────────────────────────────
class TestStopsReorder:
    def test_reorder_sets_index(self, alice, trip):
        tid = trip["trip_id"]
        current = alice.get(f"{API}/trips/{tid}/stops").json()
        ids = [s["stop_id"] for s in current]
        # Self-sufficient: this class must not rely on stops created by other classes
        # (pytest.ini uses -n 2 --dist loadscope, so each class may get its own trip).
        while len(ids) < 2:
            ids.append(mk_stop(alice, tid, f"TEST_RO{len(ids)}",
                               f"2030-06-1{len(ids)}", f"2030-06-1{len(ids)}").json()["stop_id"])
        assert len(ids) >= 2
        rev = list(reversed(ids))
        r = alice.post(f"{API}/trips/{tid}/stops/reorder", json={"stop_ids": rev})
        assert r.status_code == 200, r.text
        out = r.json()
        assert [s["stop_id"] for s in out] == rev
        assert [s["order"] for s in out] == list(range(len(rev)))
        again = alice.get(f"{API}/trips/{tid}/stops").json()
        assert [s["stop_id"] for s in again] == rev

    def test_reorder_mismatch_422(self, alice, trip):
        tid = trip["trip_id"]
        ids = [s["stop_id"] for s in alice.get(f"{API}/trips/{tid}/stops").json()]
        r = alice.post(f"{API}/trips/{tid}/stops/reorder", json={"stop_ids": ids + ["stop_bogus"]})
        assert r.status_code == 422, r.text
        # Subset / unknown-only id must now also be rejected (full permutation required).
        r2 = alice.post(f"{API}/trips/{tid}/stops/reorder", json={"stop_ids": ["stop_bogus"]})
        assert r2.status_code == 422


# ── Previously-known defects (now fixed) ─────────────────────
class TestKnownDefects:
    def test_reorder_subset_should_be_rejected(self, alice):
        r = alice.post(f"{API}/trips", json={
            "title": f"TEST_P2_SUBSET_{uuid.uuid4().hex[:6]}", "home_currency": "EUR",
            "start_date": TRIP_START, "end_date": TRIP_END})
        tid = r.json()["trip_id"]
        try:
            ids = [mk_stop(alice, tid, f"TEST_S{i}", "2030-06-0%d" % (i + 1),
                           "2030-06-0%d" % (i + 1)).json()["stop_id"] for i in range(3)]
            rr = alice.post(f"{API}/trips/{tid}/stops/reorder", json={"stop_ids": [ids[2]]})
            if rr.status_code == 200:
                orders = [s["order"] for s in alice.get(f"{API}/trips/{tid}/stops").json()]
                assert len(set(orders)) == len(orders), f"duplicate orders after subset reorder: {orders}"
            assert rr.status_code == 422
        finally:
            alice.delete(f"{API}/trips/{tid}")

    def test_trip_delete_cascades_stops_and_attractions(self, alice, mongo):
        r = alice.post(f"{API}/trips", json={
            "title": f"TEST_P2_CASCADE_{uuid.uuid4().hex[:6]}", "home_currency": "EUR",
            "start_date": TRIP_START, "end_date": TRIP_END})
        tid = r.json()["trip_id"]
        sid = mk_stop(alice, tid, "TEST_Casc", "2030-06-02", "2030-06-03").json()["stop_id"]
        mk_att(alice, tid, sid, "TEST_CascAtt")
        assert alice.delete(f"{API}/trips/{tid}").status_code == 204
        left_stops = mongo.stops.count_documents({"trip_id": tid})
        left_atts = mongo.attractions.count_documents({"trip_id": tid})
        # cleanup regardless of outcome
        mongo.stops.delete_many({"trip_id": tid})
        mongo.attractions.delete_many({"trip_id": tid})
        assert (left_stops, left_atts) == (0, 0), f"orphans left: stops={left_stops} atts={left_atts}"


# ── Attractions ──────────────────────────────────────────────
@pytest.fixture(scope="module")
def stop_a(alice, trip):
    return mk_stop(alice, trip["trip_id"], "TEST_StopA", "2030-06-20", "2030-06-21").json()


@pytest.fixture(scope="module")
def stop_b(alice, trip):
    return mk_stop(alice, trip["trip_id"], "TEST_StopB", "2030-06-22", "2030-06-23").json()


class TestAttractions:
    def test_list_empty(self, alice, trip, stop_a):
        r = alice.get(f"{API}/trips/{trip['trip_id']}/stops/{stop_a['stop_id']}/attractions")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_defaults_currency_and_order(self, alice, trip, stop_a):
        tid, sid = trip["trip_id"], stop_a["stop_id"]
        r = mk_att(alice, tid, sid, "TEST_Louvre", cost=17.5)
        assert r.status_code == 201, r.text
        a = r.json()
        assert a["attraction_id"].startswith("att_")
        assert a["trip_id"] == tid and a["stop_id"] == sid
        assert a["order"] == 0
        assert a["currency"] == trip["home_currency"] == "EUR"
        assert a["cost"] == 17.5

        r2 = mk_att(alice, tid, sid, "TEST_Eiffel", currency="usd", duration_min=90,
                    scheduled_time="09:15", booking_link="https://example.com/x")
        assert r2.status_code == 201, r2.text
        b = r2.json()
        assert b["order"] == 1
        assert b["currency"] == "USD"
        assert b["duration_min"] == 90 and b["scheduled_time"] == "09:15"

        lst = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions").json()
        assert [x["name"] for x in lst] == ["TEST_Louvre", "TEST_Eiffel"]

    def test_create_unknown_stop_404(self, alice, trip):
        r = mk_att(alice, trip["trip_id"], "stop_nope", "X")
        assert r.status_code == 404

    @pytest.mark.parametrize("payload", [
        {"name": "TEST_bad", "cost": -1},
        {"name": "TEST_bad", "duration_min": -3},
        {"name": "TEST_bad", "currency": "XXX"},
        {"name": "TEST_bad", "scheduled_time": "24:61"},
        {"name": ""},
    ])
    def test_validations_422(self, alice, trip, stop_a, payload):
        r = alice.post(
            f"{API}/trips/{trip['trip_id']}/stops/{stop_a['stop_id']}/attractions", json=payload)
        assert r.status_code == 422, r.text

    def test_patch_attraction(self, alice, trip, stop_a):
        tid, sid = trip["trip_id"], stop_a["stop_id"]
        aid = mk_att(alice, tid, sid, "TEST_ToPatch").json()["attraction_id"]
        body = {"name": "TEST_Patched", "cost": 42.0, "currency": "GBP",
                "booking_link": "https://ex.com/b", "scheduled_time": "18:45",
                "duration_min": 30, "notes": "note"}
        r = alice.patch(f"{API}/trips/{tid}/attractions/{aid}", json=body)
        assert r.status_code == 200, r.text
        d = r.json()
        for k, v in body.items():
            assert d[k] == v, k
        lst = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions").json()
        got = [x for x in lst if x["attraction_id"] == aid][0]
        assert got["name"] == "TEST_Patched" and got["cost"] == 42.0 and got["currency"] == "GBP"

    def test_patch_unknown_404(self, alice, trip):
        r = alice.patch(f"{API}/trips/{trip['trip_id']}/attractions/att_nope", json={"name": "x"})
        assert r.status_code == 404

    def test_delete_attraction(self, alice, trip, stop_a):
        tid, sid = trip["trip_id"], stop_a["stop_id"]
        aid = mk_att(alice, tid, sid, "TEST_ToDelete").json()["attraction_id"]
        r = alice.delete(f"{API}/trips/{tid}/attractions/{aid}")
        assert r.status_code == 204
        lst = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions").json()
        assert aid not in [x["attraction_id"] for x in lst]

    def test_delete_unknown_404(self, alice, trip):
        r = alice.delete(f"{API}/trips/{trip['trip_id']}/attractions/att_nope")
        assert r.status_code == 404


# ── Attractions reorder (atomic) ─────────────────────────────
class TestAttractionsReorder:
    """Self-sufficient: seeds its own attractions so it can run in any order/worker."""

    @pytest.fixture(scope="class", autouse=True)
    def seed(self, alice, trip, stop_a, stop_b):
        tid, sid = trip["trip_id"], stop_a["stop_id"]
        existing = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions").json()
        if len(existing) < 2:
            for i in range(2 - len(existing)):
                r = mk_att(alice, tid, sid, f"TEST_Reorder{i}")
                assert r.status_code == 201, r.text
        yield

    def test_same_stop_reorder(self, alice, trip, stop_a):
        tid, sid = trip["trip_id"], stop_a["stop_id"]
        lst = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions").json()
        ids = [x["attraction_id"] for x in lst]
        assert len(ids) >= 2
        rev = list(reversed(ids))
        moves = [{"attraction_id": a, "target_stop_id": sid, "new_order": i} for i, a in enumerate(rev)]
        r = alice.post(f"{API}/trips/{tid}/attractions/reorder", json={"moves": moves})
        assert r.status_code == 200, r.text
        after = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions").json()
        assert [x["attraction_id"] for x in after] == rev

    def test_cross_stop_move(self, alice, trip, stop_a, stop_b):
        tid, sa, sb = trip["trip_id"], stop_a["stop_id"], stop_b["stop_id"]
        lst_a = alice.get(f"{API}/trips/{tid}/stops/{sa}/attractions").json()
        moving = lst_a[0]["attraction_id"]
        rest = [x["attraction_id"] for x in lst_a[1:]]
        moves = [{"attraction_id": moving, "target_stop_id": sb, "new_order": 0}]
        moves += [{"attraction_id": a, "target_stop_id": sa, "new_order": i} for i, a in enumerate(rest)]
        r = alice.post(f"{API}/trips/{tid}/attractions/reorder", json={"moves": moves})
        assert r.status_code == 200, r.text
        in_b = alice.get(f"{API}/trips/{tid}/stops/{sb}/attractions").json()
        assert moving in [x["attraction_id"] for x in in_b]
        in_a = alice.get(f"{API}/trips/{tid}/stops/{sa}/attractions").json()
        assert moving not in [x["attraction_id"] for x in in_a]
        assert [x["attraction_id"] for x in in_a] == rest

    def test_invalid_attraction_id_atomic_rollback(self, alice, trip, stop_a, stop_b, mongo):
        tid, sa, sb = trip["trip_id"], stop_a["stop_id"], stop_b["stop_id"]
        before = {d["attraction_id"]: (d["stop_id"], d["order"])
                  for d in mongo.attractions.find({"trip_id": tid}, {"_id": 0})}
        valid = list(before.keys())[0]
        moves = [
            {"attraction_id": valid, "target_stop_id": sb, "new_order": 9},
            {"attraction_id": "att_bogus", "target_stop_id": sa, "new_order": 0},
        ]
        r = alice.post(f"{API}/trips/{tid}/attractions/reorder", json={"moves": moves})
        assert r.status_code == 422, r.text
        after = {d["attraction_id"]: (d["stop_id"], d["order"])
                 for d in mongo.attractions.find({"trip_id": tid}, {"_id": 0})}
        assert after == before, "DB mutated despite invalid reorder payload"

    def test_invalid_target_stop_atomic_rollback(self, alice, trip, stop_a, mongo):
        tid, sa = trip["trip_id"], stop_a["stop_id"]
        before = {d["attraction_id"]: (d["stop_id"], d["order"])
                  for d in mongo.attractions.find({"trip_id": tid}, {"_id": 0})}
        valid = list(before.keys())[0]
        moves = [
            {"attraction_id": valid, "target_stop_id": "stop_bogus", "new_order": 0},
        ]
        r = alice.post(f"{API}/trips/{tid}/attractions/reorder", json={"moves": moves})
        assert r.status_code == 422, r.text
        after = {d["attraction_id"]: (d["stop_id"], d["order"])
                 for d in mongo.attractions.find({"trip_id": tid}, {"_id": 0})}
        assert after == before

    def test_negative_order_422(self, alice, trip, stop_a):
        tid, sa = trip["trip_id"], stop_a["stop_id"]
        lst = alice.get(f"{API}/trips/{tid}/stops/{sa}/attractions").json()
        r = alice.post(f"{API}/trips/{tid}/attractions/reorder", json={"moves": [
            {"attraction_id": lst[0]["attraction_id"], "target_stop_id": sa, "new_order": -1}]})
        assert r.status_code == 422

    def test_empty_moves_422(self, alice, trip):
        r = alice.post(f"{API}/trips/{trip['trip_id']}/attractions/reorder", json={"moves": []})
        assert r.status_code == 422


# ── Viewer permissions ───────────────────────────────────────
@pytest.fixture(scope="module")
def viewer_trip(alice, bob_id, mongo):
    """Alice's trip where bob is seeded as viewer."""
    r = alice.post(f"{API}/trips", json={
        "title": f"TEST_P2_VIEWER_{uuid.uuid4().hex[:6]}",
        "home_currency": "EUR",
        "start_date": TRIP_START,
        "end_date": TRIP_END,
    })
    assert r.status_code in (200, 201), r.text
    t = r.json()
    mongo.trip_members.insert_one({
        "member_id": f"mem_{uuid.uuid4().hex[:12]}",
        "trip_id": t["trip_id"],
        "user_id": bob_id,
        "invited_email": BOB,
        "role": "viewer",
        "status": "accepted",
        "created_at": "2030-01-01T00:00:00+00:00",
    })
    st = mk_stop(alice, t["trip_id"], "TEST_ViewerStop", "2030-06-02", "2030-06-03").json()
    at = mk_att(alice, t["trip_id"], st["stop_id"], "TEST_ViewerAtt").json()
    yield t, st, at
    mongo.trip_members.delete_many({"trip_id": t["trip_id"]})
    alice.delete(f"{API}/trips/{t['trip_id']}")


class TestViewerPermissions:
    def test_viewer_can_read(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = bob.get(f"{API}/trips/{t['trip_id']}/stops")
        assert r.status_code == 200, r.text
        assert st["stop_id"] in [s["stop_id"] for s in r.json()]
        r2 = bob.get(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/attractions")
        assert r2.status_code == 200
        assert at["attraction_id"] in [a["attraction_id"] for a in r2.json()]

    def test_viewer_cannot_create_stop(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = mk_stop(bob, t["trip_id"], "TEST_nope", "2030-06-05", "2030-06-06")
        assert r.status_code == 403, r.text

    def test_viewer_cannot_patch_stop(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = bob.patch(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}", json={"title": "x"})
        assert r.status_code == 403

    def test_viewer_cannot_delete_stop(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = bob.delete(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}")
        assert r.status_code == 403

    def test_viewer_cannot_reorder_stops(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = bob.post(f"{API}/trips/{t['trip_id']}/stops/reorder",
                     json={"stop_ids": [st["stop_id"]]})
        assert r.status_code == 403

    def test_viewer_cannot_create_attraction(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = mk_att(bob, t["trip_id"], st["stop_id"], "TEST_nope")
        assert r.status_code == 403

    def test_viewer_cannot_patch_or_delete_attraction(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = bob.patch(f"{API}/trips/{t['trip_id']}/attractions/{at['attraction_id']}",
                      json={"name": "x"})
        assert r.status_code == 403
        r2 = bob.delete(f"{API}/trips/{t['trip_id']}/attractions/{at['attraction_id']}")
        assert r2.status_code == 403

    def test_viewer_cannot_reorder_attractions(self, bob, viewer_trip):
        t, st, at = viewer_trip
        r = bob.post(f"{API}/trips/{t['trip_id']}/attractions/reorder", json={"moves": [
            {"attraction_id": at["attraction_id"], "target_stop_id": st["stop_id"], "new_order": 0}]})
        assert r.status_code == 403


# ── Phase 2 fix verification: cascade, full-permutation reorder, URL scheme ──
class TestPhase2Fixes:
    """Retest of the 3 main-agent fixes (iteration_3)."""

    def _new_trip(self, alice, tag):
        r = alice.post(f"{API}/trips", json={
            "title": f"TEST_P2FIX_{tag}_{uuid.uuid4().hex[:6]}", "home_currency": "EUR",
            "start_date": TRIP_START, "end_date": TRIP_END})
        assert r.status_code in (200, 201), r.text
        return r.json()["trip_id"]

    # -- cascade delete --
    def test_delete_trip_cascades_everything(self, alice, mongo):
        tid = self._new_trip(alice, "CASC")
        s1 = mk_stop(alice, tid, "TEST_C1", "2030-06-02", "2030-06-03").json()["stop_id"]
        s2 = mk_stop(alice, tid, "TEST_C2", "2030-06-04", "2030-06-05").json()["stop_id"]
        for sid in (s1, s2):
            for n in range(2):
                assert mk_att(alice, tid, sid, f"TEST_A{n}").status_code == 201
        assert mongo.stops.count_documents({"trip_id": tid}) == 2
        assert mongo.attractions.count_documents({"trip_id": tid}) == 4

        assert alice.delete(f"{API}/trips/{tid}").status_code == 204
        try:
            assert mongo.stops.count_documents({"trip_id": tid}) == 0
            assert mongo.attractions.count_documents({"trip_id": tid}) == 0
            assert mongo.trip_members.count_documents({"trip_id": tid}) == 0
            assert mongo.trips.count_documents({"trip_id": tid}) == 0
            assert alice.get(f"{API}/trips/{tid}").status_code == 404
        finally:
            mongo.stops.delete_many({"trip_id": tid})
            mongo.attractions.delete_many({"trip_id": tid})

    def test_delete_trip_does_not_touch_other_trips(self, alice, mongo):
        keep = self._new_trip(alice, "KEEP")
        doomed = self._new_trip(alice, "DOOM")
        ks = mk_stop(alice, keep, "TEST_Keep", "2030-06-02", "2030-06-03").json()["stop_id"]
        mk_att(alice, keep, ks, "TEST_KeepAtt")
        ds = mk_stop(alice, doomed, "TEST_Doom", "2030-06-02", "2030-06-03").json()["stop_id"]
        mk_att(alice, doomed, ds, "TEST_DoomAtt")
        try:
            assert alice.delete(f"{API}/trips/{doomed}").status_code == 204
            assert mongo.stops.count_documents({"trip_id": keep}) == 1
            assert mongo.attractions.count_documents({"trip_id": keep}) == 1
        finally:
            alice.delete(f"{API}/trips/{keep}")

    # -- reorder full permutation --
    def test_reorder_full_permutation_ok(self, alice):
        tid = self._new_trip(alice, "PERM")
        try:
            ids = [mk_stop(alice, tid, f"TEST_P{i}", f"2030-06-0{i+1}",
                           f"2030-06-0{i+1}").json()["stop_id"] for i in range(3)]
            new_order = [ids[2], ids[0], ids[1]]
            r = alice.post(f"{API}/trips/{tid}/stops/reorder", json={"stop_ids": new_order})
            assert r.status_code == 200, r.text
            got = r.json()
            assert [s["stop_id"] for s in got] == new_order
            assert [s["order"] for s in got] == [0, 1, 2]
            after = alice.get(f"{API}/trips/{tid}/stops").json()
            assert [s["stop_id"] for s in after] == new_order
        finally:
            alice.delete(f"{API}/trips/{tid}")

    def test_reorder_subset_rejected_422_and_no_mutation(self, alice):
        tid = self._new_trip(alice, "SUB")
        try:
            ids = [mk_stop(alice, tid, f"TEST_S{i}", f"2030-06-0{i+1}",
                           f"2030-06-0{i+1}").json()["stop_id"] for i in range(3)]
            before = [(s["stop_id"], s["order"]) for s in alice.get(f"{API}/trips/{tid}/stops").json()]
            r = alice.post(f"{API}/trips/{tid}/stops/reorder", json={"stop_ids": [ids[2], ids[0]]})
            assert r.status_code == 422, r.text
            after = [(s["stop_id"], s["order"]) for s in alice.get(f"{API}/trips/{tid}/stops").json()]
            assert before == after
            orders = [o for _, o in after]
            assert len(set(orders)) == len(orders)
        finally:
            alice.delete(f"{API}/trips/{tid}")

    def test_reorder_duplicates_rejected_422(self, alice):
        tid = self._new_trip(alice, "DUP")
        try:
            ids = [mk_stop(alice, tid, f"TEST_D{i}", f"2030-06-0{i+1}",
                           f"2030-06-0{i+1}").json()["stop_id"] for i in range(2)]
            r = alice.post(f"{API}/trips/{tid}/stops/reorder",
                           json={"stop_ids": [ids[0], ids[0]]})
            assert r.status_code == 422, r.text
            r2 = alice.post(f"{API}/trips/{tid}/stops/reorder",
                            json={"stop_ids": [ids[0], ids[1], ids[1]]})
            assert r2.status_code == 422, r2.text
        finally:
            alice.delete(f"{API}/trips/{tid}")

    def test_reorder_superset_unknown_id_rejected(self, alice):
        tid = self._new_trip(alice, "SUP")
        try:
            ids = [mk_stop(alice, tid, f"TEST_U{i}", f"2030-06-0{i+1}",
                           f"2030-06-0{i+1}").json()["stop_id"] for i in range(2)]
            r = alice.post(f"{API}/trips/{tid}/stops/reorder",
                           json={"stop_ids": ids + ["stop_doesnotexist"]})
            assert r.status_code == 422, r.text
        finally:
            alice.delete(f"{API}/trips/{tid}")

    def test_reorder_empty_list_rejected(self, alice):
        tid = self._new_trip(alice, "EMPTY")
        try:
            mk_stop(alice, tid, "TEST_E0", "2030-06-01", "2030-06-01")
            r = alice.post(f"{API}/trips/{tid}/stops/reorder", json={"stop_ids": []})
            assert r.status_code == 422, r.text
        finally:
            alice.delete(f"{API}/trips/{tid}")

    # -- booking_link scheme validation --
    @pytest.mark.parametrize("bad", [
        "javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,<script>x</script>",
        "ftp://example.com/x", "//evil.com", "example.com",
    ])
    def test_create_attraction_rejects_bad_booking_link(self, alice, bad):
        tid = self._new_trip(alice, "LINK")
        try:
            sid = mk_stop(alice, tid, "TEST_L", "2030-06-02", "2030-06-03").json()["stop_id"]
            r = mk_att(alice, tid, sid, "TEST_BadLink", booking_link=bad)
            assert r.status_code == 422, f"{bad} accepted: {r.status_code} {r.text}"
        finally:
            alice.delete(f"{API}/trips/{tid}")

    @pytest.mark.parametrize("good", [
        "https://booking.com/x", "http://example.org/a?b=1", None, "",
    ])
    def test_create_attraction_accepts_valid_booking_link(self, alice, good):
        tid = self._new_trip(alice, "LINKOK")
        try:
            sid = mk_stop(alice, tid, "TEST_L", "2030-06-02", "2030-06-03").json()["stop_id"]
            r = mk_att(alice, tid, sid, "TEST_GoodLink", booking_link=good)
            assert r.status_code == 201, f"{good!r} rejected: {r.status_code} {r.text}"
            assert r.json()["booking_link"] in (good, None, "")
        finally:
            alice.delete(f"{API}/trips/{tid}")

    def test_patch_attraction_rejects_bad_booking_link_and_keeps_old(self, alice):
        tid = self._new_trip(alice, "PLINK")
        try:
            sid = mk_stop(alice, tid, "TEST_L", "2030-06-02", "2030-06-03").json()["stop_id"]
            aid = mk_att(alice, tid, sid, "TEST_PatchLink",
                         booking_link="https://ok.example.org/1").json()["attraction_id"]
            r = alice.patch(f"{API}/trips/{tid}/attractions/{aid}",
                            json={"booking_link": "javascript:alert(1)"})
            assert r.status_code == 422, r.text
            cur = alice.get(f"{API}/trips/{tid}/stops/{sid}/attractions").json()[0]
            assert cur["booking_link"] == "https://ok.example.org/1"

            r2 = alice.patch(f"{API}/trips/{tid}/attractions/{aid}",
                             json={"booking_link": "http://new.example.org/2"})
            assert r2.status_code == 200, r2.text
            assert r2.json()["booking_link"] == "http://new.example.org/2"

            r3 = alice.patch(f"{API}/trips/{tid}/attractions/{aid}", json={"booking_link": None})
            assert r3.status_code == 200, r3.text
            assert r3.json()["booking_link"] in (None, "")
        finally:
            alice.delete(f"{API}/trips/{tid}")
