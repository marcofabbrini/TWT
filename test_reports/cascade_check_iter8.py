"""Direct Mongo verification of trip delete cascade across all six collections."""
import asyncio, os, requests
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE = (fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"

s = requests.Session()
r = s.post(f"{BASE}/auth/dev-login", json={"email": "alice@twt.app", "name": "Alice"})
tok = r.json()["session_token"]
s.headers.update({"Authorization": f"Bearer {tok}"})

trip = s.post(f"{BASE}/trips", json={"title": "TEST_CASCADE_ITER8", "home_currency": "EUR",
                                     "start_date": "2026-08-01", "end_date": "2026-08-10"}).json()
tid = trip["trip_id"]
rs = s.post(f"{BASE}/trips/{tid}/stops", json={"title": "Rome", "location": "Italy",
        "start_date": "2026-08-01", "end_date": "2026-08-05", "transport_mode": "car"})
print("stop", rs.status_code, rs.text[:200])
stop = rs.json()
sid = stop["stop_id"]
a = s.post(f"{BASE}/trips/{tid}/stops/{sid}/attractions", json={"name": "Colosseum"})
h = s.post(f"{BASE}/trips/{tid}/stops/{sid}/hotels", json={"name": "Hotel X", "check_in": "2026-08-01", "check_out": "2026-08-03", "cost": 100, "currency": "USD"})
e = s.post(f"{BASE}/trips/{tid}/expenses", json={"stop_id": sid, "label": "Pizza", "cost": 20, "currency": "USD"})
x = s.put(f"{BASE}/trips/{tid}/exchange-rates", json={"from_currency": "USD", "to_currency": "EUR", "rate": 0.9})
print("seed statuses", a.status_code, h.status_code, e.status_code, x.status_code)


async def counts(dbc):
    out = {}
    out["trips"] = await dbc.trips.count_documents({"trip_id": tid})
    for c in ("trip_members", "stops", "attractions", "hotels", "expenses", "exchange_rates"):
        out[c] = await dbc[c].count_documents({"trip_id": tid})
    return out


async def main():
    client = AsyncIOMotorClient(be["MONGO_URL"])
    dbc = client[be["DB_NAME"]]
    before = await counts(dbc)
    print("BEFORE:", before)
    d = s.delete(f"{BASE}/trips/{tid}")
    print("delete status", d.status_code)
    after = await counts(dbc)
    print("AFTER:", after)
    assert all(v == 0 for v in after.values()), f"CASCADE FAIL: {after}"
    assert all(v >= 1 for v in before.values()), f"SEED FAIL: {before}"
    print("PASS: cascade removed all six collections")

asyncio.run(main())
