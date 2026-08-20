"""MongoDB connection + index bootstrap."""
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger("twt.db")

_mongo_url = os.environ["MONGO_URL"]
_db_name = os.environ["DB_NAME"]

client = AsyncIOMotorClient(_mongo_url)
db = client[_db_name]


async def ensure_indexes() -> None:
    # users
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("email", unique=True)
    await db.users.create_index("google_id", sparse=True)

    # user_sessions (Emergent Auth)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("user_id")
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)

    # trips
    await db.trips.create_index("trip_id", unique=True)
    await db.trips.create_index("owner_id")
    await db.trips.create_index([("start_date", DESCENDING)])

    # trip_members
    await db.trip_members.create_index("member_id", unique=True)
    await db.trip_members.create_index([("trip_id", ASCENDING), ("user_id", ASCENDING)])
    await db.trip_members.create_index("user_id")
    await db.trip_members.create_index("invited_email")

    # stops (Phase 2)
    await db.stops.create_index("stop_id", unique=True)
    await db.stops.create_index([("trip_id", ASCENDING), ("order", ASCENDING)])

    # attractions (Phase 2)
    await db.attractions.create_index("attraction_id", unique=True)
    await db.attractions.create_index(
        [("trip_id", ASCENDING), ("stop_id", ASCENDING), ("order", ASCENDING)]
    )

    # hotels (Phase 3)
    await db.hotels.create_index("hotel_id", unique=True)
    await db.hotels.create_index([("trip_id", ASCENDING), ("stop_id", ASCENDING)])

    # expenses (Phase 3)
    await db.expenses.create_index("expense_id", unique=True)
    await db.expenses.create_index("trip_id")

    # exchange_rates (Phase 3)
    await db.exchange_rates.create_index("rate_id", unique=True)
    await db.exchange_rates.create_index(
        [("trip_id", ASCENDING), ("from_currency", ASCENDING), ("to_currency", ASCENDING)],
        unique=True,
    )

    # trip_presence (Phase 4) — TTL for auto-cleanup
    await db.trip_presence.create_index(
        [("trip_id", ASCENDING), ("user_id", ASCENDING)], unique=True
    )
    await db.trip_presence.create_index("last_seen_at", expireAfterSeconds=60)

    # trip_members Phase 4 additions
    await db.trip_members.create_index("invite_token", sparse=True, unique=True)

    # geocode_cache (Phase 5) — 30 day TTL
    await db.geocode_cache.create_index("key", unique=True)
    await db.geocode_cache.create_index("cached_at", expireAfterSeconds=60 * 60 * 24 * 30)

    # route_cache (Map) — 30 day TTL, compound unique on quantised coords + mode
    await db.route_cache.create_index(
        [
            ("from_lng", ASCENDING),
            ("from_lat", ASCENDING),
            ("to_lng", ASCENDING),
            ("to_lat", ASCENDING),
            ("transport_mode", ASCENDING),
        ],
        unique=True,
    )
    await db.route_cache.create_index("cached_at", expireAfterSeconds=60 * 60 * 24 * 30)

    logger.info("MongoDB indexes ensured")
