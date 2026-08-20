"""Seed legacy expenses without expense_date, run backfill, verify idempotency."""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from db import db  # noqa


async def main():
    trip = await db.trips.find_one({"title": {"$regex": "SPRINTAB_UI Roma"}}, {"_id": 0})
    if not trip:
        print("no test trip found; create one first")
        return
    tid = trip["trip_id"]
    stop = await db.stops.find_one({"trip_id": tid}, {"_id": 0})
    now = datetime.now(timezone.utc).isoformat()
    docs = [
        {"expense_id": "exp_TESTBF1", "trip_id": tid, "stop_id": stop["stop_id"] if stop else None,
         "label": "TEST_BF_with_stop", "cost": 1, "currency": "EUR", "paid_by": trip["owner_id"],
         "split_between": [trip["owner_id"]], "created_at": now, "updated_at": now},
        {"expense_id": "exp_TESTBF2", "trip_id": tid, "stop_id": None,
         "label": "TEST_BF_no_stop", "cost": 2, "currency": "EUR", "paid_by": trip["owner_id"],
         "split_between": [trip["owner_id"]], "created_at": now, "updated_at": now},
    ]
    await db.expenses.delete_many({"expense_id": {"$in": ["exp_TESTBF1", "exp_TESTBF2"]}})
    await db.expenses.insert_many(docs)
    print("seeded trip", tid, "stop", stop["stop_id"] if stop else None,
          "trip.start_date", trip["start_date"], "stop.start_date", stop.get("start_date") if stop else None)


if __name__ == "__main__":
    asyncio.run(main())
