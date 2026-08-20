"""Trip summary aggregation (Phase 3)."""
import logging
from collections import defaultdict
from typing import List

from fastapi import APIRouter, Depends

from db import db
from auth import require_auth
from permissions import get_trip_or_404, require_role

logger = logging.getLogger("twt.summary")
router = APIRouter(prefix="/trips/{trip_id}", tags=["summary"])


@router.get("/summary")
async def trip_summary(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    trip = await get_trip_or_404(trip_id)
    home_currency = trip["home_currency"]

    # Sum of km_from_prev across all stops (Phase 5).
    km_docs = await db.stops.find(
        {"trip_id": trip_id, "km_from_prev": {"$ne": None}},
        {"_id": 0, "km_from_prev": 1},
    ).to_list(2000)
    total_km_val = round(sum(d["km_from_prev"] for d in km_docs), 1) if km_docs else None

    # Load rates map for this trip.
    rates_docs = await db.exchange_rates.find({"trip_id": trip_id}, {"_id": 0}).to_list(500)
    rates = {(r["from_currency"], r["to_currency"]): r["rate"] for r in rates_docs}

    def convert(amount: float, currency: str, item_id: str, missing: dict) -> float | None:
        """Return converted amount in home_currency, or None if rate is missing.
        Records the item into `missing[(from,to)]` when unavailable.
        """
        if amount is None:
            return 0.0
        if currency == home_currency:
            return float(amount)
        key = (currency, home_currency)
        if key in rates:
            return float(amount) * rates[key]
        missing[key].append(item_id)
        return None

    missing_map = defaultdict(list)
    breakdown = {"hotels": 0.0, "attractions": 0.0, "expenses": 0.0}

    # Hotels
    hotels = await db.hotels.find({"trip_id": trip_id}, {"_id": 0, "hotel_id": 1, "cost": 1, "currency": 1}).to_list(2000)
    for h in hotels:
        c = convert(h.get("cost") or 0.0, h.get("currency") or home_currency, h["hotel_id"], missing_map)
        if c is not None:
            breakdown["hotels"] += c

    # Attractions with cost
    atts = await db.attractions.find(
        {"trip_id": trip_id, "cost": {"$ne": None, "$gt": 0}},
        {"_id": 0, "attraction_id": 1, "cost": 1, "currency": 1},
    ).to_list(5000)
    for a in atts:
        c = convert(a["cost"], a.get("currency") or home_currency, a["attraction_id"], missing_map)
        if c is not None:
            breakdown["attractions"] += c

    # Expenses
    exps = await db.expenses.find({"trip_id": trip_id}, {"_id": 0, "expense_id": 1, "cost": 1, "currency": 1}).to_list(5000)
    for e in exps:
        c = convert(e.get("cost") or 0.0, e.get("currency") or home_currency, e["expense_id"], missing_map)
        if c is not None:
            breakdown["expenses"] += c

    total = round(sum(breakdown.values()), 2)
    breakdown = {k: round(v, 2) for k, v in breakdown.items()}

    missing_rates = [
        {"from": frm, "to": to, "affected_items": ids}
        for (frm, to), ids in missing_map.items()
    ]

    return {
        "total_km": total_km_val,
        "total_cost_home_currency": total,
        "home_currency": home_currency,
        "breakdown": breakdown,
        "missing_rates": missing_rates,
    }
