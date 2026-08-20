"""Seed a UI trip for Sprint A+B frontend tests + legacy expenses for backfill test."""
import json
import os
from datetime import date, timedelta

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
EMAIL = "sprint_ui@twt.app"

s = requests.Session()
r = s.post(f"{API}/auth/dev-login", json={"email": EMAIL, "name": "Sprint UI"}, timeout=30)
r.raise_for_status()
tok = r.json()["session_token"]
s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})

# cleanup old seeds
for t in s.get(f"{API}/trips", timeout=30).json():
    if t["title"].startswith("SPRINTAB_UI"):
        s.delete(f"{API}/trips/{t['trip_id']}", timeout=30)

start = (date.today() - timedelta(days=1)).isoformat()
end = (date.today() + timedelta(days=6)).isoformat()
trip = s.post(f"{API}/trips", json={
    "title": "SPRINTAB_UI Roma loop",
    "home_currency": "EUR",
    "start_date": start,
    "end_date": end,
    "home_location": "Roma, Italy",
    "has_return": True,
}, timeout=30).json()
tid = trip["trip_id"]

stops = []
for i, (title, loc) in enumerate([
    ("Milano", "Milano, Italy"),
    ("Firenze", "Firenze, Italy"),
    ("Bologna", "Bologna, Italy"),
]):
    rs = s.post(f"{API}/trips/{tid}/stops", json={
        "title": title, "location": loc, "order": i,
        "start_date": (date.today() + timedelta(days=i)).isoformat(),
        "end_date": (date.today() + timedelta(days=i)).isoformat(),
        "transport_mode": "car",
    }, timeout=60)
    rs.raise_for_status()
    stops.append(rs.json())

exp_ids = []
for i, d in enumerate([
    (date.today() + timedelta(days=3)).isoformat(),
    (date.today()).isoformat(),
    (date.today() + timedelta(days=5)).isoformat(),
]):
    re_ = s.post(f"{API}/trips/{tid}/expenses", json={
        "label": f"UI expense {i}", "cost": 10 + i, "expense_date": d}, timeout=30)
    re_.raise_for_status()
    exp_ids.append((re_.json()["expense_id"], d))

out = {
    "email": EMAIL,
    "session_token": tok,
    "trip_id": tid,
    "start_date": start,
    "end_date": end,
    "stop_ids": [x["stop_id"] for x in stops],
    "expenses": exp_ids,
}
# a trip without return, single stop, and future dates for expense-modal default test
t2 = s.post(f"{API}/trips", json={
    "title": "SPRINTAB_UI Future solo",
    "home_currency": "EUR",
    "start_date": (date.today() + timedelta(days=30)).isoformat(),
    "end_date": (date.today() + timedelta(days=35)).isoformat(),
}, timeout=30).json()
s.post(f"{API}/trips/{t2['trip_id']}/stops", json={
    "title": "Napoli", "location": "Napoli, Italy", "order": 0,
    "start_date": (date.today() + timedelta(days=30)).isoformat(),
    "end_date": (date.today() + timedelta(days=31)).isoformat(),
    "transport_mode": "car"}, timeout=60)
out["trip2_id"] = t2["trip_id"]
out["trip2_start"] = t2["start_date"]
out["trip2_end"] = t2["end_date"]

open("/app/test_reports/sprintab_ui_seed.json", "w").write(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
