"""Seed Phase 4 UI test data: owner trip + stop + invite tokens."""
import uuid
import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
sfx = uuid.uuid4().hex[:6]
owner_email = f"p4owner_{sfx}@twt.app"
invitee_email = f"p4invitee_{sfx}@twt.app"
other_email = f"p4other_{sfx}@twt.app"

s = requests.Session()
r = s.post(f"{API}/auth/dev-login", json={"email": owner_email, "name": "P4 Owner"})
assert r.status_code == 200, r.text
t = s.post(f"{API}/trips", json={"title": f"TEST_P4_UI_{sfx}", "home_currency": "EUR",
                                 "start_date": "2030-10-01", "end_date": "2030-10-20"}).json()
tid = t["trip_id"]
st = s.post(f"{API}/trips/{tid}/stops", json={"title": "Madrid", "location": "ES",
    "start_date": "2030-10-02", "end_date": "2030-10-06", "transport_mode": "plane"}).json()
inv = s.post(f"{API}/trips/{tid}/invites", json={"email": invitee_email, "role": "editor"}).json()
print("OWNER_EMAIL", owner_email)
print("INVITEE_EMAIL", invitee_email)
print("OTHER_EMAIL", other_email)
print("TRIP", tid)
print("STOP", st["stop_id"])
print("TOKEN", inv["invite_token"])
