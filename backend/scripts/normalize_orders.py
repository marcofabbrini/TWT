"""
One-shot migration: renormalize order values across every trip.

Ensures for every (trip_id) the `stops.order` sequence is 0..N-1
and for every (trip_id, stop_id) the `attractions.order` sequence is 0..M-1.
Tie-break: current order asc, then created_at asc.

Idempotent — safe to run multiple times.
"""
import asyncio
import os
import sys
from pathlib import Path

# Allow running as `python scripts/normalize_orders.py` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, UpdateOne

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    trips = await db.trips.find({}, {"_id": 0, "trip_id": 1, "title": 1}).to_list(10000)
    print(f"Found {len(trips)} trips")

    changes_stops = 0
    changes_attrs = 0

    for trip in trips:
        trip_id = trip["trip_id"]

        # Stops: renormalize per trip
        stops = await db.stops.find(
            {"trip_id": trip_id},
            {"_id": 0, "stop_id": 1, "order": 1, "created_at": 1},
        ).sort([("order", ASCENDING), ("created_at", ASCENDING)]).to_list(10000)

        stop_ops = [
            UpdateOne(
                {"stop_id": s["stop_id"], "trip_id": trip_id},
                {"$set": {"order": i}},
            )
            for i, s in enumerate(stops)
            if s.get("order") != i
        ]
        if stop_ops:
            r = await db.stops.bulk_write(stop_ops, ordered=False)
            changes_stops += r.modified_count
            print(f"  trip={trip_id} '{trip.get('title','')}' stops: fixed {r.modified_count}/{len(stops)}")

        # Attractions: renormalize per (trip_id, stop_id)
        for s in stops:
            atts = await db.attractions.find(
                {"trip_id": trip_id, "stop_id": s["stop_id"]},
                {"_id": 0, "attraction_id": 1, "order": 1, "created_at": 1},
            ).sort([("order", ASCENDING), ("created_at", ASCENDING)]).to_list(10000)

            att_ops = [
                UpdateOne(
                    {"attraction_id": a["attraction_id"], "trip_id": trip_id},
                    {"$set": {"order": i}},
                )
                for i, a in enumerate(atts)
                if a.get("order") != i
            ]
            if att_ops:
                r = await db.attractions.bulk_write(att_ops, ordered=False)
                changes_attrs += r.modified_count
                print(f"    stop={s['stop_id']} attractions: fixed {r.modified_count}/{len(atts)}")

    print("─" * 60)
    print(f"DONE. stops modified={changes_stops}  attractions modified={changes_attrs}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
