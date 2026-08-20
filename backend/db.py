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

    logger.info("MongoDB indexes ensured")
