"""One-shot cleanup for orphan child docs of `trips`.

Removes any document in the trip's child collections (stops, attractions,
hotels, expenses, exchange_rates, trip_members) whose `trip_id` no longer
exists in `trips`.

Context: the Sprint A+B tester flagged 5 orphan expenses; a follow-up scan
found 10 orphan `hotels` and 1 orphan `exchange_rates` from the same legacy
2026-08-20 09:30-09:34 pytest-xdist race window. The application cascade in
`backend/trips.py::delete_trip` IS correct for ALL child collections
(verified live in orphan_cascade_iter20_test.py); this script only cleans
historical data.

Idempotent: reports removed=0 on any subsequent run.

Usage:
  cd /app/backend && python -m scripts.cleanup_orphan_expenses
"""
import asyncio
import logging
import os
import sys

if __package__ is None:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cleanup_orphan_expenses")

# Collections whose docs carry a `trip_id` field and MUST be purged when
# their host trip disappears.  Order intentionally mirrors delete_trip cascade.
CHILD_COLLECTIONS = [
    "attractions",
    "stops",
    "hotels",
    "expenses",
    "exchange_rates",
    "trip_members",
]


async def main() -> int:
    # Snapshot of live trip ids.
    live_trip_ids: set[str] = set()
    async for t in db.trips.find({}, {"_id": 0, "trip_id": 1}):
        live_trip_ids.add(t["trip_id"])

    total_removed = 0
    per_coll_removed: dict[str, int] = {}

    for coll_name in CHILD_COLLECTIONS:
        coll = getattr(db, coll_name)
        # Find distinct trip_ids referenced in this collection.
        referenced = await coll.distinct("trip_id")
        stale = [tid for tid in referenced if tid not in live_trip_ids]
        if not stale:
            per_coll_removed[coll_name] = 0
            continue
        r = await coll.delete_many({"trip_id": {"$in": stale}})
        per_coll_removed[coll_name] = r.deleted_count
        total_removed += r.deleted_count
        log.info("removed=%d from %s (stale_trips=%d)", r.deleted_count, coll_name, len(stale))

    log.info(
        "done live_trips=%d removed=%d per_coll=%s",
        len(live_trip_ids),
        total_removed,
        per_coll_removed,
    )
    # Keep the legacy "removed=N" grep pattern for the idempotency test.
    print(f"orphans_found={total_removed} removed={total_removed}")
    return total_removed


if __name__ == "__main__":
    n = asyncio.run(main())
    sys.exit(0)
