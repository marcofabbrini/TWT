from pymongo import MongoClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
cli = MongoClient(env["MONGO_URL"])
db = cli[env["DB_NAME"]]
for sid in ["stop_30efa137f9c04cfc", "stop_86fcb614e2d4444d"]:
    print("=== stop", sid)
    print("stop doc:", db.stops.find_one({"stop_id": sid}, {"_id": 0, "title": 1, "trip_id": 1, "order": 1}))
    for d in db.attractions.find({"stop_id": sid}, {"_id": 0, "name": 1, "order": 1, "trip_id": 1, "created_at": 1}):
        print("  att:", d)
    tid = None
    a = db.attractions.find_one({"stop_id": sid}, {"_id": 0, "trip_id": 1})
    if a:
        tid = a["trip_id"]
        print("  trip doc:", db.trips.find_one({"trip_id": tid}, {"_id": 0, "title": 1}))
