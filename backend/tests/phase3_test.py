"""TWT Phase 3 backend tests — hotels, expenses, manual exchange rates, trip summary."""
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
API = f"{base_url.rstrip('/')}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")

ALICE = "alice@twt.app"
BOB = "bob@twt.app"
CAROL = "carol@twt.app"

TRIP_START = "2030-06-01"
TRIP_END = "2030-06-30"


def dev_login(email, name=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name or email.split("@")[0]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def alice():
    return dev_login(ALICE, "Alice")


@pytest.fixture(scope="module")
def bob():
    return dev_login(BOB, "Bob")


@pytest.fixture(scope="module")
def carol():
    return dev_login(CAROL, "Carol")


@pytest.fixture(scope="module")
def alice_id(alice):
    return alice.get(f"{API}/auth/me").json()["user_id"]


@pytest.fixture(scope="module")
def bob_id(bob):
    return bob.get(f"{API}/auth/me").json()["user_id"]


def new_trip(session, tag, currency="EUR"):
    r = session.post(f"{API}/trips", json={
        "title": f"TEST_P3_{tag}_{uuid.uuid4().hex[:6]}",
        "home_currency": currency,
        "start_date": TRIP_START, "end_date": TRIP_END})
    assert r.status_code in (200, 201), r.text
    return r.json()


def mk_stop(session, trip_id, title="TEST_P3_Stop", start=TRIP_START, end=TRIP_START):
    r = session.post(f"{API}/trips/{trip_id}/stops", json={
        "title": title, "location": "Somewhere", "start_date": start,
        "end_date": end, "transport_mode": "car"})
    assert r.status_code == 201, r.text
    return r.json()


def add_member(mongo, trip_id, user_id, email, role):
    mongo.trip_members.insert_one({
        "member_id": f"mem_{uuid.uuid4().hex[:12]}",
        "trip_id": trip_id, "user_id": user_id, "invited_email": email,
        "role": role, "status": "accepted",
        "created_at": "2030-01-01T00:00:00+00:00",
    })


def hotel_body(**kw):
    body = {"name": "TEST_Hotel", "check_in": "2030-06-02", "check_out": "2030-06-04", "cost": 150.0}
    body.update(kw)
    return body


# ── OpenAPI ──────────────────────────────────────────────────
class TestOpenAPIPhase3:
    def test_openapi_lists_phase3_paths(self):
        r = requests.get(f"{API}/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        for p in [
            "/api/trips/{trip_id}/stops/{stop_id}/hotels",
            "/api/trips/{trip_id}/hotels/{hotel_id}",
            "/api/trips/{trip_id}/expenses",
            "/api/trips/{trip_id}/expenses/{expense_id}",
            "/api/trips/{trip_id}/exchange-rates",
            "/api/trips/{trip_id}/exchange-rates/{rate_id}",
            "/api/trips/{trip_id}/summary",
        ]:
            assert p in paths, f"missing {p}"


# ── Hotels ───────────────────────────────────────────────────
class TestHotels:
    @pytest.fixture(scope="class")
    def ctx(self, alice, bob_id, mongo):
        t = new_trip(alice, "HOTEL")
        st = mk_stop(alice, t["trip_id"])
        add_member(mongo, t["trip_id"], bob_id, BOB, "viewer")
        yield t, st
        mongo.trip_members.delete_many({"trip_id": t["trip_id"]})
        alice.delete(f"{API}/trips/{t['trip_id']}")

    def test_list_role_gating(self, alice, bob, carol, ctx):
        t, st = ctx
        url = f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels"
        assert alice.get(url).status_code == 200
        assert bob.get(url).status_code == 200          # viewer
        assert carol.get(url).status_code == 404        # non-member
        assert requests.get(url).status_code == 401     # unauth

    def test_list_unknown_stop_404(self, alice, ctx):
        t, st = ctx
        r = alice.get(f"{API}/trips/{t['trip_id']}/stops/stop_nope/hotels")
        assert r.status_code == 404

    def test_create_defaults_currency_and_fields(self, alice, ctx):
        t, st = ctx
        r = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(name="TEST_HotelA", location="Rome",
                                       booking_link="https://booking.com/x",
                                       cancellation_deadline="2030-05-25", notes="n"))
        assert r.status_code == 201, r.text
        h = r.json()
        assert h["hotel_id"].startswith("hot_")
        assert h["trip_id"] == t["trip_id"] and h["stop_id"] == st["stop_id"]
        assert h["check_in"] == "2030-06-02" and h["check_out"] == "2030-06-04"
        assert h["cost"] == 150.0
        assert h["currency"] == "EUR"          # defaults to home_currency
        assert h["booking_link"] == "https://booking.com/x"
        assert h["cancellation_deadline"] == "2030-05-25"
        assert h["notes"] == "n"
        # persistence
        lst = alice.get(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels").json()
        got = [x for x in lst if x["hotel_id"] == h["hotel_id"]][0]
        assert got["cost"] == 150.0 and got["currency"] == "EUR"
        alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}")

    def test_dates_outside_stop_range_allowed(self, alice, ctx):
        t, st = ctx
        r = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(name="TEST_HotelOut", check_in="2030-06-20",
                                       check_out="2030-06-25"))
        assert r.status_code == 201, r.text
        alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{r.json()['hotel_id']}")

    @pytest.mark.parametrize("payload", [
        {"cost": -1},
        {"check_in": "2030-06-05", "check_out": "2030-06-04"},
        {"booking_link": "javascript:alert(1)"},
        {"currency": "XXX"},
        {"name": ""},
    ])
    def test_validations_422(self, alice, ctx, payload):
        t, st = ctx
        r = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(**payload))
        assert r.status_code == 422, r.text

    def test_currency_case_insensitive(self, alice, ctx):
        t, st = ctx
        r = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(name="TEST_HotelUsd", currency="usd"))
        assert r.status_code == 201, r.text
        assert r.json()["currency"] == "USD"
        alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{r.json()['hotel_id']}")

    def test_patch_partial_and_effective_range(self, alice, ctx):
        t, st = ctx
        h = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(name="TEST_HotelPatch")).json()
        hid = h["hotel_id"]
        r = alice.patch(f"{API}/trips/{t['trip_id']}/hotels/{hid}",
                        json={"cost": 99.5, "notes": "updated"})
        assert r.status_code == 200, r.text
        assert r.json()["cost"] == 99.5 and r.json()["notes"] == "updated"
        assert r.json()["check_in"] == "2030-06-02"

        # check_in after existing check_out -> 422, no mutation
        bad = alice.patch(f"{API}/trips/{t['trip_id']}/hotels/{hid}", json={"check_in": "2030-06-10"})
        assert bad.status_code == 422, bad.text
        cur = [x for x in alice.get(
            f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels").json()
            if x["hotel_id"] == hid][0]
        assert cur["check_in"] == "2030-06-02" and cur["cost"] == 99.5

        ok = alice.patch(f"{API}/trips/{t['trip_id']}/hotels/{hid}", json={"check_in": "2030-06-03"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["check_in"] == "2030-06-03"
        alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{hid}")

    def test_patch_unknown_404(self, alice, ctx):
        t, st = ctx
        r = alice.patch(f"{API}/trips/{t['trip_id']}/hotels/hot_nope", json={"cost": 1})
        assert r.status_code == 404

    def test_patch_bad_link_422(self, alice, ctx):
        t, st = ctx
        h = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(name="TEST_HotelLink")).json()
        r = alice.patch(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}",
                        json={"booking_link": "javascript:alert(1)"})
        assert r.status_code == 422, r.text
        alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}")

    def test_delete_and_404(self, alice, ctx, mongo):
        t, st = ctx
        h = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(name="TEST_HotelDel")).json()
        r = alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}")
        assert r.status_code == 204
        assert mongo.hotels.count_documents({"hotel_id": h["hotel_id"]}) == 0
        assert alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}").status_code == 404

    def test_viewer_cannot_write(self, alice, bob, ctx):
        t, st = ctx
        h = alice.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                       json=hotel_body(name="TEST_HotelViewer")).json()
        assert bob.post(f"{API}/trips/{t['trip_id']}/stops/{st['stop_id']}/hotels",
                        json=hotel_body()).status_code == 403
        assert bob.patch(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}",
                         json={"cost": 1}).status_code == 403
        assert bob.delete(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}").status_code == 403
        alice.delete(f"{API}/trips/{t['trip_id']}/hotels/{h['hotel_id']}")

    def test_multiple_hotels_sorted_by_check_in(self, alice, ctx):
        t, st = ctx
        s2 = mk_stop(alice, t["trip_id"], "TEST_P3_MultiStop")
        url = f"{API}/trips/{t['trip_id']}/stops/{s2['stop_id']}/hotels"
        h2 = alice.post(url, json=hotel_body(name="TEST_Later", check_in="2030-06-10",
                                            check_out="2030-06-12")).json()
        h1 = alice.post(url, json=hotel_body(name="TEST_Earlier", check_in="2030-06-05",
                                            check_out="2030-06-06")).json()
        lst = alice.get(url).json()
        assert len(lst) == 2
        assert [x["name"] for x in lst] == ["TEST_Earlier", "TEST_Later"]
        alice.delete(f"{API}/trips/{t['trip_id']}/stops/{s2['stop_id']}")


