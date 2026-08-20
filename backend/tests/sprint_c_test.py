"""Sprint C — day-centric timeline + attraction scheduling tests."""
import os
import time
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

OWNER_EMAIL = "sprintc_be@twt.app"


def _login(email, name="Sprint C"):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name}, timeout=60)
    assert r.status_code == 200, f"dev-login failed {r.status_code} {r.text[:300]}"
    tok = r.json().get("session_token")
    assert tok
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def owner():
    return _login(OWNER_EMAIL)


@pytest.fixture(scope="module")
def trash():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(owner, trash):
    yield
    for tid in trash:
        try:
            owner.delete(f"{API}/trips/{tid}", timeout=60)
        except Exception:
            pass


def mk_trip(owner, trash, start, end, **extra):
    payload = {
        "title": "TEST_SprintC Trip",
        "home_currency": "EUR",
        "start_date": start,
        "end_date": end,
    }
    payload.update(extra)
    r = owner.post(f"{API}/trips", json=payload, timeout=60)
    assert r.status_code == 201, f"{r.status_code} {r.text[:300]}"
    tid = r.json()["trip_id"]
    trash.append(tid)
    return tid


def mk_stop(owner, tid, title, location, start, end, **extra):
    payload = {
        "title": title,
        "location": location,
        "start_date": start,
        "end_date": end,
    }
    payload.update(extra)
    r = owner.post(f"{API}/trips/{tid}/stops", json=payload, timeout=90)
    assert r.status_code == 201, f"{r.status_code} {r.text[:300]}"
    return r.json()["stop_id"]


def mk_att(owner, tid, sid, name, **extra):
    payload = {"name": name}
    payload.update(extra)
    r = owner.post(f"{API}/trips/{tid}/stops/{sid}/attractions", json=payload, timeout=60)
    return r


# ── Base dates (fixed, deterministic) ─────────────────────────
D1 = "2026-08-01"
D2 = "2026-08-02"
D3 = "2026-08-03"
D4 = "2026-08-04"
D5 = "2026-08-05"


# ══════════════════════════════════════════════════════════════
# GET /api/trips/{id}/timeline
# ══════════════════════════════════════════════════════════════
class TestTimelineBasic:
    @pytest.fixture(scope="class")
    def fx(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        roma = mk_stop(owner, tid, "Roma", "Roma, IT", D1, D3, transport_mode="train")
        milano = mk_stop(owner, tid, "Milano", "Milano, IT", D4, D5, transport_mode="plane")
        return {"tid": tid, "roma": roma, "milano": milano}

    def test_days_and_positions(self, owner, fx):
        r = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        days = data["days"]
        assert len(days) == 5
        assert [d["date"] for d in days] == [D1, D2, D3, D4, D5]
        assert [d["day_index"] for d in days] == [0, 1, 2, 3, 4]
        assert [d["stop_position"] for d in days] == ["first", "middle", "last", "first", "last"]
        assert [d["stop_id"] for d in days[:3]] == [fx["roma"]] * 3
        assert [d["stop_id"] for d in days[3:]] == [fx["milano"]] * 2
        assert days[0]["weekday"] == "Sat"  # 2026-08-01
        assert all(d["is_transit_day"] is False for d in days)
        assert days[0]["stop_title"] == "Roma"
        assert days[3]["stop_transport_mode"] == "plane"

    def test_route_in_on_arrival_day(self, owner, fx):
        data = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()
        days = data["days"]
        assert days[0]["route_in"] is None, "first stop of trip must not have route_in"
        ri = days[3]["route_in"]
        assert ri is not None, "day4 (Milano arrival) should have route_in"
        assert ri["from_stop_id"] == fx["roma"]
        assert ri["from_title"] == "Roma"
        assert ri["transport_mode"] == "plane"
        assert ri["distance_m"] is None or ri["distance_m"] > 0
        # non-arrival days have no route_in
        assert days[1]["route_in"] is None
        assert days[4]["route_in"] is None

    def test_no_return_leg_when_flag_off(self, owner, fx):
        data = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()
        assert data["return_leg"] is None
        assert all(d["is_return_home_day"] is False for d in data["days"])

    def test_timeline_perf_and_openapi(self, owner, fx):
        t0 = time.time()
        r = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60)
        assert r.status_code == 200
        assert (time.time() - t0) < 3.0
        oa = requests.get(f"{API}/openapi.json", timeout=60)
        assert oa.status_code == 200
        paths = oa.json()["paths"]
        assert any(p.endswith("/timeline") for p in paths), "timeline path missing in openapi"
        assert any(p.endswith("/schedule") for p in paths), "schedule path missing in openapi"


