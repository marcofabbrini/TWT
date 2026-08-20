import requests, json, time
API = "https://voyage-setup-1.preview.emergentagent.com/api"

def dev_login(email, name=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": name or email.split("@")[0].title()})
    return s, r.json()["user"]

def dev_login_as(email, trip_id, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login-as", json={"email": email, "trip_id": trip_id, "role": role})
    assert r.status_code == 200, r.text
    return s, r.json()

def uid_of(m): return m.get("user",{}).get("user_id")

RESULTS = {}
def rr(name, ok, evidence=""):
    tag = "[PASS]" if ok else "[FAIL]"
    RESULTS[name]=ok
    print(f"{tag} {name}: {str(evidence)[:400]}")

alice, alice_u = dev_login("alice@twt.app","Alice")
bob, bob_u = dev_login("bob@twt.app","Bob")
carol, carol_u = dev_login("carol@twt.app","Carol")
alice_uid = alice_u["user_id"]; bob_uid = bob_u["user_id"]; carol_uid = carol_u["user_id"]

# === TEST 4: transfer ownership ===
print("\n=== TEST 4: transfer ownership ===")
r = alice.post(f"{API}/trips", json={"title":"Transfer Test","home_currency":"EUR","start_date":"2025-03-01","end_date":"2025-03-10"})
trip4_id = r.json()["trip_id"]
bob4, _ = dev_login_as("bob@twt.app", trip4_id, "editor")
time.sleep(1.0)
carol4, _ = dev_login_as("carol@twt.app", trip4_id, "editor")

r = alice.post(f"{API}/trips/{trip4_id}/leave")
rr("4a_alice_leaves_ok", r.status_code in (200,204), f"{r.status_code} {r.text[:200]}")

r = bob4.get(f"{API}/trips/{trip4_id}")
rr("4b_trip_still_exists", r.status_code==200, f"{r.status_code}")
trip4_now = r.json() if r.status_code==200 else {}
rr("4c_owner_transferred_to_bob", trip4_now.get("owner_id")==bob_uid, f"owner_id={trip4_now.get('owner_id')} bob={bob_uid}")

r = bob4.get(f"{API}/trips/{trip4_id}/members")
members4 = r.json()
bob_m = next((m for m in members4 if uid_of(m)==bob_uid),None)
carol_m = next((m for m in members4 if uid_of(m)==carol_uid),None)
alice_gone = not any(uid_of(m)==alice_uid for m in members4)
rr("4d_bob_now_owner", bob_m and bob_m.get("role")=="owner", bob_m)
rr("4e_carol_still_editor", carol_m and carol_m.get("role")=="editor", carol_m)
rr("4f_alice_removed", alice_gone, [f"{m.get('role')}/{uid_of(m)}" for m in members4])

# === TEST 5: cascade delete ===
print("\n=== TEST 5 ===")
alice2, _ = dev_login("alice@twt.app","Alice")
r = alice2.post(f"{API}/trips", json={"title":"Solo Owner","home_currency":"EUR","start_date":"2025-04-01","end_date":"2025-04-10"})
trip5a_id = r.json()["trip_id"]
r = alice2.post(f"{API}/trips/{trip5a_id}/leave")
rr("5a_solo_leave_ok", r.status_code in (200,204), f"{r.status_code} {r.text[:200]}")
r = alice2.get(f"{API}/trips/{trip5a_id}")
rr("5b_solo_trip_deleted", r.status_code==404, f"{r.status_code}")

r = alice2.post(f"{API}/trips", json={"title":"Only Viewer","home_currency":"EUR","start_date":"2025-04-15","end_date":"2025-04-20"})
trip5b_id = r.json()["trip_id"]
bob5, _ = dev_login_as("bob@twt.app", trip5b_id, "viewer")
r = alice2.post(f"{API}/trips/{trip5b_id}/leave")
rr("5c_viewer_only_leave_ok", r.status_code in (200,204), f"{r.status_code} {r.text[:200]}")
r = bob5.get(f"{API}/trips/{trip5b_id}")
rr("5d_viewer_only_trip_deleted", r.status_code==404, f"{r.status_code} {r.text[:200]}")

# === TEST 3 setup for tests 6-10 ===
print("\n=== Rebuild trip3 for tests 6-10 ===")
alice, _ = dev_login("alice@twt.app","Alice")
r = alice.post(f"{API}/trips", json={"title":"Perm Test 6","home_currency":"EUR","start_date":"2025-05-01","end_date":"2025-05-10"})
trip3_id = r.json()["trip_id"]
bob, _ = dev_login_as("bob@twt.app", trip3_id, "editor")
carol, _ = dev_login_as("carol@twt.app", trip3_id, "viewer")

r = alice.post(f"{API}/trips/{trip3_id}/stops", json={"title":"S1","location":"Rome","start_date":"2025-05-02","end_date":"2025-05-03"})
stop_id = r.json()["stop_id"]
r = alice.post(f"{API}/trips/{trip3_id}/stops/{stop_id}/attractions", json={"name":"Colosseum","cost":50,"currency":"EUR"})
attr_id = r.json()["attraction_id"]

# === TEST 6: expenses & debts ===
print("\n=== TEST 6: expenses/debts ===")
# Expense 1: Alice paid 300, split A/B/C
r = alice.post(f"{API}/trips/{trip3_id}/expenses", json={
    "label":"E1","cost":300,"currency":"EUR","paid_by":alice_uid,
    "split_between":[alice_uid,bob_uid,carol_uid]})
print("e1:", r.status_code, r.text[:200])
rr("6a_expense1_created", r.status_code in (200,201), r.status_code)

# Expense 2: Bob paid 150, split A/B
r = bob.post(f"{API}/trips/{trip3_id}/expenses", json={
    "label":"E2","cost":150,"currency":"EUR","paid_by":bob_uid,
    "split_between":[alice_uid,bob_uid]})
print("e2:", r.status_code, r.text[:200])
rr("6b_expense2_created", r.status_code in (200,201), r.status_code)

# Expense 3: Carol paid 90, split B/C. Carol is viewer -> should be 403
r = carol.post(f"{API}/trips/{trip3_id}/expenses", json={
    "label":"E3","cost":90,"currency":"EUR","paid_by":carol_uid,
    "split_between":[bob_uid,carol_uid]})
print("e3 (carol viewer):", r.status_code, r.text[:200])
# create as alice instead but paid_by=carol
r = alice.post(f"{API}/trips/{trip3_id}/expenses", json={
    "label":"E3","cost":90,"currency":"EUR","paid_by":carol_uid,
    "split_between":[bob_uid,carol_uid]})
print("e3 (alice for carol):", r.status_code, r.text[:200])
rr("6c_expense3_created", r.status_code in (200,201), r.status_code)

# GET debts
r = alice.get(f"{API}/trips/{trip3_id}/debts")
print("debts:", r.status_code, r.text[:800])
debts = r.json() if r.status_code==200 else {}
rr("6d_debts_endpoint_ok", r.status_code==200, r.status_code)

# Parse balances
# Expected:
# Alice: paid 300, owes 100+75+0=175, balance = +125
# Bob: paid 150, owes 100+75+45=220, balance = -70
# Carol: paid 90, owes 100+0+45=145, balance = -55
# Sum = 0
bal = debts.get("balances") or debts.get("net") or {}
if isinstance(bal, list):
    balmap = {b.get("user_id"): b.get("balance") or b.get("net") for b in bal}
else:
    balmap = bal

def approx(a,b,tol=0.01): return abs(a-b) < tol

alice_bal = balmap.get(alice_uid)
bob_bal = balmap.get(bob_uid)
carol_bal = balmap.get(carol_uid)
print("balances:", {"alice":alice_bal, "bob":bob_bal, "carol":carol_bal})

# Handle possibility that balances are amounts owed by user (opposite sign)
ok1 = alice_bal is not None and (approx(alice_bal,125) or approx(alice_bal,-125))
rr("6e_balances_match", 
   alice_bal is not None and bob_bal is not None and carol_bal is not None and
   approx(alice_bal,125) and approx(bob_bal,-70) and approx(carol_bal,-55),
   {"alice":alice_bal, "bob":bob_bal, "carol":carol_bal, "raw":debts})

# Settlements
settlements = debts.get("settlements") or debts.get("transfers") or []
print("settlements:", settlements)
rr("6f_settlements_2_transactions", len(settlements)==2, f"count={len(settlements)} {settlements}")

# Check specific settlements
def find_settle(from_u, to_u):
    for s in settlements:
        f = s.get("from") or s.get("from_user_id") or s.get("payer")
        t = s.get("to") or s.get("to_user_id") or s.get("payee")
        if f==from_u and t==to_u:
            return s.get("amount") or s.get("value")
    return None

bob_to_alice = find_settle(bob_uid, alice_uid)
carol_to_alice = find_settle(carol_uid, alice_uid)
rr("6g_bob_to_alice_70", bob_to_alice is not None and approx(bob_to_alice,70), bob_to_alice)
rr("6h_carol_to_alice_55", carol_to_alice is not None and approx(carol_to_alice,55), carol_to_alice)

# === TEST 7: split with non-member ===
print("\n=== TEST 7 ===")
fake_uid = "user_notreal000000000000000000000"
r = alice.post(f"{API}/trips/{trip3_id}/expenses", json={
    "label":"Bad","cost":10,"currency":"EUR","paid_by":alice_uid,
    "split_between":[alice_uid, fake_uid]})
print("bad split:", r.status_code, r.text[:200])
rr("7_split_nonmember_rejected", r.status_code in (400,422), f"{r.status_code} {r.text[:200]}")

# === TEST 8: version endpoint ===
print("\n=== TEST 8 ===")
r = alice.get(f"{API}/trips/{trip3_id}/version")
print("v raw:", r.status_code, r.text[:200])
v1 = r.json() if r.status_code==200 else {}
version_key = "version" if "version" in v1 else next(iter(v1), None)
val1 = v1.get(version_key) if version_key else None

r = alice.post(f"{API}/trips/{trip3_id}/stops", json={"title":"S2","location":"Milan","start_date":"2025-05-04","end_date":"2025-05-05"})
new_stop = r.json()["stop_id"] if r.ok else None
r = alice.get(f"{API}/trips/{trip3_id}/version")
val2 = r.json().get(version_key) if r.status_code==200 else None

r = alice.patch(f"{API}/trips/{trip3_id}/attractions/{attr_id}", json={"name":"Colosseum2"})
print("patch attr:", r.status_code, r.text[:200])
r = alice.get(f"{API}/trips/{trip3_id}/version")
val3 = r.json().get(version_key) if r.status_code==200 else None
print(f"versions: v1={val1} v2={val2} v3={val3}")
rr("8_version_increments", val1 is not None and val2>val1 and val3>val2, f"v1={val1} v2={val2} v3={val3}")

# === TEST 9: presence ===
print("\n=== TEST 9: presence ===")
r = alice.post(f"{API}/trips/{trip3_id}/presence", json={"editing":"stop_xxx"})
print("presence post:", r.status_code, r.text[:300])
rr("9a_presence_post_ok", r.status_code in (200,201,204), f"{r.status_code}")

r = bob.get(f"{API}/trips/{trip3_id}/presence")
print("presence get:", r.status_code, r.text[:400])
pres = r.json() if r.status_code==200 else []
alice_pres = None
if isinstance(pres,list):
    for p in pres:
        u = p.get("user_id") or p.get("user",{}).get("user_id")
        if u == alice_uid:
            alice_pres = p; break
elif isinstance(pres,dict):
    users = pres.get("users") or pres.get("presence") or []
    for p in users:
        u = p.get("user_id") or p.get("user",{}).get("user_id")
        if u == alice_uid:
            alice_pres = p; break

rr("9b_bob_sees_alice", alice_pres is not None and alice_pres.get("editing")=="stop_xxx", alice_pres)

# TTL not tested (would need to wait 60s+)
print("TTL 60s not tested (HUMAN_REQUIRED for real timing)")

# === TEST 10: regressions ===
print("\n=== TEST 10: regressions ===")
r = alice.post(f"{API}/trips", json={"title":"Regr","home_currency":"USD","start_date":"2025-06-01","end_date":"2025-06-05"})
rt_id = r.json()["trip_id"]
r = alice.post(f"{API}/trips/{rt_id}/stops", json={"title":"S1","location":"NYC","start_date":"2025-06-01","end_date":"2025-06-02"})
sa = r.json()["stop_id"]
r = alice.post(f"{API}/trips/{rt_id}/stops", json={"title":"S2","location":"LA","start_date":"2025-06-03","end_date":"2025-06-04"})
sb = r.json()["stop_id"]
r = alice.post(f"{API}/trips/{rt_id}/stops/{sa}/attractions", json={"name":"A1"})
a1 = r.json()["attraction_id"]
r = alice.post(f"{API}/trips/{rt_id}/stops/{sb}/attractions", json={"name":"A2"})
a2 = r.json()["attraction_id"]

# cross-stop reorder: move a1 to sb
r = alice.post(f"{API}/trips/{rt_id}/attractions/reorder", json={"moves":[{"attraction_id":a1,"stop_id":sb,"order":0}]})
print("reorder:", r.status_code, r.text[:200])
rr("10a_reorder_cross_stop", r.status_code in (200,204), f"{r.status_code}")

# summary with missing_rates: home_currency USD, add expense in EUR without rate
r = alice.post(f"{API}/trips/{rt_id}/expenses", json={"label":"foo","cost":10,"currency":"EUR","paid_by":alice_uid,"split_between":[alice_uid]})
r = alice.get(f"{API}/trips/{rt_id}/summary")
print("summary:", r.status_code, r.text[:300])
summ = r.json() if r.status_code==200 else {}
mr = summ.get("missing_rates")
rr("10b_summary_missing_rates", r.status_code==200 and (mr is not None and (len(mr)>0 if isinstance(mr,list) else True)), f"missing_rates={mr}")

# cascade delete trip
r = alice.delete(f"{API}/trips/{rt_id}")
rr("10c_delete_trip_ok", r.status_code in (200,204), f"{r.status_code}")
r = alice.get(f"{API}/trips/{rt_id}")
rr("10d_deleted_trip_404", r.status_code==404, f"{r.status_code}")

# print final
print("\n=== FINAL ===")
for k,v in RESULTS.items(): print(f"  {'PASS' if v else 'FAIL'}: {k}")
print(f"\nTotal: {sum(RESULTS.values())}/{len(RESULTS)} passed")
