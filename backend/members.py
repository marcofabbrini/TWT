"""Members, invites, presence, version, debts (Phase 4)."""
import logging
import os
import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from db import db
from auth import require_auth
from models import utcnow, new_id
from permissions import get_trip_or_404, get_membership_or_404, require_role
from versioning import bump_version

logger = logging.getLogger("twt.members")


# ── Models ─────────────────────────────────────────────
class InviteCreate(BaseModel):
    email: EmailStr
    role: Literal["editor", "viewer"]


class MemberPatch(BaseModel):
    role: Literal["editor", "viewer"]


class PresencePost(BaseModel):
    editing: Optional[str] = None


class InvitePublic(BaseModel):
    trip_title: str
    inviter_name: str
    invited_email: str
    role: str
    status: str


# ── Routers ────────────────────────────────────────────
trip_router = APIRouter(prefix="/trips/{trip_id}", tags=["members"])
invites_router = APIRouter(prefix="/invites", tags=["invites"])

INVITE_TTL_DAYS = 30


def _frontend_url() -> str:
    # Emergent preview URL; the frontend serves the trip UI so we share the same host.
    return os.environ.get("FRONTEND_URL", "").rstrip("/") or ""


async def _member_public(m: dict) -> dict:
    user = None
    if m.get("user_id"):
        user = await db.users.find_one(
            {"user_id": m["user_id"]},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "avatar_url": 1},
        )
    return {
        "member_id": m["member_id"],
        "trip_id": m["trip_id"],
        "role": m["role"],
        "status": m["status"],
        "invited_email": m.get("invited_email"),
        "created_at": m.get("created_at"),
        "user": user,
    }


# ── Members list & mgmt ────────────────────────────────
@trip_router.get("/members")
async def list_members(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    docs = await db.trip_members.find({"trip_id": trip_id}, {"_id": 0}).to_list(500)
    return [await _member_public(d) for d in docs]


@trip_router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    trip_id: str,
    body: InviteCreate,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "owner")
    trip = await get_trip_or_404(trip_id)
    email = body.email.lower().strip()

    if email == current_user["email"].lower():
        raise HTTPException(status_code=400, detail="You cannot invite yourself")

    existing = await db.trip_members.find_one(
        {"trip_id": trip_id, "$or": [
            {"invited_email": email},
            {"user_id": {"$ne": None}},
        ]},
        {"_id": 0},
    )
    # More precise: check any active membership by email or by user with that email.
    dup = await db.trip_members.find_one(
        {"trip_id": trip_id, "invited_email": email, "status": {"$in": ["pending", "accepted"]}},
        {"_id": 0},
    )
    if dup:
        raise HTTPException(status_code=409, detail="A member/invite already exists for this email")
    # Also check by resolved user
    user_by_email = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    if user_by_email:
        dup2 = await db.trip_members.find_one(
            {"trip_id": trip_id, "user_id": user_by_email["user_id"], "status": "accepted"},
            {"_id": 0},
        )
        if dup2:
            raise HTTPException(status_code=409, detail="This user is already a member")

    token = secrets.token_urlsafe(24)
    expires_at = utcnow() + timedelta(days=INVITE_TTL_DAYS)
    doc = {
        "member_id": new_id("mem_"),
        "trip_id": trip_id,
        "user_id": None,
        "invited_email": email,
        "role": body.role,
        "status": "pending",
        "invite_token": token,
        "invited_by": current_user["user_id"],
        "invite_expires_at": expires_at.isoformat(),
        "created_at": utcnow().isoformat(),
    }
    await db.trip_members.insert_one(doc)
    await bump_version(trip_id, current_user["user_id"])
    fe = _frontend_url()
    invite_url = f"{fe}/invite/{token}" if fe else f"/invite/{token}"
    logger.info("invites.create trip=%s email=%s by=%s", trip_id, email, current_user["user_id"])
    return {"invite_token": token, "invite_url": invite_url, "expires_at": expires_at.isoformat(), "role": body.role, "invited_email": email}


