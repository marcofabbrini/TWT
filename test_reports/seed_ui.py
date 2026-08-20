"""Seed one UI smoke trip for alice with 2 stops + 3 attractions. Prints ids."""
import os, requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
s = requests.Session()
assert s.post(f"{API}/auth/dev-login", json={"email": "alice@twt.app", "name": "Alice"}).status_code == 200

t = s.post(f"{API}/trips", json={"title": "TEST_UI_P2FIX", "home_currency": "EUR",
                                 "start_date": "2030-09-01", "end_date": "2030-09-30"}).json()
tid = t["trip_id"]
s1 = s.post(f"{API}/trips/{tid}/stops", json={"title": "Lisbon", "location": "PT",
    "start_date": "2030-09-02", "end_date": "2030-09-05", "transport_mode": "plane"}).json()
s2 = s.post(f"{API}/trips/{tid}/stops", json={"title": "Porto", "location": "PT",
    "start_date": "2030-09-06", "end_date": "2030-09-09", "transport_mode": "car"}).json()
atts = []
for n in ("A1", "A2", "A3"):
    r = s.post(f"{API}/trips/{tid}/stops/{s1['stop_id']}/attractions",
               json={"name": n, "cost": 10, "booking_link": "https://example.org/x"})
    assert r.status_code == 201, r.text
    atts.append(r.json()["attraction_id"])
print("TRIP", tid)
print("STOP1", s1["stop_id"])
print("STOP2", s2["stop_id"])
print("ATTS", atts)
