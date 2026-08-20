"""One-shot backfill for Expense.expense_date.

Rule:
  - if expense.stop_id → expense_date = stop.start_date
  - else               → expense_date = trip.start_date

Idempotent: only touches documents where expense_date is missing/null.
Safe to re-run any number of times.

Usage:
  cd /app/backend && python -m scripts.backfill_expense_date
"""
import asyncio
import logging
import os
import sys
from datetime import date, datetime

# Allow running as `python -m scripts.backfill_expense_date` OR directly.
if __package__ is None:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_expense_date")


def _to_date_str(v) -> str | None:
    if isinstance(v, str):
        return v[:10]
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return None


async def main() -> int:
    # Only expenses missing expense_date
    q = {"$or": [{"expense_date": {"$exists": False}}, {"expense_date": None}]}
    cursor = db.expenses.find(q, {"_id": 0})

    trip_cache: dict[str, dict] = {}
    stop_cache: dict[str, dict] = {}
    updated = 0
    scanned = 0

    async for exp in cursor:
        scanned += 1
        trip_id = exp["trip_id"]
        stop_id = exp.get("stop_id")

        # Load trip if needed
        trip = trip_cache.get(trip_id)
        if trip is None:
            trip = await db.trips.find_one({"trip_id": trip_id}, {"_id": 0})
            if trip:
                trip_cache[trip_id] = trip
        if not trip:
            log.warning("skip exp=%s trip=%s not found", exp["expense_id"], trip_id)
            continue

        new_date_str: str | None = None
        if stop_id:
            stop = stop_cache.get(stop_id)
            if stop is None:
                stop = await db.stops.find_one({"stop_id": stop_id}, {"_id": 0})
                if stop:
                    stop_cache[stop_id] = stop
            if stop:
                new_date_str = _to_date_str(stop.get("start_date"))
        if not new_date_str:
            new_date_str = _to_date_str(trip.get("start_date"))

        if not new_date_str:
            log.warning("skip exp=%s: no fallback date", exp["expense_id"])
            continue

        await db.expenses.update_one(
            {"expense_id": exp["expense_id"]},
            {"$set": {"expense_date": new_date_str}},
        )
        updated += 1

    log.info("done scanned=%d updated=%d (already_ok=%d)", scanned, updated, scanned - updated)
    return updated


if __name__ == "__main__":
    n = asyncio.run(main())
    print(f"backfilled {n} expenses")
