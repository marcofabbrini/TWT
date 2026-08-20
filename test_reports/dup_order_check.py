# Sanity: no duplicate order per (trip_id, stop_id) in attractions, and per trip_id in stops
import os
from pymongo import MongoClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
cli = MongoClient(env["MONGO_URL"])
db = cli[env["DB_NAME"]]

dups = list(db.attractions.aggregate([
    {"$group": {"_id": {"t": "$trip_id", "s": "$stop_id", "o": "$order"}, "n": {"$sum": 1}}},
    {"$match": {"n": {"$gt": 1}}},
]))
print("attraction duplicate (trip,stop,order) groups:", len(dups))
for d in dups[:10]:
    print("  ", d)

sdups = list(db.stops.aggregate([
    {"$group": {"_id": {"t": "$trip_id", "o": "$order"}, "n": {"$sum": 1}}},
    {"$match": {"n": {"$gt": 1}}},
]))
print("stop duplicate (trip,order) groups:", len(sdups))
for d in sdups[:10]:
    print("  ", d)

# contiguity check per stop
bad = 0
for key in db.attractions.distinct("stop_id"):
    docs = list(db.attractions.find({"stop_id": key}, {"_id": 0, "order": 1, "trip_id": 1}))
    orders = sorted(d.get("order", -1) for d in docs)
    if orders != list(range(len(docs))):
        bad += 1
        if bad <= 10:
            print("  non-contiguous stop", key, orders)
print("non-contiguous stops:", bad)
