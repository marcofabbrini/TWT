"""Orphan integrity check across child collections."""
import os
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pymongo import MongoClient

m = MongoClient(os.environ["MONGO_URL"])
d = m[os.environ["DB_NAME"]]
trips = {t["trip_id"] for t in d.trips.find({}, {"_id": 0, "trip_id": 1})}
print("live_trips:", len(trips))
for coll in ["expenses", "stops", "hotels", "attractions", "exchange_rates", "trip_members"]:
    total = d[coll].count_documents({})
    orphans = [x.get("trip_id") for x in d[coll].find({}, {"_id": 0, "trip_id": 1}) if x.get("trip_id") not in trips]
    print(f"{coll}: total={total} orphans={len(orphans)} sample={orphans[:5]}")
m.close()
