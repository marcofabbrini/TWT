"""Ad-hoc orphan/data-integrity check against Mongo (read-only)."""
import os
from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
db = MongoClient(os.environ.get("MONGO_URL") or env["MONGO_URL"])[
    os.environ.get("DB_NAME") or env["DB_NAME"]]

trip_ids = {t["trip_id"] for t in db.trips.find({}, {"trip_id": 1})}
print("trips:", len(trip_ids))
for coll in ("stops", "attractions", "trip_members"):
    docs = list(db[coll].find({}, {"trip_id": 1}))
    orphans = [d for d in docs if d.get("trip_id") not in trip_ids]
    print(f"{coll}: total={len(docs)} orphans={len(orphans)}")
print("TEST_ trips left:", db.trips.count_documents({"title": {"$regex": "^TEST_"}}))
