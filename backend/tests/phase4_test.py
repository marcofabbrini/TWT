"""Phase 4 tests — collaborators, invites, roles, sync/version, presence, split expenses, debts."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


def _uniq(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}@twt.app"


def dev_login(email, name=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name or email.split("@")[0]}, timeout=30)
    assert r.status_code == 200, f"dev-login failed {r.status_code} {r.text[:300]}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['session_token']}"})
    return s, data["user"]


def dev_login_as(email, trip_id, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login-as", json={"email": email, "trip_id": trip_id, "role": role}, timeout=30)
    assert r.status_code == 200, f"dev-login-as failed {r.status_code} {r.text[:300]}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['session_token']}"})
    return s, data["user"]


def create_trip(sess, title="TEST_P4 Trip", home="EUR", start="2026-06-01", end="2026-06-10"):
    r = sess.post(f"{API}/trips", json={
        "title": title, "start_date": start, "end_date": end, "home_currency": home,
    }, timeout=30)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    return r.json()


def get_version(sess, trip_id):
    r = sess.get(f"{API}/trips/{trip_id}/version", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()["version"]


def create_stop(sess, trip_id, name="TEST_Stop", start="2026-06-01", end="2026-06-03"):
    r = sess.post(f"{API}/trips/{trip_id}/stops", json={
        "title": name, "location": "Paris, FR", "start_date": start, "end_date": end,
    }, timeout=30)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    return r.json()


@pytest.fixture(scope="module")
def owner():
    return dev_login(_uniq("TEST_owner_"), "TEST Owner")


@pytest.fixture(scope="module")
def owner_trip(owner):
    sess, user = owner
    return create_trip(sess)


# ── /version endpoint ──────────────────────────────────
class TestVersion:
    def test_version_owner(self, owner, owner_trip):
        sess, _ = owner
        r = sess.get(f"{API}/trips/{owner_trip['trip_id']}/version", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d["version"], int)
        assert "last_updated_at" in d and "last_updated_by" in d

    def test_version_viewer_ok(self, owner_trip):
        vsess, _ = dev_login_as(_uniq("TEST_viewer_"), owner_trip["trip_id"], "viewer")
        r = vsess.get(f"{API}/trips/{owner_trip['trip_id']}/version", timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_version_non_member_404(self, owner_trip):
        osess, _ = dev_login(_uniq("TEST_outsider_"))
        r = osess.get(f"{API}/trips/{owner_trip['trip_id']}/version", timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_version_unauth_401(self, owner_trip):
        r = requests.get(f"{API}/trips/{owner_trip['trip_id']}/version", timeout=30)
        assert r.status_code == 401, f"{r.status_code} {r.text[:200]}"


# ── version bumps on every mutation ────────────────────
class TestVersionBumps:
    def test_bumps_on_all_mutations(self, owner):
        sess, user = owner
        trip = create_trip(sess, "TEST_P4 Bumps")
        tid = trip["trip_id"]
        results = {}

        def step(label, fn):
            before = get_version(sess, tid)
            resp = fn()
            after = get_version(sess, tid)
            results[label] = (resp.status_code, before, after)
            assert resp.status_code < 400, f"{label}: {resp.status_code} {resp.text[:250]}"
            assert after > before, f"{label} did not bump version ({before} -> {after})"
            return resp

        # stop create/patch
        r = step("stop.create", lambda: sess.post(f"{API}/trips/{tid}/stops", json={
            "title": "Paris", "location": "Paris, FR", "start_date": "2026-06-01", "end_date": "2026-06-03"}, timeout=30))
        stop_id = r.json()["stop_id"]
        step("stop.patch", lambda: sess.patch(f"{API}/trips/{tid}/stops/{stop_id}", json={"title": "Lyon"}, timeout=30))
        # attraction
        r = step("attraction.create", lambda: sess.post(f"{API}/trips/{tid}/stops/{stop_id}/attractions", json={
            "name": "TEST_Attr", "cost": 10}, timeout=30))
        attr_id = r.json()["attraction_id"]
        step("attraction.patch", lambda: sess.patch(f"{API}/trips/{tid}/attractions/{attr_id}", json={"name": "TEST_Attr2"}, timeout=30))
        step("attraction.delete", lambda: sess.delete(f"{API}/trips/{tid}/attractions/{attr_id}", timeout=30))
        # hotel
        r = step("hotel.create", lambda: sess.post(f"{API}/trips/{tid}/stops/{stop_id}/hotels", json={
            "name": "TEST_Hotel", "cost": 100, "check_in": "2026-06-01", "check_out": "2026-06-02"}, timeout=30))
        hotel_id = r.json()["hotel_id"]
        step("hotel.patch", lambda: sess.patch(f"{API}/trips/{tid}/hotels/{hotel_id}", json={"name": "TEST_Hotel2"}, timeout=30))
        step("hotel.delete", lambda: sess.delete(f"{API}/trips/{tid}/hotels/{hotel_id}", timeout=30))
        # expense
        r = step("expense.create", lambda: sess.post(f"{API}/trips/{tid}/expenses", json={
            "label": "TEST_Exp", "cost": 25}, timeout=30))
        exp_id = r.json()["expense_id"]
        step("expense.patch", lambda: sess.patch(f"{API}/trips/{tid}/expenses/{exp_id}", json={"cost": 30}, timeout=30))
        step("expense.delete", lambda: sess.delete(f"{API}/trips/{tid}/expenses/{exp_id}", timeout=30))
        # exchange rates
        rr = step("rate.put", lambda: sess.put(f"{API}/trips/{tid}/exchange-rates", json={
            "from_currency": "USD", "to_currency": "EUR", "rate": 0.9}, timeout=30))
        rate_id = rr.json()["rate_id"]
        step("rate.delete", lambda: sess.delete(f"{API}/trips/{tid}/exchange-rates/{rate_id}", timeout=30))
        # member mgmt (invite)
        step("invite.create", lambda: sess.post(f"{API}/trips/{tid}/invites", json={
            "email": _uniq("TEST_inv_"), "role": "viewer"}, timeout=30))
        # stop delete last
        step("stop.delete", lambda: sess.delete(f"{API}/trips/{tid}/stops/{stop_id}", timeout=30))

    def test_member_patch_and_delete_bump(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 MemberBump")
        tid = trip["trip_id"]
        esess, euser = dev_login_as(_uniq("TEST_ed_"), tid, "editor")
        members = sess.get(f"{API}/trips/{tid}/members", timeout=30).json()
        mem = next(m for m in members if m["user"] and m["user"]["user_id"] == euser["user_id"])
        v0 = get_version(sess, tid)
        r = sess.patch(f"{API}/trips/{tid}/members/{mem['member_id']}", json={"role": "viewer"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["role"] == "viewer"
        v1 = get_version(sess, tid)
        assert v1 > v0
        r = sess.delete(f"{API}/trips/{tid}/members/{mem['member_id']}", timeout=30)
        assert r.status_code in (200, 204), r.text[:300]
        assert get_version(sess, tid) > v1
        # removed member loses access
        assert esess.get(f"{API}/trips/{tid}", timeout=30).status_code == 404


# ── Invites ────────────────────────────────────────────
class TestInvites:
    def test_invite_lifecycle(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 Invites")
        tid = trip["trip_id"]
        email = _uniq("TEST_invitee_")

        r = sess.post(f"{API}/trips/{tid}/invites", json={"email": email.upper(), "role": "editor"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        d = r.json()
        token = d["invite_token"]
        assert token and token in d["invite_url"]
        assert d["role"] == "editor"
        assert d["invited_email"] == email.lower()
        assert d["expires_at"]

        # public GET (no auth)
        pr = requests.get(f"{API}/invites/{token}", timeout=30)
        assert pr.status_code == 200, pr.text[:300]
        pd = pr.json()
        assert pd["trip_title"] == "TEST_P4 Invites"
        assert pd["invited_email"] == email.lower()
        assert pd["role"] == "editor"
        assert pd["status"] == "pending"
        assert pd["inviter_name"]

        # duplicate invite -> 409
        assert sess.post(f"{API}/trips/{tid}/invites", json={"email": email, "role": "viewer"}, timeout=30).status_code == 409

        # pending member appears in members list
        members = sess.get(f"{API}/trips/{tid}/members", timeout=30).json()
        pend = [m for m in members if m["status"] == "pending"]
        assert len(pend) == 1 and pend[0]["invited_email"] == email.lower()

        # wrong-email accept -> 403
        wsess, _ = dev_login(_uniq("TEST_wrong_"))
        wr = wsess.post(f"{API}/invites/{token}/accept", timeout=30)
        assert wr.status_code == 403, f"{wr.status_code} {wr.text[:200]}"

        # correct accept
        isess, iuser = dev_login(email, "TEST Invitee")
        ar = isess.post(f"{API}/invites/{token}/accept", timeout=30)
        assert ar.status_code == 200, ar.text[:300]
        assert ar.json()["trip_id"] == tid
        assert ar.json()["role"] == "editor"

        # second accept -> 410
        assert isess.post(f"{API}/invites/{token}/accept", timeout=30).status_code == 410
        # public GET after accept -> 404 (token unset)
        assert requests.get(f"{API}/invites/{token}", timeout=30).status_code == 404

        # accepted member now has trip access with editor rights
        assert isess.get(f"{API}/trips/{tid}", timeout=30).status_code == 200
        members = sess.get(f"{API}/trips/{tid}/members", timeout=30).json()
        acc = [m for m in members if m["status"] == "accepted" and m["user"] and m["user"]["user_id"] == iuser["user_id"]]
        assert len(acc) == 1 and acc[0]["role"] == "editor"

    def test_invite_self_400(self, owner, owner_trip):
        sess, user = owner
        r = sess.post(f"{API}/trips/{owner_trip['trip_id']}/invites", json={"email": user["email"], "role": "viewer"}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_invite_bad_role_422(self, owner, owner_trip):
        sess, _ = owner
        r = sess.post(f"{API}/trips/{owner_trip['trip_id']}/invites", json={"email": _uniq("TEST_x_"), "role": "owner"}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_unknown_token_404(self):
        assert requests.get(f"{API}/invites/nope_{uuid.uuid4().hex}", timeout=30).status_code == 404

    def test_decline(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 Decline")
        tid = trip["trip_id"]
        email = _uniq("TEST_decl_")
        token = sess.post(f"{API}/trips/{tid}/invites", json={"email": email, "role": "viewer"}, timeout=30).json()["invite_token"]
        # wrong email decline -> 403
        wsess, _ = dev_login(_uniq("TEST_wrongd_"))
        assert wsess.post(f"{API}/invites/{token}/decline", timeout=30).status_code == 403
        dsess, _ = dev_login(email)
        r = dsess.post(f"{API}/invites/{token}/decline", timeout=30)
        assert r.status_code == 200, r.text[:300]
        members = sess.get(f"{API}/trips/{tid}/members", timeout=30).json()
        assert any(m["status"] == "declined" for m in members)
        # declined -> no access
        assert dsess.get(f"{API}/trips/{tid}", timeout=30).status_code == 404
        # second decline -> 410
        assert dsess.post(f"{API}/invites/{token}/decline", timeout=30).status_code == 410

    def test_status_not_pending_410_on_get(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 Declined410")
        tid = trip["trip_id"]
        email = _uniq("TEST_d410_")
        token = sess.post(f"{API}/trips/{tid}/invites", json={"email": email, "role": "viewer"}, timeout=30).json()["invite_token"]
        # manually flip status via decline but keep token? decline unsets token -> use members patch is n/a.
        # Instead verify pending GET is 200 then after decline token removal yields 404 (documented behaviour).
        assert requests.get(f"{API}/invites/{token}", timeout=30).status_code == 200
        dsess, _ = dev_login(email)
        dsess.post(f"{API}/invites/{token}/decline", timeout=30)
        assert requests.get(f"{API}/invites/{token}", timeout=30).status_code in (404, 410)


# ── Member management permissions ──────────────────────
class TestMemberMgmt:
    def test_patch_owner_role_400(self, owner):
        sess, ouser = owner
        trip = create_trip(sess, "TEST_P4 OwnerRole")
        tid = trip["trip_id"]
        members = sess.get(f"{API}/trips/{tid}/members", timeout=30).json()
        own = next(m for m in members if m["role"] == "owner")
        r = sess.patch(f"{API}/trips/{tid}/members/{own['member_id']}", json={"role": "editor"}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_patch_unknown_member_404(self, owner, owner_trip):
        sess, _ = owner
        r = sess.patch(f"{API}/trips/{owner_trip['trip_id']}/members/mem_nope", json={"role": "editor"}, timeout=30)
        assert r.status_code == 404

    def test_non_owner_cannot_remove_other(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 RemoveOther")
        tid = trip["trip_id"]
        esess, euser = dev_login_as(_uniq("TEST_ed2_"), tid, "editor")
        vsess, vuser = dev_login_as(_uniq("TEST_vw2_"), tid, "viewer")
        members = sess.get(f"{API}/trips/{tid}/members", timeout=30).json()
        vmem = next(m for m in members if m["user"] and m["user"]["user_id"] == vuser["user_id"])
        emem = next(m for m in members if m["user"] and m["user"]["user_id"] == euser["user_id"])
        r = esess.delete(f"{API}/trips/{tid}/members/{vmem['member_id']}", timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"
        # editor removes self -> ok
        r = esess.delete(f"{API}/trips/{tid}/members/{emem['member_id']}", timeout=30)
        assert r.status_code in (200, 204), r.text[:200]
        assert esess.get(f"{API}/trips/{tid}", timeout=30).status_code == 404

    def test_non_owner_cannot_patch_member(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 NoPatch")
        tid = trip["trip_id"]
        esess, _ = dev_login_as(_uniq("TEST_ed3_"), tid, "editor")
        vsess, vuser = dev_login_as(_uniq("TEST_vw3_"), tid, "viewer")
        members = sess.get(f"{API}/trips/{tid}/members", timeout=30).json()
        vmem = next(m for m in members if m["user"] and m["user"]["user_id"] == vuser["user_id"])
        assert esess.patch(f"{API}/trips/{tid}/members/{vmem['member_id']}", json={"role": "editor"}, timeout=30).status_code == 403
        assert vsess.patch(f"{API}/trips/{tid}/members/{vmem['member_id']}", json={"role": "editor"}, timeout=30).status_code == 403


# ── Leave / transfer ownership ─────────────────────────
class TestLeave:
    def test_non_owner_leave(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 Leave")
        tid = trip["trip_id"]
        vsess, _ = dev_login_as(_uniq("TEST_lv_"), tid, "viewer")
        r = vsess.post(f"{API}/trips/{tid}/leave", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert vsess.get(f"{API}/trips/{tid}", timeout=30).status_code == 404
        # second leave -> 404
        assert vsess.post(f"{API}/trips/{tid}/leave", timeout=30).status_code == 404

    def test_owner_leave_promotes_first_editor(self, owner):
        sess, ouser = owner
        trip = create_trip(sess, "TEST_P4 Transfer")
        tid = trip["trip_id"]
        e1s, e1 = dev_login_as(_uniq("TEST_e1_"), tid, "editor")
        e2s, e2 = dev_login_as(_uniq("TEST_e2_"), tid, "editor")
        r = sess.post(f"{API}/trips/{tid}/leave", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["outcome"] == "transferred"
        # e1 (oldest editor) is now owner: can do owner-only ops
        tr = e1s.get(f"{API}/trips/{tid}", timeout=30)
        assert tr.status_code == 200, tr.text[:200]
        assert tr.json()["owner_id"] == e1["user_id"], "trips.owner_id not updated to promoted editor"
        members = e1s.get(f"{API}/trips/{tid}/members", timeout=30).json()
        me = next(m for m in members if m["user"] and m["user"]["user_id"] == e1["user_id"])
        assert me["role"] == "owner", "trip_members.role not promoted to owner"
        # owner-only action works for new owner
        assert e1s.post(f"{API}/trips/{tid}/invites", json={"email": _uniq("TEST_ni_"), "role": "viewer"}, timeout=30).status_code in (200, 201)
        # old owner lost access
        assert sess.get(f"{API}/trips/{tid}", timeout=30).status_code == 404

    def test_owner_leave_no_editors_deletes_trip(self, owner):
        sess, _ = owner
        trip = create_trip(sess, "TEST_P4 AutoDelete")
        tid = trip["trip_id"]
        stop = create_stop(sess, tid)
        sess.post(f"{API}/trips/{tid}/stops/{stop['stop_id']}/attractions", json={"name": "TEST_A", "cost": 5}, timeout=30)
        sess.post(f"{API}/trips/{tid}/stops/{stop['stop_id']}/hotels", json={"name": "TEST_H", "cost": 50, "check_in": "2026-06-01", "check_out": "2026-06-02"}, timeout=30)
        sess.post(f"{API}/trips/{tid}/expenses", json={"label": "TEST_E", "cost": 5}, timeout=30)
        sess.put(f"{API}/trips/{tid}/exchange-rates", json={"from_currency": "USD", "to_currency": "EUR", "rate": 0.9}, timeout=30)
        sess.post(f"{API}/trips/{tid}/presence", json={"editing": None}, timeout=30)
        vsess, _ = dev_login_as(_uniq("TEST_vwd_"), tid, "viewer")
        r = sess.post(f"{API}/trips/{tid}/leave", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["outcome"] == "deleted"
        assert sess.get(f"{API}/trips/{tid}", timeout=30).status_code == 404
        assert vsess.get(f"{API}/trips/{tid}", timeout=30).status_code == 404
        # cascade verified in Mongo
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import dotenv_values as dv
        env = dv("/app/backend/.env")

        async def counts():
            cl = AsyncIOMotorClient(env["MONGO_URL"])
            d = cl[env["DB_NAME"]]
            out = {}
            for coll in ["trips", "stops", "attractions", "hotels", "expenses", "exchange_rates", "trip_members", "trip_presence"]:
                key = "trip_id"
                out[coll] = await d[coll].count_documents({key: tid})
            cl.close()
            return out

        res = asyncio.get_event_loop().run_until_complete(counts()) if False else asyncio.run(counts())
        assert all(v == 0 for v in res.values()), f"cascade delete left orphans: {res}"


# ── Presence ───────────────────────────────────────────
class TestPresence:
    def test_presence_post_get(self, owner):
        sess, ouser = owner
        trip = create_trip(sess, "TEST_P4 Presence")
        tid = trip["trip_id"]
        vsess, vuser = dev_login_as(_uniq("TEST_pv_"), tid, "viewer")
        assert vsess.post(f"{API}/trips/{tid}/presence", json={"editing": "stop_1"}, timeout=30).status_code == 200
        assert sess.post(f"{API}/trips/{tid}/presence", json={}, timeout=30).status_code == 200
        r = sess.get(f"{API}/trips/{tid}/presence", timeout=30)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        ids = {row["user_id"] for row in rows}
        assert vuser["user_id"] in ids and ouser["user_id"] in ids
        row = next(x for x in rows if x["user_id"] == vuser["user_id"])
        assert row["editing"] == "stop_1"
        assert row["name"] and "avatar_url" in row and row["last_seen_at"]
        # upsert (no duplicates)
        vsess.post(f"{API}/trips/{tid}/presence", json={"editing": None}, timeout=30)
        rows2 = sess.get(f"{API}/trips/{tid}/presence", timeout=30).json()
        assert len([x for x in rows2 if x["user_id"] == vuser["user_id"]]) == 1

    def test_presence_stale_excluded(self, owner):
        sess, ouser = owner
        trip = create_trip(sess, "TEST_P4 PresenceStale")
        tid = trip["trip_id"]
        sess.post(f"{API}/trips/{tid}/presence", json={}, timeout=30)
        import asyncio
        from datetime import datetime, timedelta, timezone
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import dotenv_values as dv
        env = dv("/app/backend/.env")

        async def age():
            cl = AsyncIOMotorClient(env["MONGO_URL"])
            d = cl[env["DB_NAME"]]
            await d.trip_presence.update_one(
                {"trip_id": tid, "user_id": ouser["user_id"]},
                {"$set": {"last_seen_at": datetime.now(timezone.utc) - timedelta(seconds=120)}},
            )
            cl.close()

        asyncio.run(age())
        rows = sess.get(f"{API}/trips/{tid}/presence", timeout=30).json()
        assert all(r["user_id"] != ouser["user_id"] for r in rows), "stale presence row (>30s) was returned"

    def test_presence_non_member_404(self, owner, owner_trip):
        osess, _ = dev_login(_uniq("TEST_pout_"))
        assert osess.get(f"{API}/trips/{owner_trip['trip_id']}/presence", timeout=30).status_code == 404
        assert osess.post(f"{API}/trips/{owner_trip['trip_id']}/presence", json={}, timeout=30).status_code == 404


# ── Role permissions matrix ────────────────────────────
class TestRolePermissions:
    @pytest.fixture(scope="class")
    def ctx(self):
        osess, ouser = dev_login(_uniq("TEST_rp_owner_"), "TEST RP Owner")
        trip = create_trip(osess, "TEST_P4 Roles")
        tid = trip["trip_id"]
        stop = create_stop(osess, tid)
        esess, euser = dev_login_as(_uniq("TEST_rp_ed_"), tid, "editor")
        vsess, vuser = dev_login_as(_uniq("TEST_rp_vw_"), tid, "viewer")
        return {"osess": osess, "ouser": ouser, "esess": esess, "euser": euser,
                "vsess": vsess, "vuser": vuser, "tid": tid, "stop_id": stop["stop_id"]}

    def test_editor_crud_allowed(self, ctx):
        s, tid, stop_id = ctx["esess"], ctx["tid"], ctx["stop_id"]
        r = s.post(f"{API}/trips/{tid}/stops", json={"title": "Nice", "location": "Nice, FR",
                                                    "start_date": "2026-06-04", "end_date": "2026-06-05"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:250]
        s2 = r.json()["stop_id"]
        assert s.patch(f"{API}/trips/{tid}/stops/{s2}", json={"title": "Cannes"}, timeout=30).status_code == 200
        ra = s.post(f"{API}/trips/{tid}/stops/{stop_id}/attractions", json={"name": "TEST_EA", "cost": 3}, timeout=30)
        assert ra.status_code in (200, 201), ra.text[:250]
        assert s.patch(f"{API}/trips/{tid}/attractions/{ra.json()['attraction_id']}", json={"cost": 4}, timeout=30).status_code == 200
        assert s.delete(f"{API}/trips/{tid}/attractions/{ra.json()['attraction_id']}", timeout=30).status_code in (200, 204)
        rh = s.post(f"{API}/trips/{tid}/stops/{stop_id}/hotels", json={"name": "TEST_EH", "cost": 30, "check_in": "2026-06-01", "check_out": "2026-06-02"}, timeout=30)
        assert rh.status_code in (200, 201), rh.text[:250]
        assert s.delete(f"{API}/trips/{tid}/hotels/{rh.json()['hotel_id']}", timeout=30).status_code in (200, 204)
        re_ = s.post(f"{API}/trips/{tid}/expenses", json={"label": "TEST_EE", "cost": 9}, timeout=30)
        assert re_.status_code in (200, 201), re_.text[:250]
        assert s.patch(f"{API}/trips/{tid}/expenses/{re_.json()['expense_id']}", json={"cost": 11}, timeout=30).status_code == 200
        assert s.delete(f"{API}/trips/{tid}/expenses/{re_.json()['expense_id']}", timeout=30).status_code in (200, 204)
        assert s.delete(f"{API}/trips/{tid}/stops/{s2}", timeout=30).status_code in (200, 204)

    def test_editor_denied_owner_actions(self, ctx):
        s, tid = ctx["esess"], ctx["tid"]
        assert s.put(f"{API}/trips/{tid}/exchange-rates", json={"from_currency": "USD", "to_currency": "EUR", "rate": 1.0}, timeout=30).status_code == 403
        assert s.delete(f"{API}/trips/{tid}/exchange-rates/rate_dummy", timeout=30).status_code == 403
        assert s.post(f"{API}/trips/{tid}/invites", json={"email": _uniq("TEST_ei_"), "role": "viewer"}, timeout=30).status_code == 403
        assert s.delete(f"{API}/trips/{tid}", timeout=30).status_code == 403

    def test_viewer_reads_ok(self, ctx):
        s, tid, stop_id = ctx["vsess"], ctx["tid"], ctx["stop_id"]
        for path in [f"/trips/{tid}", f"/trips/{tid}/stops", f"/trips/{tid}/expenses",
                     f"/trips/{tid}/exchange-rates", f"/trips/{tid}/members",
                     f"/trips/{tid}/version", f"/trips/{tid}/presence", f"/trips/{tid}/debts",
                     f"/trips/{tid}/summary", f"/trips/{tid}/stops/{stop_id}/attractions", f"/trips/{tid}/stops/{stop_id}/hotels"]:
            r = s.get(f"{API}{path}", timeout=30)
            assert r.status_code == 200, f"GET {path} -> {r.status_code} {r.text[:200]}"

    def test_viewer_denied_all_mutations(self, ctx):
        s, tid, stop_id = ctx["vsess"], ctx["tid"], ctx["stop_id"]
        checks = [
            ("POST", f"/trips/{tid}/stops", {"title": "X", "location": "X, FR", "start_date": "2026-06-02", "end_date": "2026-06-03"}),
            ("PATCH", f"/trips/{tid}/stops/{stop_id}", {"title": "Y"}),
            ("DELETE", f"/trips/{tid}/stops/{stop_id}", None),
            ("POST", f"/trips/{tid}/stops/{stop_id}/attractions", {"name": "TEST_VA", "cost": 1}),
            ("POST", f"/trips/{tid}/stops/{stop_id}/hotels", {"name": "TEST_VH", "cost": 1, "check_in": "2026-06-01", "check_out": "2026-06-02"}),
            ("POST", f"/trips/{tid}/expenses", {"label": "TEST_VE", "cost": 1}),
            ("PUT", f"/trips/{tid}/exchange-rates", {"from_currency": "USD", "to_currency": "EUR", "rate": 1.0}),
            ("POST", f"/trips/{tid}/invites", {"email": _uniq("TEST_vi_"), "role": "viewer"}),
            ("DELETE", f"/trips/{tid}", None),
        ]
        failures = []
        for method, path, body in checks:
            r = s.request(method, f"{API}{path}", json=body, timeout=30)
            if r.status_code != 403:
                failures.append(f"{method} {path} -> {r.status_code} {r.text[:120]}")
        assert not failures, f"viewer mutations not blocked: {failures}"


# ── Split validation + debts ───────────────────────────
class TestSplitAndDebts:
    @pytest.fixture(scope="class")
    def ctx(self):
        asess, alice = dev_login(_uniq("TEST_alice_"), "TEST Alice")
        trip = create_trip(asess, "TEST_P4 Debts", home="EUR")
        tid = trip["trip_id"]
        bsess, bob = dev_login_as(_uniq("TEST_bob_"), tid, "editor")
        return {"asess": asess, "alice": alice, "bsess": bsess, "bob": bob, "tid": tid}

    def test_split_non_member_422(self, ctx):
        s, tid = ctx["asess"], ctx["tid"]
        r = s.post(f"{API}/trips/{tid}/expenses", json={
            "label": "TEST_BadSplit", "cost": 10,
            "split_between": [ctx["alice"]["user_id"], "usr_doesnotexist"]}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:250]}"
        assert "non-member user_ids" in str(r.json()), r.text[:250]

    def test_paid_by_non_member_422(self, ctx):
        s, tid = ctx["asess"], ctx["tid"]
        r = s.post(f"{API}/trips/{tid}/expenses", json={
            "label": "TEST_BadPaidBy", "cost": 10, "paid_by": "usr_nope"}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:250]}"

    def test_patch_split_non_member_422(self, ctx):
        s, tid = ctx["asess"], ctx["tid"]
        r = s.post(f"{API}/trips/{tid}/expenses", json={"label": "TEST_PatchSplit", "cost": 10}, timeout=30)
        eid = r.json()["expense_id"]
        pr = s.patch(f"{API}/trips/{tid}/expenses/{eid}", json={"split_between": ["usr_nope2"]}, timeout=30)
        assert pr.status_code == 422, f"{pr.status_code} {pr.text[:250]}"
        s.delete(f"{API}/trips/{tid}/expenses/{eid}", timeout=30)

    def test_debts_scenario(self, ctx):
        s, tid = ctx["asess"], ctx["tid"]
        a, b = ctx["alice"]["user_id"], ctx["bob"]["user_id"]
        # alice pays 100 EUR split 50/50
        r = s.post(f"{API}/trips/{tid}/expenses", json={
            "label": "TEST_D1", "cost": 100, "currency": "EUR", "paid_by": a, "split_between": [a, b]}, timeout=30)
        assert r.status_code in (200, 201), r.text[:250]
        e1 = r.json()["expense_id"]
        d = s.get(f"{API}/trips/{tid}/debts", timeout=30).json()
        assert d["home_currency"] == "EUR"
        bal = {x["user_id"]: x["balance"] for x in d["balances"]}
        assert bal[a] == 50.0 and bal[b] == -50.0, bal
        assert d["settlements"] == [{"from_user_id": b, "to_user_id": a, "amount": 50.0}], d["settlements"]
        assert d["missing_rates"] == []

        # bob pays 60 EUR split 50/50
        r2 = s.post(f"{API}/trips/{tid}/expenses", json={
            "label": "TEST_D2", "cost": 60, "currency": "EUR", "paid_by": b, "split_between": [a, b]}, timeout=30)
        e2 = r2.json()["expense_id"]
        d = s.get(f"{API}/trips/{tid}/debts", timeout=30).json()
        bal = {x["user_id"]: x["balance"] for x in d["balances"]}
        assert bal[a] == 20.0 and bal[b] == -20.0, bal
        assert d["settlements"] == [{"from_user_id": b, "to_user_id": a, "amount": 20.0}], d["settlements"]

        # cleanup
        s.delete(f"{API}/trips/{tid}/expenses/{e1}", timeout=30)
        s.delete(f"{API}/trips/{tid}/expenses/{e2}", timeout=30)

    def test_debts_missing_rate(self, ctx):
        s, tid = ctx["asess"], ctx["tid"]
        a, b = ctx["alice"]["user_id"], ctx["bob"]["user_id"]
        r = s.post(f"{API}/trips/{tid}/expenses", json={
            "label": "TEST_USD", "cost": 80, "currency": "USD", "paid_by": a, "split_between": [a, b]}, timeout=30)
        eid = r.json()["expense_id"]
        d = s.get(f"{API}/trips/{tid}/debts", timeout=30).json()
        assert d["missing_rates"], "USD expense with no USD->EUR rate not reported in missing_rates"
        mr = d["missing_rates"][0]
        assert mr["from"] == "USD" and mr["to"] == "EUR"
        bal = {x["user_id"]: x["balance"] for x in d["balances"]}
        assert bal[a] == 0.0 and bal[b] == 0.0, f"expense with missing rate leaked into balances: {bal}"
        assert d["settlements"] == []
        # add rate -> now included
        s.put(f"{API}/trips/{tid}/exchange-rates", json={"from_currency": "USD", "to_currency": "EUR", "rate": 0.5}, timeout=30)
        d = s.get(f"{API}/trips/{tid}/debts", timeout=30).json()
        assert d["missing_rates"] == []
        bal = {x["user_id"]: x["balance"] for x in d["balances"]}
        assert bal[a] == 20.0 and bal[b] == -20.0, bal
        s.delete(f"{API}/trips/{tid}/expenses/{eid}", timeout=30)
        pass

    def test_debts_non_member_404(self, ctx):
        osess, _ = dev_login(_uniq("TEST_dout_"))
        assert osess.get(f"{API}/trips/{ctx['tid']}/debts", timeout=30).status_code == 404


# ── dev-login-as ───────────────────────────────────────
class TestDevLoginAs:
    def test_success_and_role(self, owner, owner_trip):
        email = _uniq("TEST_dla_")
        r = requests.post(f"{API}/auth/dev-login-as", json={"email": email, "trip_id": owner_trip["trip_id"], "role": "viewer"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["user"]["email"].lower() == email.lower()
        assert d["session_token"] and d["trip_id"] == owner_trip["trip_id"] and d["role"] == "viewer"
        assert "twt_session" in r.cookies or any("twt_session" in v for v in r.headers.get("set-cookie", "").split(","))
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {d['session_token']}"})
        assert s.get(f"{API}/trips/{owner_trip['trip_id']}", timeout=30).status_code == 200

    def test_invalid_role_422(self, owner_trip):
        r = requests.post(f"{API}/auth/dev-login-as", json={"email": _uniq("TEST_dlb_"), "trip_id": owner_trip["trip_id"], "role": "boss"}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_unknown_trip_404(self):
        r = requests.post(f"{API}/auth/dev-login-as", json={"email": _uniq("TEST_dlc_"), "trip_id": "trip_nope", "role": "editor"}, timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"


# ── OpenAPI ────────────────────────────────────────────
class TestOpenAPI:
    def test_phase4_paths_present(self):
        r = requests.get(f"{API}/openapi.json", timeout=30)
        assert r.status_code == 200
        paths = r.json()["paths"]
        for p in ["/api/trips/{trip_id}/version", "/api/trips/{trip_id}/invites",
                  "/api/trips/{trip_id}/members", "/api/trips/{trip_id}/members/{member_id}",
                  "/api/trips/{trip_id}/leave", "/api/trips/{trip_id}/presence",
                  "/api/trips/{trip_id}/debts", "/api/invites/{invite_token}",
                  "/api/invites/{invite_token}/accept", "/api/invites/{invite_token}/decline",
                  "/api/auth/dev-login-as"]:
            assert p in paths, f"missing OpenAPI path {p}"
