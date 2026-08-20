"""Iteration 21 — explicit live-cascade sanity across ALL 6 child collections.

Complements orphan_cascade_iter20_test.py by asserting a NON-ZERO pre-delete
row count in every child collection (iter20 only asserted >0 for
stops/hotels/expenses/trip_members), including an explicitly-created
exchange_rates row and an attraction, and then asserting 0 rows post-delete.

Also re-verifies the global orphan invariant AFTER this test's own
create/delete churn so we prove the cascade does not create new orphans.
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL") or backend_env["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME") or backend_env["DB_NAME"]

CHILD_COLLECTIONS = [
    "attractions",
    "stops",
    "hotels",
    "expenses",
    "exchange_rates",
    "trip_members",
]


@pytest.fixture(scope="module")
def mongo_db():
    from pymongo import MongoClient

    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(
        f"{API}/auth/dev-login",
        json={"email": "orphan_regress_v2@twt.app", "name": "OrphanRegressV2"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert s.cookies.get("twt_session"), f"twt_session cookie not set: {s.cookies.get_dict()}"
    return s


class TestLiveCascadeAllCollections:
    def test_full_seed_then_delete_leaves_nothing(self, session, mongo_db):
        s = session

        r = s.post(
            f"{API}/trips",
            json={
                "title": "TEST_Iter21Cascade",
                "home_currency": "EUR",
                "start_date": "2026-09-01",
                "end_date": "2026-09-10",
            },
            timeout=15,
        )
        assert r.status_code == 201, r.text
        trip_id = r.json()["trip_id"]

        # 1 stop
        r = s.post(
            f"{API}/trips/{trip_id}/stops",
            json={
                "title": "TEST_Iter21Stop",
                "location": "Firenze",
                "start_date": "2026-09-01",
                "end_date": "2026-09-03",
                "transport_mode": "car",
            },
            timeout=25,
        )
        assert r.status_code == 201, r.text
        stop_id = r.json()["stop_id"]

        # 1 hotel
        r = s.post(
            f"{API}/trips/{trip_id}/stops/{stop_id}/hotels",
            json={
                "name": "TEST_Iter21Hotel",
                "check_in": "2026-09-01",
                "check_out": "2026-09-03",
                "cost": 220,
                "currency": "USD",
            },
            timeout=25,
        )
        assert r.status_code == 201, r.text

        # 1 attraction
        r = s.post(
            f"{API}/trips/{trip_id}/stops/{stop_id}/attractions",
            json={"name": "TEST_Iter21Attr", "cost": 12, "currency": "EUR"},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text

        # 1 expense with stop_id = null
        r = s.post(
            f"{API}/trips/{trip_id}/expenses",
            json={"label": "TEST_Iter21GeneralExpense", "cost": 30, "currency": "EUR"},
            timeout=15,
        )
        assert r.status_code == 201, r.text
        assert r.json().get("stop_id") is None

        # 1 expense with stop_id set
        r = s.post(
            f"{API}/trips/{trip_id}/expenses",
            json={
                "label": "TEST_Iter21StopExpense",
                "cost": 15,
                "currency": "USD",
                "stop_id": stop_id,
            },
            timeout=15,
        )
        assert r.status_code == 201, r.text

        # 1 explicit exchange rate
        r = s.put(
            f"{API}/trips/{trip_id}/exchange-rates",
            json={"from_currency": "USD", "to_currency": "EUR", "rate": 0.91},
            timeout=15,
        )
        assert r.status_code == 200, r.text

        # Pre-delete: every child collection must have rows for this trip
        pre = {c: mongo_db[c].count_documents({"trip_id": trip_id}) for c in CHILD_COLLECTIONS}
        for c in CHILD_COLLECTIONS:
            assert pre[c] > 0, f"seed did not populate {c}: {pre}"
        assert pre["expenses"] == 2, pre

        # Delete trip
        r = s.delete(f"{API}/trips/{trip_id}", timeout=25)
        assert r.status_code == 204, r.text
        assert s.get(f"{API}/trips/{trip_id}", timeout=15).status_code == 404

        post = {c: mongo_db[c].count_documents({"trip_id": trip_id}) for c in CHILD_COLLECTIONS}
        assert all(v == 0 for v in post.values()), f"cascade left rows: {post} (pre={pre})"
        assert mongo_db.trips.count_documents({"trip_id": trip_id}) == 0

    def test_global_orphan_invariant_after_churn(self, mongo_db):
        trips = {t["trip_id"] for t in mongo_db.trips.find({}, {"_id": 0, "trip_id": 1})}
        report = {}
        for coll in CHILD_COLLECTIONS:
            orphans = [
                x.get("trip_id")
                for x in mongo_db[coll].find({}, {"_id": 0, "trip_id": 1})
                if x.get("trip_id") not in trips
            ]
            report[coll] = sorted(set(orphans))
        assert all(v == [] for v in report.values()), f"orphans present: {report}"
