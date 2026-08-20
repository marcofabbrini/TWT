"""Exchange rates routes (Phase 3, manual only)."""
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from db import db
from auth import require_auth
from models import ExchangeRate, ExchangeRateUpsert, utcnow, new_id
from permissions import require_role
from versioning import bump_version

logger = logging.getLogger("twt.rates")
router = APIRouter(prefix="/trips/{trip_id}/exchange-rates", tags=["exchange_rates"])


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    v = out.get("updated_at")
    if isinstance(v, str):
        out["updated_at"] = datetime.fromisoformat(v)
    return out


@router.get("", response_model=List[ExchangeRate])
async def list_rates(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    docs = await db.exchange_rates.find({"trip_id": trip_id}, {"_id": 0}).to_list(500)
    return [ExchangeRate(**_serialize(d)) for d in docs]


@router.put("", response_model=ExchangeRate)
async def upsert_rate(
    trip_id: str,
    body: ExchangeRateUpsert,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "owner")

    filt = {
        "trip_id": trip_id,
        "from_currency": body.from_currency,
        "to_currency": body.to_currency,
    }
    now_iso = utcnow().isoformat()
    existing = await db.exchange_rates.find_one(filt, {"_id": 0})
    if existing:
        await db.exchange_rates.update_one(
            filt,
            {"$set": {"rate": body.rate, "updated_at": now_iso, "updated_by": current_user["user_id"]}},
        )
        doc = await db.exchange_rates.find_one(filt, {"_id": 0})
    else:
        doc = {
            "rate_id": new_id("rate_"),
            **filt,
            "rate": body.rate,
            "updated_at": now_iso,
            "updated_by": current_user["user_id"],
        }
        await db.exchange_rates.insert_one(doc)
    await bump_version(trip_id, current_user["user_id"])
    logger.info("rates.upsert trip=%s %s->%s=%s", trip_id, body.from_currency, body.to_currency, body.rate)
    return ExchangeRate(**_serialize(doc))


@router.delete("/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate(
    trip_id: str,
    rate_id: str,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "owner")
    r = await db.exchange_rates.delete_one({"rate_id": rate_id, "trip_id": trip_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rate not found")
    await bump_version(trip_id, current_user["user_id"])
    return None
