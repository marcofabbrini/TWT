"""Iteration 20 — full-cascade regression (all child collections).

Extends orphan_expenses_test.py: proves DELETE /api/trips/{id} removes rows
from EVERY child collection (stops, hotels, expenses, attractions,
exchange_rates, trip_members), not just expenses. Added because iteration-20
integrity scan found 10 orphan `hotels` + 1 orphan `exchange_rates` doc from
the same 2026-08-20 09:30-09:34 legacy pytest-xdist window.
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
    "stops",
    "hotels",
    "expenses",
    "attractions",
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
    r = s.post(f"{API}/auth/dev-login", json={"email": "orphan_regress@twt.app", "name": "OrphanRegress"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


class TestFullCascade:
    def test_delete_trip_purges_every_child_collection(self, session, mongo_db):
        s = session
        r = s.post(
            f"{API}/trips",
            json={"title": "TEST_FullCascade", "home_currency": "EUR",
                  "start_date": "2026-07-01", "end_date": "2026-07-10"},
            timeout=15,
        )
        assert r.status_code == 201, r.text
        trip_id = r.json()["trip_id"]

        # stop
        r = s.post(f"{API}/trips/{trip_id}/stops",
                   json={"title": "TEST_Stop", "location": "Roma", "start_date": "2026-07-01",
                         "end_date": "2026-07-03", "transport_mode": "car"}, timeout=20)
        assert r.status_code == 201, r.text
        stop_id = r.json()["stop_id"]

        # hotel on the stop (the orphan class found in the scan) — USD forces an
        # exchange_rates row to be created for this trip too.
        r = s.post(f"{API}/trips/{trip_id}/stops/{stop_id}/hotels",
                   json={"name": "TEST_CascadeHotel", "check_in": "2026-07-01",
                         "check_out": "2026-07-03", "cost": 100, "currency": "USD"},
                   timeout=20)
        assert r.status_code == 201, r.text

        # expense with stop_id=None
        r = s.post(f"{API}/trips/{trip_id}/expenses",
                   json={"label": "TEST_CascadeExpense", "cost": 20, "currency": "USD"}, timeout=15)
        assert r.status_code == 201, r.text

        # attraction
        r = s.post(f"{API}/trips/{trip_id}/stops/{stop_id}/attractions",
                   json={"name": "TEST_CascadeAttr", "cost": 5, "currency": "EUR"}, timeout=15)
        assert r.status_code in (200, 201), r.text

        # Pre-delete: at least stops/hotels/expenses/trip_members must exist in Mongo
        pre = {c: mongo_db[c].count_documents({"trip_id": trip_id}) for c in CHILD_COLLECTIONS}
        for c in ["stops", "hotels", "expenses", "trip_members"]:
            assert pre[c] > 0, f"expected seeded rows in {c}, got {pre}"

        # Delete trip
        r = s.delete(f"{API}/trips/{trip_id}", timeout=20)
        assert r.status_code == 204, r.text
        assert s.get(f"{API}/trips/{trip_id}", timeout=15).status_code == 404

        post = {c: mongo_db[c].count_documents({"trip_id": trip_id}) for c in CHILD_COLLECTIONS}
        assert all(v == 0 for v in post.values()), f"cascade left rows behind: {post} (pre={pre})"
        assert mongo_db.trips.count_documents({"trip_id": trip_id}) == 0


class TestDbIntegrity:
    def test_no_orphan_expenses_remain(self, mongo_db):
        trips = {t["trip_id"] for t in mongo_db.trips.find({}, {"_id": 0, "trip_id": 1})}
        orphans = [e.get("expense_id") for e in mongo_db.expenses.find({}, {"_id": 0, "expense_id": 1, "trip_id": 1})
                   if e.get("trip_id") not in trips]
        assert orphans == [], f"orphan expenses: {orphans}"

    @pytest.mark.parametrize("coll", ["stops", "hotels", "attractions", "exchange_rates", "trip_members"])
    def test_no_orphans_in_other_child_collections(self, mongo_db, coll):
        trips = {t["trip_id"] for t in mongo_db.trips.find({}, {"_id": 0, "trip_id": 1})}
        orphans = [x.get("trip_id") for x in mongo_db[coll].find({}, {"_id": 0, "trip_id": 1})
                   if x.get("trip_id") not in trips]
        assert orphans == [], f"{coll} has {len(orphans)} orphan docs (trip_ids={sorted(set(orphans))})"