class TestTimelineTransitDay:
    def test_transit_day(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        mk_stop(owner, tid, "Roma", "Roma, IT", D1, D2)
        mk_stop(owner, tid, "Milano", "Milano, IT", D4, D5)
        days = owner.get(f"{API}/trips/{tid}/timeline", timeout=60).json()["days"]
        d3 = days[2]
        assert d3["date"] == D3
        assert d3["stop_id"] is None
        assert d3["stop_position"] == "none"
        assert d3["is_transit_day"] is True
        assert d3["stop_title"] is None


class TestTimelineSingleDayStop:
    def test_only_position(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D1)
        mk_stop(owner, tid, "Roma", "Roma, IT", D1, D1)
        days = owner.get(f"{API}/trips/{tid}/timeline", timeout=60).json()["days"]
        assert len(days) == 1
        assert days[0]["stop_position"] == "only"


class TestTimelineReturnHome:
    def test_return_home_day(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D3, home_location="Torino, IT", has_return=True)
        mk_stop(owner, tid, "Roma", "Roma, IT", D1, D3)
        data = owner.get(f"{API}/trips/{tid}/timeline", timeout=60).json()
        days = data["days"]
        assert days[-1]["is_return_home_day"] is True
        assert all(d["is_return_home_day"] is False for d in days[:-1])
        assert data["return_leg"] == {"home_location": "Torino, IT"}

    def test_route_geometry_return_leg_regression(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D3, home_location="Torino, IT", has_return=True)
        mk_stop(owner, tid, "Roma", "Roma, IT", D1, D2)
        mk_stop(owner, tid, "Milano", "Milano, IT", D3, D3)
        r = owner.get(f"{API}/trips/{tid}/route-geometry", timeout=120)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "return_leg" in body
        assert body["return_leg"] is not None


# ══════════════════════════════════════════════════════════════
# scheduled_date validation on create / update
# ══════════════════════════════════════════════════════════════
class TestAttractionScheduledDateValidation:
    @pytest.fixture(scope="class")
    def fx(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        roma = mk_stop(owner, tid, "Roma", "Roma, IT", D1, D3)
        milano = mk_stop(owner, tid, "Milano", "Milano, IT", D4, D5)
        return {"tid": tid, "roma": roma, "milano": milano}

    def test_create_in_range(self, owner, fx):
        r = mk_att(owner, fx["tid"], fx["roma"], "TEST_Colosseo", scheduled_date=D2)
        assert r.status_code == 201, r.text[:300]
        assert r.json()["scheduled_date"] == D2
        aid = r.json()["attraction_id"]
        g = owner.get(f"{API}/trips/{fx['tid']}/stops/{fx['roma']}/attractions", timeout=60)
        assert g.status_code == 200
        found = [a for a in g.json() if a["attraction_id"] == aid]
        assert found and found[0]["scheduled_date"] == D2

    def test_create_out_of_range_422(self, owner, fx):
        r = mk_att(owner, fx["tid"], fx["roma"], "TEST_Bad", scheduled_date=D5)
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text[:300]}"
        detail = str(r.json().get("detail"))
        assert "scheduled_date must be within stop range" in detail, detail
        assert D1 in detail and D3 in detail, detail

    def test_create_null_default(self, owner, fx):
        r = mk_att(owner, fx["tid"], fx["roma"], "TEST_NoDate")
        assert r.status_code == 201
        assert r.json()["scheduled_date"] is None

    def test_patch_in_range_and_out_of_range(self, owner, fx):
        aid = mk_att(owner, fx["tid"], fx["roma"], "TEST_Patchable").json()["attraction_id"]
        ok = owner.patch(f"{API}/trips/{fx['tid']}/attractions/{aid}", json={"scheduled_date": D3}, timeout=60)
        assert ok.status_code == 200, ok.text[:300]
        assert ok.json()["scheduled_date"] == D3
        bad = owner.patch(f"{API}/trips/{fx['tid']}/attractions/{aid}", json={"scheduled_date": D4}, timeout=60)
        assert bad.status_code == 422, bad.text[:300]
        # unchanged after failed patch
        again = owner.get(f"{API}/trips/{fx['tid']}/stops/{fx['roma']}/attractions", timeout=60).json()
        cur = [a for a in again if a["attraction_id"] == aid][0]
        assert cur["scheduled_date"] == D3


# ══════════════════════════════════════════════════════════════
# PATCH /attractions/{id}/schedule
# ══════════════════════════════════════════════════════════════
class TestScheduleEndpoint:
    @pytest.fixture(scope="class")
    def fx(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        roma = mk_stop(owner, tid, "Roma", "Roma, IT", D1, D3)
        milano = mk_stop(owner, tid, "Milano", "Milano, IT", D4, D5)
        return {"tid": tid, "roma": roma, "milano": milano}

    def _sched(self, owner, fx, aid, body):
        return owner.patch(
            f"{API}/trips/{fx['tid']}/attractions/{aid}/schedule", json=body, timeout=60
        )

    def test_date_derives_target_stop(self, owner, fx):
        aid = mk_att(owner, fx["tid"], fx["roma"], "TEST_Move1").json()["attraction_id"]
        r = self._sched(owner, fx, aid, {"scheduled_date": D4})
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["stop_id"] == fx["milano"], "stop_id should auto-derive to Milano"
        assert body["scheduled_date"] == D4
        # persisted + shows on the right day of the timeline
        tl = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()
        day4 = [d for d in tl["days"] if d["date"] == D4][0]
        assert aid in [a["attraction_id"] for a in day4["attractions"]]
        assert aid not in [a["attraction_id"] for a in tl["unscheduled_attractions"]]

    def test_date_with_no_stop_422(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        roma = mk_stop(owner, tid, "Roma", "Roma, IT", D1, D2)
        aid = mk_att(owner, tid, roma, "TEST_NoStopDay").json()["attraction_id"]
        r = owner.patch(
            f"{API}/trips/{tid}/attractions/{aid}/schedule", json={"scheduled_date": D4}, timeout=60
        )
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
        assert "No stop covers" in str(r.json().get("detail"))

    def test_null_clears_date_keeps_stop(self, owner, fx):
        aid = mk_att(owner, fx["tid"], fx["roma"], "TEST_Clear", scheduled_date=D2).json()["attraction_id"]
        r = self._sched(owner, fx, aid, {"scheduled_date": None})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["scheduled_date"] is None
        assert r.json()["stop_id"] == fx["roma"]
        tl = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()
        un = [a for a in tl["unscheduled_attractions"] if a["attraction_id"] == aid]
        assert un, "cleared attraction must appear in unscheduled_attractions"
        assert un[0]["stop_title"] == "Roma"

    def test_target_stop_with_out_of_range_date_422(self, owner, fx):
        aid = mk_att(owner, fx["tid"], fx["roma"], "TEST_BadTarget").json()["attraction_id"]
        r = self._sched(owner, fx, aid, {"target_stop_id": fx["milano"], "scheduled_date": D2})
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
        assert "scheduled_date must be within stop range" in str(r.json().get("detail"))

    def test_target_stop_valid(self, owner, fx):
        aid = mk_att(owner, fx["tid"], fx["roma"], "TEST_GoodTarget").json()["attraction_id"]
        r = self._sched(owner, fx, aid, {"target_stop_id": fx["milano"], "scheduled_date": D5})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["stop_id"] == fx["milano"]
        assert r.json()["scheduled_date"] == D5

    def test_new_order_reorders(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        roma = mk_stop(owner, tid, "Roma", "Roma, IT", D1, D3)
        ids = [mk_att(owner, tid, roma, f"TEST_O{i}").json()["attraction_id"] for i in range(3)]
        # move last to position 0 within same stop, with a date
        r = owner.patch(
            f"{API}/trips/{tid}/attractions/{ids[2]}/schedule",
            json={"scheduled_date": D2, "new_order": 0},
            timeout=60,
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["order"] == 0
        listing = owner.get(f"{API}/trips/{tid}/stops/{roma}/attractions", timeout=60).json()
        order_ids = [a["attraction_id"] for a in listing]
        assert order_ids[0] == ids[2], order_ids
        assert [a["order"] for a in listing] == [0, 1, 2]

    def test_schedule_unknown_attraction_404(self, owner, fx):
        r = self._sched(owner, fx, "att_doesnotexist", {"scheduled_date": D2})
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════
# /attractions/reorder — backward compat + scheduled_date
# ══════════════════════════════════════════════════════════════
class TestReorderWithScheduledDate:
    @pytest.fixture(scope="class")
    def fx(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        roma = mk_stop(owner, tid, "Roma", "Roma, IT", D1, D3)
        milano = mk_stop(owner, tid, "Milano", "Milano, IT", D4, D5)
        ids = [mk_att(owner, tid, roma, f"TEST_R{i}").json()["attraction_id"] for i in range(3)]
        return {"tid": tid, "roma": roma, "milano": milano, "ids": ids}

    def test_reorder_without_scheduled_date_backward_compat(self, owner, fx):
        ids = fx["ids"]
        r = owner.post(
            f"{API}/trips/{fx['tid']}/attractions/reorder",
            json={"moves": [{"attraction_id": ids[2], "target_stop_id": fx["roma"], "new_order": 0}]},
            timeout=60,
        )
        assert r.status_code == 200, r.text[:300]
        listing = owner.get(f"{API}/trips/{fx['tid']}/stops/{fx['roma']}/attractions", timeout=60).json()
        assert [a["attraction_id"] for a in listing][0] == ids[2]
        # date untouched
        assert all(a["scheduled_date"] is None for a in listing)

    def test_reorder_with_valid_scheduled_date(self, owner, fx):
        ids = fx["ids"]
        r = owner.post(
            f"{API}/trips/{fx['tid']}/attractions/reorder",
            json={"moves": [{
                "attraction_id": ids[0], "target_stop_id": fx["milano"],
                "new_order": 0, "scheduled_date": D4,
            }]},
            timeout=60,
        )
        assert r.status_code == 200, r.text[:300]
        moved = [a for a in r.json() if a["attraction_id"] == ids[0]][0]
        assert moved["stop_id"] == fx["milano"]
        assert moved["scheduled_date"] == D4

    def test_reorder_with_out_of_range_date_422_atomic(self, owner, fx):
        ids = fx["ids"]
        before = owner.get(f"{API}/trips/{fx['tid']}/stops/{fx['roma']}/attractions", timeout=60).json()
        before_map = {a["attraction_id"]: (a["order"], a["stop_id"]) for a in before}
        r = owner.post(
            f"{API}/trips/{fx['tid']}/attractions/reorder",
            json={"moves": [{
                "attraction_id": ids[1], "target_stop_id": fx["milano"],
                "new_order": 0, "scheduled_date": D2,
            }]},
            timeout=60,
        )
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
        after = owner.get(f"{API}/trips/{fx['tid']}/stops/{fx['roma']}/attractions", timeout=60).json()
        after_map = {a["attraction_id"]: (a["order"], a["stop_id"]) for a in after}
        assert after_map == before_map, "failed reorder must not mutate anything (atomic)"


# ══════════════════════════════════════════════════════════════
# Timeline aggregation: hotels / expenses / unscheduled
# ══════════════════════════════════════════════════════════════
class TestTimelineAggregation:
    @pytest.fixture(scope="class")
    def fx(self, owner, trash):
        tid = mk_trip(owner, trash, D1, D5)
        roma = mk_stop(owner, tid, "Roma", "Roma, IT", D1, D3)
        milano = mk_stop(owner, tid, "Milano", "Milano, IT", D4, D5)
        sched = mk_att(owner, tid, roma, "TEST_Sched", scheduled_date=D2).json()["attraction_id"]
        unsched = mk_att(owner, tid, milano, "TEST_Unsched").json()["attraction_id"]
        h = owner.post(f"{API}/trips/{tid}/stops/{roma}/hotels", json={
            "name": "TEST_Hotel Roma", "cost": 120,
            "check_in": D1, "check_out": D3,
        }, timeout=60)
        assert h.status_code == 201, h.text[:300]
        e = owner.post(f"{API}/trips/{tid}/expenses", json={
            "label": "TEST_Dinner", "cost": 20, "currency": "EUR",
            "stop_id": roma, "expense_date": D2,
        }, timeout=60)
        return {"tid": tid, "roma": roma, "milano": milano, "sched": sched,
                "unsched": unsched, "exp_status": e.status_code, "exp_body": e.text[:300]}

    def test_unscheduled_and_scheduled_split(self, owner, fx):
        tl = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()
        un_ids = [a["attraction_id"] for a in tl["unscheduled_attractions"]]
        assert fx["unsched"] in un_ids
        assert fx["sched"] not in un_ids
        un = [a for a in tl["unscheduled_attractions"] if a["attraction_id"] == fx["unsched"]][0]
        assert un["stop_title"] == "Milano"
        day2 = [d for d in tl["days"] if d["date"] == D2][0]
        assert fx["sched"] in [a["attraction_id"] for a in day2["attractions"]]

    def test_hotels_active_nights(self, owner, fx):
        tl = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()
        by_date = {d["date"]: d for d in tl["days"]}
        assert len(by_date[D1]["hotels_active"]) == 1
        assert len(by_date[D2]["hotels_active"]) == 1
        assert by_date[D3]["hotels_active"] == [], "checkout day should not be an active night"
        assert by_date[D4]["hotels_active"] == []

    def test_expenses_by_day(self, owner, fx):
        assert fx["exp_status"] == 201, f"expense create failed: {fx['exp_status']} {fx['exp_body']}"
        tl = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()
        by_date = {d["date"]: d for d in tl["days"]}
        descs = [e["label"] for e in by_date[D2]["expenses"]]
        assert "TEST_Dinner" in descs
        assert by_date[D1]["expenses"] == []

    def test_no_mongo_id_leak(self, owner, fx):
        tl = owner.get(f"{API}/trips/{fx['tid']}/timeline", timeout=60).json()

        def walk(o):
            if isinstance(o, dict):
                assert "_id" not in o, f"mongo _id leaked: {list(o)[:8]}"
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(tl)


# ══════════════════════════════════════════════════════════════
# Perf: 30-day trip, ~100 attractions
# ══════════════════════════════════════════════════════════════
class TestTimelinePerf:
    def test_30_days_100_attractions_under_1s(self, owner, trash):
        start = date(2026, 9, 1)
        end = start + timedelta(days=29)
        tid = mk_trip(owner, trash, start.isoformat(), end.isoformat())
        sids = []
        for i in range(3):
            s = start + timedelta(days=i * 10)
            e = s + timedelta(days=9)
            sids.append(mk_stop(owner, tid, f"S{i}", ["Roma, IT", "Milano, IT", "Firenze, IT"][i],
                                s.isoformat(), e.isoformat()))
        for i in range(100):
            sid = sids[i % 3]
            d = start + timedelta(days=(i % 3) * 10 + (i % 10))
            r = mk_att(owner, tid, sid, f"TEST_P{i}", scheduled_date=d.isoformat())
            assert r.status_code == 201, r.text[:200]
        t0 = time.time()
        r = owner.get(f"{API}/trips/{tid}/timeline", timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200
        data = r.json()
        assert len(data["days"]) == 30
        assert sum(len(d["attractions"]) for d in data["days"]) == 100
        print(f"timeline 30d/100att elapsed={elapsed:.3f}s")
        assert elapsed < 1.5, f"timeline too slow: {elapsed:.3f}s"
