"""Inspect orphan hotels / exchange_rates (new WARN found in iteration 20)."""
import os
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pymongo import MongoClient

m = MongoClient(os.environ["MONGO_URL"])
d = m[os.environ["DB_NAME"]]
trips = {t["trip_id"] for t in d.trips.find({}, {"_id": 0, "trip_id": 1})}
for coll in ["hotels", "exchange_rates"]:
    print(f"=== {coll}")
    for x in d[coll].find({}, {"_id": 0}):
        if x.get("trip_id") not in trips:
            print({k: x.get(k) for k in ("trip_id", "hotel_id", "stop_id", "name", "base", "quote", "created_at", "updated_at")})
m.close()
