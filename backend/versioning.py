"""Shared helpers used by mutation endpoints (Phase 4)."""
import logging
from db import db
from models import utcnow

logger = logging.getLogger("twt.versioning")


async def bump_version(trip_id: str, user_id: str) -> None:
    """Increment trips.version + set last_updated_at/last_updated_by.

    Idempotent per call; safe to call from every mutation.
    """
    await db.trips.update_one(
        {"trip_id": trip_id},
        {
            "$inc": {"version": 1},
            "$set": {
                "last_updated_at": utcnow().isoformat(),
                "last_updated_by": user_id,
                "updated_at": utcnow().isoformat(),
            },
        },
    )
