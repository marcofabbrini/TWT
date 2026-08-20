"""Expenses routes (Phase 3)."""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import db
from auth import require_auth
from models import Expense, ExpenseCreate, ExpenseUpdate, utcnow, new_id
from permissions import get_trip_or_404, require_role
from versioning import bump_version

logger = logging.getLogger("twt.expenses")
router = APIRouter(prefix="/trips/{trip_id}/expenses", tags=["expenses"])


async def _validate_split(trip_id: str, user_ids: list) -> None:
    """All user_ids must be accepted members of this trip."""
    if not user_ids:
        return
    unique_ids = list(set(user_ids))
    docs = await db.trip_members.find(
        {"trip_id": trip_id, "status": "accepted", "user_id": {"$in": unique_ids}},
        {"_id": 0, "user_id": 1},
    ).to_list(500)
    found = {d["user_id"] for d in docs}
    missing = set(unique_ids) - found
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"split_between contains non-member user_ids: {sorted(missing)}",
        )


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, str):
            out[k] = datetime.fromisoformat(v)
    return out


async def _validate_stop(trip_id: str, stop_id: Optional[str]):
    if not stop_id:
        return
    s = await db.stops.find_one({"stop_id": stop_id, "trip_id": trip_id}, {"_id": 0, "stop_id": 1})
    if not s:
        raise HTTPException(status_code=422, detail="Unknown stop_id")


@router.get("", response_model=List[Expense])
async def list_expenses(
    trip_id: str,
    stop_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "viewer")
    q = {"trip_id": trip_id}
    if stop_id is not None:
        q["stop_id"] = stop_id
    docs = await db.expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return [Expense(**_serialize(d)) for d in docs]


@router.post("", response_model=Expense, status_code=status.HTTP_201_CREATED)
async def create_expense(
    trip_id: str,
    body: ExpenseCreate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    trip = await get_trip_or_404(trip_id)
    await _validate_stop(trip_id, body.stop_id)

    paid_by = body.paid_by or current_user["user_id"]
    split_between = body.split_between or [current_user["user_id"]]
    currency = body.currency or trip["home_currency"]
    await _validate_split(trip_id, split_between + [paid_by])

    doc = {
        "expense_id": new_id("exp_"),
        "trip_id": trip_id,
        "stop_id": body.stop_id,
        "label": body.label.strip(),
        "cost": body.cost,
        "currency": currency,
        "paid_by": paid_by,
        "split_between": split_between,
        "notes": body.notes,
        "created_at": utcnow().isoformat(),
        "updated_at": utcnow().isoformat(),
    }
    await db.expenses.insert_one(doc)
    await bump_version(trip_id, current_user["user_id"])
    logger.info("expenses.create trip=%s exp=%s", trip_id, doc["expense_id"])
    return Expense(**_serialize(doc))


@router.patch("/{expense_id}", response_model=Expense)
async def update_expense(
    trip_id: str,
    expense_id: str,
    body: ExpenseUpdate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    existing = await db.expenses.find_one({"expense_id": expense_id, "trip_id": trip_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")

    updates = body.model_dump(exclude_unset=True)
    if "stop_id" in updates:
        await _validate_stop(trip_id, updates["stop_id"])
    if "split_between" in updates or "paid_by" in updates:
        new_split = updates.get("split_between", existing.get("split_between") or [])
        new_paid_by = updates.get("paid_by", existing.get("paid_by"))
        await _validate_split(trip_id, list(new_split) + ([new_paid_by] if new_paid_by else []))
    updates["updated_at"] = utcnow().isoformat()
    await db.expenses.update_one({"expense_id": expense_id}, {"$set": updates})
    await bump_version(trip_id, current_user["user_id"])
    doc = await db.expenses.find_one({"expense_id": expense_id}, {"_id": 0})
    return Expense(**_serialize(doc))


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    trip_id: str,
    expense_id: str,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "editor")
    r = await db.expenses.delete_one({"expense_id": expense_id, "trip_id": trip_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    await bump_version(trip_id, current_user["user_id"])
    return None
