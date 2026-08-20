"""Seed iteration-10 UI test data: owner trip + stop + expense + viewer member."""
import json
import uuid

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
sfx = uuid.uuid4().hex[:6]
owner_email = f"i10owner_{sfx}@twt.app"
viewer_email = f"i10viewer_{sfx}@twt.app"

s = requests.Session()
r = s.post(f"{API}/auth/dev-login", json={"email": owner_email, "name": "I10 Owner"})
assert r.status_code == 200, r.text
owner_token = r.json()["session_token"]
t = s.post(f"{API}/trips", json={"title": f"TEST_I10_{sfx}", "home_currency": "EUR",
                                 "start_date": "2030-10-01", "end_date": "2030-10-20"}).json()
tid = t["trip_id"]
st = s.post(f"{API}/trips/{tid}/stops", json={"title": "Madrid", "location": "ES",
    "start_date": "2030-10-02", "end_date": "2030-10-06", "transport_mode": "plane"}).json()

# viewer as accepted member
r2 = requests.post(f"{API}/auth/dev-login-as", json={"email": viewer_email, "trip_id": tid, "role": "viewer"})
assert r2.status_code == 200, r2.text
viewer_token = r2.json()["session_token"]
members = s.get(f"{API}/trips/{tid}/members").json()
viewer_member_id = next(m["member_id"] for m in members if (m.get("user") or {}).get("email", "").lower() == viewer_email)

out = {
    "owner_email": owner_email, "owner_token": owner_token,
    "viewer_email": viewer_email, "viewer_token": viewer_token,
    "trip_id": tid, "stop_id": st["stop_id"], "viewer_member_id": viewer_member_id,
}
print(json.dumps(out, indent=2))
with open("/app/test_reports/iter10_seed.json", "w") as f:
    json.dump(out, f)
