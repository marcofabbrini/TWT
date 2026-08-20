"""Seed one UI smoke trip (Phase 3) for alice: 2 stops, attractions (EUR+USD), 1 hotel. Prints ids."""
import os, requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
s = requests.Session()
assert s.post(f"{API}/auth/dev-login", json={"email": "alice@twt.app", "name": "Alice"}).status_code == 200

t = s.post(f"{API}/trips", json={"title": "TEST_UI_P3", "home_currency": "EUR",
                                 "start_date": "2030-09-01", "end_date": "2030-09-30"}).json()
tid = t["trip_id"]
s1 = s.post(f"{API}/trips/{tid}/stops", json={"title": "Lisbon", "location": "PT",
    "start_date": "2030-09-02", "end_date": "2030-09-05", "transport_mode": "plane"}).json()
s2 = s.post(f"{API}/trips/{tid}/stops", json={"title": "Porto", "location": "PT",
    "start_date": "2030-09-06", "end_date": "2030-09-09", "transport_mode": "car"}).json()
for n, cur in (("Belem Tower", "EUR"), ("Oceanarium", "EUR"), ("Tram 28", "USD")):
    r = s.post(f"{API}/trips/{tid}/stops/{s1['stop_id']}/attractions",
               json={"name": n, "cost": 20, "currency": cur,
                     "booking_link": "https://example.org/x"})
    assert r.status_code == 201, r.text
h = s.post(f"{API}/trips/{tid}/stops/{s1['stop_id']}/hotels",
           json={"name": "Hotel Alfama", "location": "Lisbon", "check_in": "2030-09-02",
                 "check_out": "2030-09-05", "cost": 300, "currency": "EUR",
                 "booking_link": "https://booking.com/x"})
assert h.status_code == 201, h.text
e = s.post(f"{API}/trips/{tid}/expenses", json={"label": "Rental car", "cost": 120})
assert e.status_code == 201, e.text
print("TRIP", tid)
print("STOP1", s1["stop_id"])
print("STOP2", s2["stop_id"])
print("SUMMARY", s.get(f"{API}/trips/{tid}/summary").json())
