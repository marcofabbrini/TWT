"""Independent orphan scan (iteration 21) — does NOT reuse cleanup script logic."""
import os
from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or env["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME") or env["DB_NAME"]

COLLS = ["attractions", "stops", "hotels", "expenses", "exchange_rates", "trip_members"]

c = MongoClient(MONGO_URL)
d = c[DB_NAME]
trips = {t["trip_id"] for t in d.trips.find({}, {"_id": 0, "trip_id": 1})}
print(f"live_trips={len(trips)}")
print(f"all_collections_in_db={sorted(d.list_collection_names())}")
total = 0
for coll in COLLS:
    docs = list(d[coll].find({}, {"_id": 0, "trip_id": 1}))
    orphans = [x.get("trip_id") for x in docs if x.get("trip_id") not in trips]
    missing_field = sum(1 for x in docs if "trip_id" not in x)
    total += len(orphans)
    print(f"{coll}: total={len(docs)} orphans={len(orphans)} missing_trip_id_field={missing_field} "
          f"orphan_trip_ids={sorted(set(orphans))[:5]}")
print(f"TOTAL_ORPHANS={total}")
c.close()
