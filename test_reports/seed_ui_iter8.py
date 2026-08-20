"""Seed a trip (EUR home) with EUR hotel + USD hotel (no rate) for iteration_8 FE test."""
import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
s = requests.Session()
assert s.post(f"{API}/auth/dev-login", json={"email": "alice@twt.app", "name": "Alice"}).status_code == 200
t = s.post(f"{API}/trips", json={"title": "TEST_UI_ITER8", "home_currency": "EUR",
                                 "start_date": "2030-10-01", "end_date": "2030-10-20"}).json()
tid = t["trip_id"]
st = s.post(f"{API}/trips/{tid}/stops", json={"title": "Madrid", "location": "ES",
    "start_date": "2030-10-02", "end_date": "2030-10-06", "transport_mode": "plane"}).json()
sid = st["stop_id"]
r1 = s.post(f"{API}/trips/{tid}/stops/{sid}/hotels", json={"name": "Hotel EUR", "check_in": "2030-10-02",
    "check_out": "2030-10-04", "cost": 200, "currency": "EUR"})
r2 = s.post(f"{API}/trips/{tid}/stops/{sid}/hotels", json={"name": "Hotel USD", "check_in": "2030-10-04",
    "check_out": "2030-10-06", "cost": 100, "currency": "USD"})
a1 = s.post(f"{API}/trips/{tid}/stops/{sid}/attractions", json={"name": "Prado", "cost": 15, "currency": "EUR"})
a2 = s.post(f"{API}/trips/{tid}/stops/{sid}/attractions", json={"name": "Retiro", "cost": 5, "currency": "EUR"})
print("statuses", r1.status_code, r2.status_code, a1.status_code, a2.status_code)
print("TRIP", tid)
print("STOP", sid)
print("SUMMARY", s.get(f"{API}/trips/{tid}/summary").json())
