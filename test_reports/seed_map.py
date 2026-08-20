"""Seed data for Trip Map UI testing (iteration 18).

Creates user mapui@twt.app with trip 'TEST_MAP_UI' containing 4 stops:
  1. Roma   (car)
  2. Firenze(train)
  3. London (plane)
  4. Napoli (other)
Prints the trip_id + stop ids as JSON.
"""
import json
import os
import sys

import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
EMAIL = "mapui@twt.app"

s = requests.Session()
r = s.post(f"{API}/auth/dev-login", json={"email": EMAIL, "name": "Map UI"})
r.raise_for_status()

# remove old seeds
for t in s.get(f"{API}/trips").json():
    if t["title"] == "TEST_MAP_UI":
        s.delete(f"{API}/trips/{t['trip_id']}")

r = s.post(f"{API}/trips", json={
    "title": "TEST_MAP_UI", "home_currency": "EUR",
    "start_date": "2026-09-01", "end_date": "2026-09-20"})
r.raise_for_status()
tid = r.json()["trip_id"]

stops = [
    ("Roma stop", "Roma", "car", "2026-09-01", "2026-09-03"),
    ("Firenze stop", "Firenze", "train", "2026-09-04", "2026-09-06"),
    ("London stop", "London", "plane", "2026-09-07", "2026-09-10"),
    ("Napoli stop", "Napoli", "other", "2026-09-11", "2026-09-13"),
]
ids = []
for title, loc, mode, sd, ed in stops:
    rr = s.post(f"{API}/trips/{tid}/stops", json={
        "title": title, "location": loc, "start_date": sd, "end_date": ed,
        "transport_mode": mode})
    rr.raise_for_status()
    ids.append(rr.json()["stop_id"])

out = {"email": EMAIL, "trip_id": tid, "stop_ids": ids,
       "trip_url": f"{BASE}/trip/{tid}"}
print(json.dumps(out, indent=2))