@trip_router.patch("/members/{member_id}")
async def patch_member(
    trip_id: str,
    member_id: str,
    body: MemberPatch,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "owner")
    m = await db.trip_members.find_one({"member_id": member_id, "trip_id": trip_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    if m["role"] == "owner":
        raise HTTPException(status_code=400, detail="Cannot change the owner's role directly")
    if m.get("user_id") == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    await db.trip_members.update_one({"member_id": member_id}, {"$set": {"role": body.role}})
    await bump_version(trip_id, current_user["user_id"])
    updated = await db.trip_members.find_one({"member_id": member_id}, {"_id": 0})
    return await _member_public(updated)


async def _transfer_or_delete_trip(trip_id: str, actor_user_id: str) -> str:
    """When owner leaves: promote oldest editor, else hard-delete the trip.
    Returns 'transferred' or 'deleted'.
    """
    editor = await db.trip_members.find_one(
        {"trip_id": trip_id, "role": "editor", "status": "accepted"},
        {"_id": 0},
        sort=[("created_at", 1)],
    )
    if editor:
        await db.trip_members.update_one({"member_id": editor["member_id"]}, {"$set": {"role": "owner"}})
        await db.trips.update_one({"trip_id": trip_id}, {"$set": {"owner_id": editor["user_id"]}})
        await bump_version(trip_id, actor_user_id)
        logger.info("trips.transfer trip=%s new_owner=%s", trip_id, editor["user_id"])
        return "transferred"

    # Cascade delete (same as trips.delete_trip)
    await db.attractions.delete_many({"trip_id": trip_id})
    await db.stops.delete_many({"trip_id": trip_id})
    await db.hotels.delete_many({"trip_id": trip_id})
    await db.expenses.delete_many({"trip_id": trip_id})
    await db.exchange_rates.delete_many({"trip_id": trip_id})
    await db.trip_presence.delete_many({"trip_id": trip_id})
    await db.trip_members.delete_many({"trip_id": trip_id})
    await db.trips.delete_one({"trip_id": trip_id})
    logger.info("trips.autodelete trip=%s (no editors left)", trip_id)
    return "deleted"


@trip_router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    trip_id: str,
    member_id: str,
    current_user: dict = Depends(require_auth),
):
    m = await db.trip_members.find_one({"member_id": member_id, "trip_id": trip_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    # Owner can remove anyone. Non-owner can only remove themselves.
    my_m = await get_membership_or_404(trip_id, current_user["user_id"])
    if m.get("user_id") != current_user["user_id"] and my_m["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can remove other members")

    is_self_owner = m.get("user_id") == current_user["user_id"] and m["role"] == "owner"

    await db.trip_members.delete_one({"member_id": member_id})
    if is_self_owner:
        await _transfer_or_delete_trip(trip_id, current_user["user_id"])
    else:
        await bump_version(trip_id, current_user["user_id"])
    return None


@trip_router.post("/leave", status_code=status.HTTP_200_OK)
async def leave_trip(trip_id: str, current_user: dict = Depends(require_auth)):
    m = await db.trip_members.find_one(
        {"trip_id": trip_id, "user_id": current_user["user_id"], "status": "accepted"},
        {"_id": 0},
    )
    if not m:
        raise HTTPException(status_code=404, detail="You are not a member of this trip")

    await db.trip_members.delete_one({"member_id": m["member_id"]})
    if m["role"] == "owner":
        outcome = await _transfer_or_delete_trip(trip_id, current_user["user_id"])
        return {"outcome": outcome}
    await bump_version(trip_id, current_user["user_id"])
    return {"outcome": "left"}


# ── Public invites ─────────────────────────────────────
@invites_router.get("/{invite_token}", response_model=InvitePublic)
async def get_invite(invite_token: str):
    m = await db.trip_members.find_one({"invite_token": invite_token}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Invite not found")
    if m["status"] != "pending":
        raise HTTPException(status_code=410, detail="Invite is no longer active")

    trip = await db.trips.find_one({"trip_id": m["trip_id"]}, {"_id": 0, "title": 1, "owner_id": 1})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip no longer exists")
    inviter = await db.users.find_one({"user_id": m.get("invited_by") or trip["owner_id"]}, {"_id": 0, "name": 1})
    return InvitePublic(
        trip_title=trip["title"],
        inviter_name=(inviter or {}).get("name", "Someone"),
        invited_email=m["invited_email"],
        role=m["role"],
        status=m["status"],
    )


@invites_router.post("/{invite_token}/accept")
async def accept_invite(invite_token: str, current_user: dict = Depends(require_auth)):
    m = await db.trip_members.find_one({"invite_token": invite_token}, {"_id": 0})
    if not m or m["status"] != "pending":
        raise HTTPException(status_code=410, detail="Invite is no longer active")
    if m["invited_email"].lower() != current_user["email"].lower():
        raise HTTPException(status_code=403, detail=f"This invite is for {m['invited_email']}")

    await db.trip_members.update_one(
        {"member_id": m["member_id"]},
        {"$set": {
            "status": "accepted",
            "user_id": current_user["user_id"],
            "accepted_at": utcnow().isoformat(),
        }, "$unset": {"invite_token": ""}},
    )
    await bump_version(m["trip_id"], current_user["user_id"])
    trip = await db.trips.find_one({"trip_id": m["trip_id"]}, {"_id": 0})
    return {"trip_id": m["trip_id"], "role": m["role"], "trip": trip}


@invites_router.post("/{invite_token}/decline")
async def decline_invite(invite_token: str, current_user: dict = Depends(require_auth)):
    m = await db.trip_members.find_one({"invite_token": invite_token}, {"_id": 0})
    if not m or m["status"] != "pending":
        raise HTTPException(status_code=410, detail="Invite is no longer active")
    if m["invited_email"].lower() != current_user["email"].lower():
        raise HTTPException(status_code=403, detail="This invite is for another email")
    await db.trip_members.update_one(
        {"member_id": m["member_id"]},
        {"$set": {"status": "declined"}, "$unset": {"invite_token": ""}},
    )
    return {"ok": True}


# ── Version (sync polling) ─────────────────────────────
@trip_router.get("/version")
async def get_version(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    trip = await db.trips.find_one(
        {"trip_id": trip_id},
        {"_id": 0, "version": 1, "last_updated_at": 1, "last_updated_by": 1},
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {
        "version": trip.get("version", 0),
        "last_updated_at": trip.get("last_updated_at"),
        "last_updated_by": trip.get("last_updated_by"),
    }


# ── Presence ───────────────────────────────────────────
@trip_router.post("/presence")
async def post_presence(
    trip_id: str,
    body: PresencePost,
    current_user: dict = Depends(require_auth),
):
    await require_role(trip_id, current_user["user_id"], "viewer")
    await db.trip_presence.update_one(
        {"trip_id": trip_id, "user_id": current_user["user_id"]},
        {"$set": {
            "trip_id": trip_id,
            "user_id": current_user["user_id"],
            "editing": body.editing,
            "last_seen_at": utcnow(),
        }},
        upsert=True,
    )
    return {"ok": True}


@trip_router.get("/presence")
async def get_presence(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    cutoff = utcnow() - timedelta(seconds=30)
    docs = await db.trip_presence.find(
        {"trip_id": trip_id, "last_seen_at": {"$gte": cutoff}},
        {"_id": 0},
    ).to_list(200)
    out = []
    for d in docs:
        u = await db.users.find_one(
            {"user_id": d["user_id"]},
            {"_id": 0, "user_id": 1, "name": 1, "avatar_url": 1},
        )
        if not u:
            continue
        ls = d.get("last_seen_at")
        if isinstance(ls, datetime):
            ls = ls.isoformat()
        out.append({
            "user_id": d["user_id"],
            "name": u.get("name"),
            "avatar_url": u.get("avatar_url"),
            "editing": d.get("editing"),
            "last_seen_at": ls,
        })
    return out


# ── Debts (settlements) ────────────────────────────────
@trip_router.get("/debts")
async def get_debts(trip_id: str, current_user: dict = Depends(require_auth)):
    await require_role(trip_id, current_user["user_id"], "viewer")
    trip = await get_trip_or_404(trip_id)
    home = trip["home_currency"]

    # Accepted members
    members = await db.trip_members.find(
        {"trip_id": trip_id, "status": "accepted"},
        {"_id": 0, "user_id": 1, "role": 1},
    ).to_list(200)
    user_ids = [m["user_id"] for m in members if m.get("user_id")]
    if not user_ids:
        return {"home_currency": home, "balances": [], "settlements": [], "missing_rates": []}

    users = await db.users.find(
        {"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "name": 1, "avatar_url": 1}
    ).to_list(200)
    user_by_id = {u["user_id"]: u for u in users}

    rates_docs = await db.exchange_rates.find({"trip_id": trip_id}, {"_id": 0}).to_list(500)
    rates = {(r["from_currency"], r["to_currency"]): r["rate"] for r in rates_docs}

    missing = defaultdict(list)

    def convert(amount, currency, item_id):
        if amount is None:
            return 0.0
        if currency == home:
            return float(amount)
        key = (currency, home)
        if key in rates:
            return float(amount) * rates[key]
        missing[key].append(item_id)
        return None

    balance = defaultdict(float)  # user_id -> home_currency amount (positive = should receive)

    expenses = await db.expenses.find(
        {"trip_id": trip_id}, {"_id": 0, "expense_id": 1, "cost": 1, "currency": 1, "paid_by": 1, "split_between": 1}
    ).to_list(5000)
    for e in expenses:
        amount = convert(e["cost"], e.get("currency") or home, e["expense_id"])
        if amount is None:
            continue
        split = [uid for uid in (e.get("split_between") or []) if uid in user_by_id]
        if not split:
            continue
        share = amount / len(split)
        paid_by = e.get("paid_by")
        if paid_by in user_by_id:
            balance[paid_by] += amount
        for uid in split:
            balance[uid] -= share

    # Round to cents.
    balances_list = []
    for uid in user_ids:
        u = user_by_id.get(uid, {"name": "", "avatar_url": None})
        balances_list.append({
            "user_id": uid,
            "name": u.get("name"),
            "avatar_url": u.get("avatar_url"),
            "balance": round(balance.get(uid, 0.0), 2),
        })

    # Greedy min-cash-flow settlements — use COPIES so `balances_list` stays intact.
    creditors = sorted(
        [dict(b) for b in balances_list if b["balance"] > 0.01],
        key=lambda x: -x["balance"],
    )
    debtors = sorted(
        [dict(b) for b in balances_list if b["balance"] < -0.01],
        key=lambda x: x["balance"],
    )
    settlements = []
    ci = di = 0
    while ci < len(creditors) and di < len(debtors):
        c = creditors[ci]
        d = debtors[di]
        amt = min(c["balance"], -d["balance"])
        amt = round(amt, 2)
        if amt >= 0.01:
            settlements.append({
                "from_user_id": d["user_id"],
                "to_user_id": c["user_id"],
                "amount": amt,
            })
        c["balance"] = round(c["balance"] - amt, 2)
        d["balance"] = round(d["balance"] + amt, 2)
        if c["balance"] <= 0.01:
            ci += 1
        if d["balance"] >= -0.01:
            di += 1

    return {
        "home_currency": home,
        "balances": balances_list,
        "settlements": settlements,
        "missing_rates": [
            {"from": f, "to": t, "affected_items": ids} for (f, t), ids in missing.items()
        ],
    }