# ── Expenses ─────────────────────────────────────────────────
class TestExpenses:
    @pytest.fixture(scope="class")
    def ctx(self, alice, bob_id, mongo):
        t = new_trip(alice, "EXP")
        st = mk_stop(alice, t["trip_id"])
        add_member(mongo, t["trip_id"], bob_id, BOB, "viewer")
        yield t, st
        mongo.trip_members.delete_many({"trip_id": t["trip_id"]})
        alice.delete(f"{API}/trips/{t['trip_id']}")

    def test_list_gating(self, alice, bob, carol, ctx):
        t, st = ctx
        url = f"{API}/trips/{t['trip_id']}/expenses"
        assert alice.get(url).status_code == 200
        assert bob.get(url).status_code == 200
        assert carol.get(url).status_code == 404
        assert requests.get(url).status_code == 401

    def test_create_defaults(self, alice, alice_id, ctx):
        t, st = ctx
        r = alice.post(f"{API}/trips/{t['trip_id']}/expenses",
                       json={"label": "TEST_Gas", "cost": 42.0})
        assert r.status_code == 201, r.text
        e = r.json()
        assert e["expense_id"].startswith("exp_")
        assert e["currency"] == "EUR"
        assert e["stop_id"] is None
        assert e["paid_by"] == alice_id
        assert e["split_between"] == [alice_id]
        # persisted
        lst = alice.get(f"{API}/trips/{t['trip_id']}/expenses").json()
        assert e["expense_id"] in [x["expense_id"] for x in lst]
        alice.delete(f"{API}/trips/{t['trip_id']}/expenses/{e['expense_id']}")

    def test_create_with_stop_and_filter(self, alice, ctx):
        t, st = ctx
        tid, sid = t["trip_id"], st["stop_id"]
        e1 = alice.post(f"{API}/trips/{tid}/expenses",
                        json={"label": "TEST_StopExp", "cost": 10, "stop_id": sid,
                              "currency": "usd"}).json()
        e2 = alice.post(f"{API}/trips/{tid}/expenses",
                        json={"label": "TEST_GenExp", "cost": 20}).json()
        assert e1["currency"] == "USD"
        filtered = alice.get(f"{API}/trips/{tid}/expenses", params={"stop_id": sid}).json()
        ids = [x["expense_id"] for x in filtered]
        assert e1["expense_id"] in ids and e2["expense_id"] not in ids
        unknown = alice.get(f"{API}/trips/{tid}/expenses", params={"stop_id": "stop_nope"}).json()
        assert unknown == []
        alice.delete(f"{API}/trips/{tid}/expenses/{e1['expense_id']}")
        alice.delete(f"{API}/trips/{tid}/expenses/{e2['expense_id']}")

    def test_create_unknown_stop_422(self, alice, ctx):
        t, st = ctx
        r = alice.post(f"{API}/trips/{t['trip_id']}/expenses",
                       json={"label": "TEST_Bad", "cost": 5, "stop_id": "stop_nope"})
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("payload", [
        {"label": "TEST_x", "cost": -1},
        {"label": "", "cost": 1},
        {"label": "TEST_x", "cost": 1, "currency": "XXX"},
    ])
    def test_validations_422(self, alice, ctx, payload):
        t, st = ctx
        r = alice.post(f"{API}/trips/{t['trip_id']}/expenses", json=payload)
        assert r.status_code == 422, r.text

    def test_patch_and_delete(self, alice, ctx):
        t, st = ctx
        tid = t["trip_id"]
        e = alice.post(f"{API}/trips/{tid}/expenses",
                       json={"label": "TEST_Patch", "cost": 5}).json()
        r = alice.patch(f"{API}/trips/{tid}/expenses/{e['expense_id']}",
                        json={"label": "TEST_Patched", "cost": 7.5, "currency": "GBP"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["label"] == "TEST_Patched" and d["cost"] == 7.5 and d["currency"] == "GBP"
        got = [x for x in alice.get(f"{API}/trips/{tid}/expenses").json()
               if x["expense_id"] == e["expense_id"]][0]
        assert got["label"] == "TEST_Patched" and got["currency"] == "GBP"

        assert alice.patch(f"{API}/trips/{tid}/expenses/exp_nope",
                           json={"cost": 1}).status_code == 404
        assert alice.patch(f"{API}/trips/{tid}/expenses/{e['expense_id']}",
                           json={"stop_id": "stop_nope"}).status_code == 422
        assert alice.delete(f"{API}/trips/{tid}/expenses/{e['expense_id']}").status_code == 204
        assert alice.delete(f"{API}/trips/{tid}/expenses/{e['expense_id']}").status_code == 404

    def test_viewer_cannot_write(self, alice, bob, ctx):
        t, st = ctx
        tid = t["trip_id"]
        e = alice.post(f"{API}/trips/{tid}/expenses",
                       json={"label": "TEST_ViewerExp", "cost": 5}).json()
        assert bob.post(f"{API}/trips/{tid}/expenses",
                        json={"label": "x", "cost": 1}).status_code == 403
        assert bob.patch(f"{API}/trips/{tid}/expenses/{e['expense_id']}",
                         json={"cost": 1}).status_code == 403
        assert bob.delete(f"{API}/trips/{tid}/expenses/{e['expense_id']}").status_code == 403
        alice.delete(f"{API}/trips/{tid}/expenses/{e['expense_id']}")


# ── Exchange rates ───────────────────────────────────────────
class TestExchangeRates:
    @pytest.fixture(scope="class")
    def ctx(self, alice, bob_id, carol, mongo):
        t = new_trip(alice, "RATES")
        add_member(mongo, t["trip_id"], bob_id, BOB, "viewer")
        carol_id = carol.get(f"{API}/auth/me").json()["user_id"]
        add_member(mongo, t["trip_id"], carol_id, CAROL, "editor")
        yield t
        mongo.trip_members.delete_many({"trip_id": t["trip_id"]})
        mongo.exchange_rates.delete_many({"trip_id": t["trip_id"]})
        alice.delete(f"{API}/trips/{t['trip_id']}")

    def test_get_gating(self, alice, bob, ctx):
        url = f"{API}/trips/{ctx['trip_id']}/exchange-rates"
        assert alice.get(url).status_code == 200
        assert bob.get(url).status_code == 200
        assert requests.get(url).status_code == 401

    def test_put_owner_only(self, bob, carol, ctx):
        url = f"{API}/trips/{ctx['trip_id']}/exchange-rates"
        body = {"from_currency": "USD", "to_currency": "EUR", "rate": 0.9}
        assert carol.put(url, json=body).status_code == 403   # editor
        assert bob.put(url, json=body).status_code == 403      # viewer

    def test_put_upsert_same_row(self, alice, ctx, mongo):
        tid = ctx["trip_id"]
        url = f"{API}/trips/{tid}/exchange-rates"
        r1 = alice.put(url, json={"from_currency": "USD", "to_currency": "EUR", "rate": 0.92})
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["rate_id"].startswith("rate_")
        assert d1["from_currency"] == "USD" and d1["to_currency"] == "EUR" and d1["rate"] == 0.92

        r2 = alice.put(url, json={"from_currency": "usd", "to_currency": "eur", "rate": 0.93})
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["rate_id"] == d1["rate_id"], "upsert created a new row instead of updating"
        assert d2["rate"] == 0.93
        assert d2["updated_at"] >= d1["updated_at"]
        assert mongo.exchange_rates.count_documents(
            {"trip_id": tid, "from_currency": "USD", "to_currency": "EUR"}) == 1
        lst = alice.get(url).json()
        assert len([x for x in lst if x["from_currency"] == "USD"]) == 1

    @pytest.mark.parametrize("body", [
        {"from_currency": "EUR", "to_currency": "EUR", "rate": 1.0},
        {"from_currency": "USD", "to_currency": "EUR", "rate": 0},
        {"from_currency": "USD", "to_currency": "EUR", "rate": -1},
        {"from_currency": "XXX", "to_currency": "EUR", "rate": 1.1},
        {"from_currency": "USD", "to_currency": "ZZZ", "rate": 1.1},
    ])
    def test_put_validations_422(self, alice, ctx, body):
        r = alice.put(f"{API}/trips/{ctx['trip_id']}/exchange-rates", json=body)
        assert r.status_code == 422, r.text

    def test_delete_owner_only(self, alice, bob, carol, ctx):
        tid = ctx["trip_id"]
        url = f"{API}/trips/{tid}/exchange-rates"
        rid = alice.put(url, json={"from_currency": "GBP", "to_currency": "EUR",
                                   "rate": 1.15}).json()["rate_id"]
        assert bob.delete(f"{url}/{rid}").status_code == 403
        assert carol.delete(f"{url}/{rid}").status_code == 403
        assert alice.delete(f"{url}/{rid}").status_code == 204
        assert alice.delete(f"{url}/{rid}").status_code == 404


# ── Summary ──────────────────────────────────────────────────
class TestSummary:
    @pytest.fixture(scope="class")
    def ctx(self, alice, bob_id, mongo):
        """home=EUR; hotel EUR 150, hotel USD 200, attraction USD 30, expense EUR 50."""
        t = new_trip(alice, "SUM", "EUR")
        tid = t["trip_id"]
        st = mk_stop(alice, tid)
        sid = st["stop_id"]
        add_member(mongo, tid, bob_id, BOB, "viewer")
        h_eur = alice.post(f"{API}/trips/{tid}/stops/{sid}/hotels",
                           json=hotel_body(name="TEST_EurHotel", cost=150.0)).json()
        h_usd = alice.post(f"{API}/trips/{tid}/stops/{sid}/hotels",
                           json=hotel_body(name="TEST_UsdHotel", cost=200.0,
                                           currency="USD")).json()
        att = alice.post(f"{API}/trips/{tid}/stops/{sid}/attractions",
                         json={"name": "TEST_UsdAtt", "cost": 30.0, "currency": "USD"}).json()
        exp = alice.post(f"{API}/trips/{tid}/expenses",
                         json={"label": "TEST_EurExp", "cost": 50.0}).json()
        yield {"trip": t, "stop": st, "h_eur": h_eur, "h_usd": h_usd, "att": att, "exp": exp}
        mongo.trip_members.delete_many({"trip_id": tid})
        mongo.exchange_rates.delete_many({"trip_id": tid})
        alice.delete(f"{API}/trips/{tid}")

    def test_gating(self, alice, bob, carol, ctx):
        url = f"{API}/trips/{ctx['trip']['trip_id']}/summary"
        assert alice.get(url).status_code == 200
        assert bob.get(url).status_code == 200
        assert carol.get(url).status_code == 404
        assert requests.get(url).status_code == 401

    def test_a_missing_rate_excludes_and_reports(self, alice, ctx):
        tid = ctx["trip"]["trip_id"]
        r = alice.get(f"{API}/trips/{tid}/summary")
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["total_km"] is None
        assert s["home_currency"] == "EUR"
        assert set(s["breakdown"].keys()) == {"hotels", "attractions", "expenses"}
        assert s["breakdown"]["hotels"] == 150.0
        assert s["breakdown"]["attractions"] == 0.0
        assert s["breakdown"]["expenses"] == 50.0
        assert s["total_cost_home_currency"] == 200.0
        assert len(s["missing_rates"]) == 1, s["missing_rates"]
        m = s["missing_rates"][0]
        assert m["from"] == "USD" and m["to"] == "EUR"
        assert set(m["affected_items"]) == {ctx["h_usd"]["hotel_id"], ctx["att"]["attraction_id"]}

    def test_b_with_rate_total_and_recompute(self, alice, ctx):
        tid = ctx["trip"]["trip_id"]
        url = f"{API}/trips/{tid}/exchange-rates"
        assert alice.put(url, json={"from_currency": "USD", "to_currency": "EUR",
                                    "rate": 0.92}).status_code == 200
        s = alice.get(f"{API}/trips/{tid}/summary").json()
        assert s["missing_rates"] == []
        assert s["breakdown"]["hotels"] == pytest.approx(150 + 200 * 0.92, abs=0.01)
        assert s["breakdown"]["attractions"] == pytest.approx(30 * 0.92, abs=0.01)
        assert s["breakdown"]["expenses"] == 50.0
        assert s["total_cost_home_currency"] == pytest.approx(411.60, abs=0.01)

        assert alice.put(url, json={"from_currency": "USD", "to_currency": "EUR",
                                    "rate": 0.93}).status_code == 200
        s2 = alice.get(f"{API}/trips/{tid}/summary").json()
        expected = 150 + 200 * 0.93 + 30 * 0.93 + 50
        assert s2["total_cost_home_currency"] == pytest.approx(round(expected, 2), abs=0.01)

    def test_c_rate_is_unidirectional(self, alice, mongo):
        """home=USD, EUR item, only USD->EUR set => EUR->USD must be MISSING."""
        t = new_trip(alice, "UNI", "USD")
        tid = t["trip_id"]
        try:
            st = mk_stop(alice, tid)
            e = alice.post(f"{API}/trips/{tid}/expenses",
                           json={"label": "TEST_EurItem", "cost": 100.0,
                                 "currency": "EUR"}).json()
            assert alice.put(f"{API}/trips/{tid}/exchange-rates",
                             json={"from_currency": "USD", "to_currency": "EUR",
                                   "rate": 0.92}).status_code == 200
            s = alice.get(f"{API}/trips/{tid}/summary").json()
            assert s["home_currency"] == "USD"
            assert s["total_cost_home_currency"] == 0.0, s
            assert len(s["missing_rates"]) == 1, s["missing_rates"]
            m = s["missing_rates"][0]
            assert (m["from"], m["to"]) == ("EUR", "USD"), "rate was auto-inverted!"
            assert m["affected_items"] == [e["expense_id"]]
        finally:
            mongo.exchange_rates.delete_many({"trip_id": tid})
            alice.delete(f"{API}/trips/{tid}")

    def test_d_empty_trip_summary(self, alice):
        t = new_trip(alice, "EMPTY")
        try:
            s = alice.get(f"{API}/trips/{t['trip_id']}/summary").json()
            assert s["total_cost_home_currency"] == 0.0
            assert s["missing_rates"] == []
            assert s["breakdown"] == {"hotels": 0.0, "attractions": 0.0, "expenses": 0.0}
        finally:
            alice.delete(f"{API}/trips/{t['trip_id']}")


# ── Trip cascade delete (Phase 3 collections) ────────────────
class TestTripCascadePhase3:
    def test_delete_trip_cascades_all_six_collections(self, alice, mongo):
        t = new_trip(alice, "CASC3")
        tid = t["trip_id"]
        st = mk_stop(alice, tid)
        sid = st["stop_id"]
        alice.post(f"{API}/trips/{tid}/stops/{sid}/attractions",
                   json={"name": "TEST_CascAtt", "cost": 5})
        assert alice.post(f"{API}/trips/{tid}/stops/{sid}/hotels",
                          json=hotel_body(name="TEST_CascHotel")).status_code == 201
        assert alice.post(f"{API}/trips/{tid}/expenses",
                          json={"label": "TEST_CascExp", "cost": 9}).status_code == 201
        assert alice.put(f"{API}/trips/{tid}/exchange-rates",
                         json={"from_currency": "USD", "to_currency": "EUR",
                               "rate": 0.9}).status_code == 200

        assert alice.delete(f"{API}/trips/{tid}").status_code == 204
        counts = {c: mongo[c].count_documents({"trip_id": tid}) for c in
                  ("stops", "attractions", "trip_members", "hotels", "expenses", "exchange_rates")}
        try:
            assert counts == {c: 0 for c in counts}, f"orphans left after trip delete: {counts}"
        finally:
            for c in counts:
                mongo[c].delete_many({"trip_id": tid})
