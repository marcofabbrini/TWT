import requests, json, time, uuid
API = "https://voyage-setup-1.preview.emergentagent.com/api"

def dev_login(email, name=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name or email.split("@")[0].title()})
    assert r.status_code == 200, f"dev-login: {r.status_code} {r.text}"
    return s, r.json()["user"]

def dev_login_as(email, trip_id, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login-as", json={"email": email, "trip_id": trip_id, "role": role})
    assert r.status_code == 200, f"dev-login-as: {r.status_code} {r.text}"
    return s, r.json()

RESULTS = {}
def rr(name, ok, evidence=""):
    tag = "[PASS]" if ok else "[FAIL]"
    RESULTS[name]=ok
    print(f"{tag} {name}: {str(evidence)[:400]}")
    return ok

# === TEST 1 ===
print("\n=== TEST 1: Invite flow ===")
alice, alice_u = dev_login("alice@twt.app","Alice")
bob, bob_u = dev_login("bob@twt.app","Bob")
carol, carol_u = dev_login("carol@twt.app","Carol")
alice_uid = alice_u["user_id"]
bob_uid = bob_u["user_id"]
carol_uid = carol_u["user_id"]
print("uids:", alice_uid, bob_uid, carol_uid)

r = alice.post(f"{API}/trips", json={"title":"Invite Test","home_currency":"EUR","start_date":"2025-01-01","end_date":"2025-01-10"})
trip1 = r.json(); trip1_id = trip1["trip_id"]

r = alice.post(f"{API}/trips/{trip1_id}/invites", json={"email":"bob@twt.app","role":"editor"})
inv = r.json()
token = inv.get("invite_token")
rr("1a_invite_has_token_and_url", "invite_token" in inv and "invite_url" in inv, list(inv.keys()))

r = bob.get(f"{API}/invites/{token}")
inv_get = r.json() if r.status_code==200 else {}
rr("1b_invite_get_public", r.status_code==200 and inv_get.get("role")=="editor" and inv_get.get("status")=="pending" and "trip_title" in inv_get and "inviter_name" in inv_get, inv_get)

r = bob.post(f"{API}/invites/{token}/accept")
rr("1c_bob_accept_200", r.status_code==200, f"{r.status_code} {r.text[:200]}")

r = bob.get(f"{API}/trips")
trips_bob = r.json()
rr("1d_bob_sees_trip", any(t["trip_id"]==trip1_id for t in trips_bob), f"count={len(trips_bob)}")

r = alice.get(f"{API}/trips/{trip1_id}/members")
members = r.json()
print("members1:", members)
bob_mem = next((m for m in members if m.get("user_id")==bob_uid), None)
rr("1e_bob_editor_accepted", bob_mem and bob_mem.get("role")=="editor" and bob_mem.get("status")=="accepted", bob_mem)

# === TEST 2: email mismatch ===
print("\n=== TEST 2 ===")
r = alice.post(f"{API}/trips/{trip1_id}/invites", json={"email":"carol@twt.app","role":"viewer"})
ctoken = r.json().get("invite_token")
r = bob.post(f"{API}/invites/{ctoken}/accept")
rr("2_mismatch_403", r.status_code==403, f"{r.status_code} {r.text[:200]}")

# === TEST 3: permissions ===
print("\n=== TEST 3: permissions ===")
r = alice.post(f"{API}/trips", json={"title":"Perm Test","home_currency":"EUR","start_date":"2025-02-01","end_date":"2025-02-10"})
trip3 = r.json(); trip3_id = trip3["trip_id"]
bob, _ = dev_login_as("bob@twt.app", trip3_id, "editor")
carol, _ = dev_login_as("carol@twt.app", trip3_id, "viewer")

r = alice.get(f"{API}/trips/{trip3_id}/members")
members3 = r.json()
print("members3:", members3)
alice_mem = next(m for m in members3 if m.get("role")=="owner")
alice_mem_id = alice_mem.get("member_id") or alice_mem.get("id")

# Bob (editor)
r = bob.put(f"{API}/trips/{trip3_id}/exchange-rates", json={"from_currency":"USD","to_currency":"EUR","rate":0.9})
rr("3a_editor_xr_403", r.status_code==403, f"{r.status_code} {r.text[:200]}")

r = bob.patch(f"{API}/trips/{trip3_id}/members/{alice_mem_id}", json={"role":"viewer"})
rr("3b_editor_patch_member_403", r.status_code==403, f"{r.status_code} {r.text[:200]}")

r = bob.delete(f"{API}/trips/{trip3_id}")
rr("3c_editor_delete_trip_403", r.status_code==403, f"{r.status_code} {r.text[:200]}")

r = bob.post(f"{API}/trips/{trip3_id}/stops", json={"title":"S1","location":"Rome","start_date":"2025-02-02","end_date":"2025-02-03"})
rr("3d_editor_create_stop", r.status_code in (200,201), f"{r.status_code} {r.text[:200]}")
stop_id = r.json().get("stop_id") if r.ok else None

attr_id = None
if stop_id:
    r = bob.post(f"{API}/trips/{trip3_id}/stops/{stop_id}/attractions", json={"name":"Colosseum"})
    rr("3e_editor_create_attr", r.status_code in (200,201), f"{r.status_code} {r.text[:200]}")
    attr_id = r.json().get("attraction_id") if r.ok else None

# Carol (viewer)
r = carol.post(f"{API}/trips/{trip3_id}/stops", json={"title":"X","location":"Y","start_date":"2025-02-04","end_date":"2025-02-05"})
rr("3f_viewer_stop_403", r.status_code==403, f"{r.status_code} {r.text[:200]}")

if stop_id:
    r = carol.patch(f"{API}/trips/{trip3_id}/stops/{stop_id}", json={"title":"newT"})
    rr("3g_viewer_patch_403", r.status_code==403, f"{r.status_code} {r.text[:200]}")

r = carol.get(f"{API}/trips/{trip3_id}")
rr("3h_viewer_get_ok", r.status_code==200, f"{r.status_code}")

# Non-member
stranger, _ = dev_login("dave@twt.app","Dave")
r = stranger.get(f"{API}/trips/{trip3_id}")
rr("3i_stranger_get_404", r.status_code==404, f"{r.status_code} {r.text[:200]}")
r = stranger.post(f"{API}/trips/{trip3_id}/stops", json={"title":"x","location":"y","start_date":"2025-02-02","end_date":"2025-02-03"})
rr("3j_stranger_post_404", r.status_code==404, f"{r.status_code}")

# === TEST 4: transfer ownership ===
print("\n=== TEST 4: transfer ownership ===")
r = alice.post(f"{API}/trips", json={"title":"Transfer Test","home_currency":"EUR","start_date":"2025-03-01","end_date":"2025-03-10"})
trip4_id = r.json()["trip_id"]
bob4, _ = dev_login_as("bob@twt.app", trip4_id, "editor")
time.sleep(0.5)
carol4, _ = dev_login_as("carol@twt.app", trip4_id, "editor")

r = alice.get(f"{API}/trips/{trip4_id}/members")
members4 = r.json()
alice_mem4 = next(m for m in members4 if m.get("user_id")==alice_uid)
alice_mem4_id = alice_mem4.get("member_id") or alice_mem4.get("id")

# Alice leaves
r = alice.post(f"{API}/trips/{trip4_id}/leave")
rr("4a_alice_leaves_ok", r.status_code in (200,204), f"{r.status_code} {r.text[:200]}")

# Trip still exists
r = bob4.get(f"{API}/trips/{trip4_id}")
rr("4b_trip_still_exists", r.status_code==200, f"{r.status_code}")
trip4_now = r.json() if r.status_code==200 else {}
rr("4c_owner_transferred_to_bob", trip4_now.get("owner_id")==bob_uid, f"owner_id={trip4_now.get('owner_id')} bob={bob_uid}")

r = bob4.get(f"{API}/trips/{trip4_id}/members")
members4_after = r.json()
bob_after = next((m for m in members4_after if m.get("user_id")==bob_uid),None)
carol_after = next((m for m in members4_after if m.get("user_id")==carol_uid),None)
alice_gone = not any(m.get("user_id")==alice_uid for m in members4_after)
rr("4d_bob_now_owner", bob_after and bob_after.get("role")=="owner", bob_after)
rr("4e_carol_still_editor", carol_after and carol_after.get("role")=="editor", carol_after)
rr("4f_alice_removed", alice_gone, [m.get("role")+"/"+m.get("user_id","") for m in members4_after])

# === TEST 5: cascade delete no editor ===
print("\n=== TEST 5: cascade delete when no editor ===")
alice, _ = dev_login("alice@twt.app","Alice")
r = alice.post(f"{API}/trips", json={"title":"Solo Owner","home_currency":"EUR","start_date":"2025-04-01","end_date":"2025-04-10"})
trip5a_id = r.json()["trip_id"]
r = alice.post(f"{API}/trips/{trip5a_id}/leave")
rr("5a_solo_leave_ok", r.status_code in (200,204), f"{r.status_code} {r.text[:200]}")
r = alice.get(f"{API}/trips/{trip5a_id}")
rr("5b_solo_trip_deleted", r.status_code==404, f"{r.status_code}")

# alice + bob viewer only
r = alice.post(f"{API}/trips", json={"title":"Only Viewer","home_currency":"EUR","start_date":"2025-04-15","end_date":"2025-04-20"})
trip5b_id = r.json()["trip_id"]
bob5, _ = dev_login_as("bob@twt.app", trip5b_id, "viewer")
r = alice.post(f"{API}/trips/{trip5b_id}/leave")
rr("5c_viewer_only_leave_ok", r.status_code in (200,204), f"{r.status_code} {r.text[:200]}")
r = bob5.get(f"{API}/trips/{trip5b_id}")
rr("5d_viewer_only_trip_deleted", r.status_code==404, f"{r.status_code} {r.text[:200]}")

# save state
STATE=dict(trip3_id=trip3_id, alice_uid=alice_uid, bob_uid=bob_uid, carol_uid=carol_uid,
           stop_id=stop_id, attr_id=attr_id, alice_mem_id=alice_mem_id, trip1_id=trip1_id)
with open("/app/test_reports/state.json","w") as f: json.dump(STATE,f)

# save cookies
def cksave(sess, path):
    with open(path,"w") as f: json.dump(dict(sess.cookies), f)
cksave(alice, "/app/test_reports/alice.json")
cksave(bob, "/app/test_reports/bob.json")
cksave(carol, "/app/test_reports/carol.json")

print("\n=== T1-T5 Summary ===")
for k,v in RESULTS.items(): print(f"  {'PASS' if v else 'FAIL'}: {k}")
print(f"Total: {sum(RESULTS.values())}/{len(RESULTS)} passed")
