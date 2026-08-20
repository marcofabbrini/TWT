import os, uuid, json, requests
from dotenv import dotenv_values
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

def u(p): return f"{p}{uuid.uuid4().hex[:8]}@twt.app"

s = requests.Session()
d = s.post(f"{API}/auth/dev-login", json={"email": u("dbg_a_"), "name": "A"}).json()
s.headers.update({"Authorization": f"Bearer {d['session_token']}"})
alice = d["user"]["user_id"]
trip = s.post(f"{API}/trips", json={"title": "DBG", "start_date": "2026-06-01", "end_date": "2026-06-10", "home_currency": "EUR"}).json()
tid = trip["trip_id"]
print("trip home:", trip.get("home_currency"))
b = requests.Session()
db_ = b.post(f"{API}/auth/dev-login-as", json={"email": u("dbg_b_"), "trip_id": tid, "role": "editor"}).json()
b.headers.update({"Authorization": f"Bearer {db_['session_token']}"})
bob = db_["user"]["user_id"]
r = s.post(f"{API}/trips/{tid}/expenses", json={"label": "D1", "cost": 100, "currency": "EUR", "paid_by": alice, "split_between": [alice, bob]})
print("expense:", r.status_code, r.text[:400])
print("members:", json.dumps(s.get(f"{API}/trips/{tid}/members").json(), indent=1)[:800])
print("debts:", json.dumps(s.get(f"{API}/trips/{tid}/debts").json(), indent=1))
