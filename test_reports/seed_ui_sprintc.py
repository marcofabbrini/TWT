"""Seed a UI trip for Sprint C day-tabs frontend tests."""
import json
from datetime import date, timedelta

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
EMAIL = "sprintc_ui@twt.app"

s = requests.Session()
r = s.post(f"{API}/auth/dev-login", json={"email": EMAIL, "name": "Sprint C UI"}, timeout=60)
r.raise_for_status()
tok = r.json()["session_token"]
s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})

for t in s.get(f"{API}/trips", timeout=60).json():
    if t["title"].startswith("SPRINTC_UI"):
        s.delete(f"{API}/trips/{t['trip_id']}", timeout=60)

T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()
start, end = d(-1), d(8)

trip = s.post(f"{API}/trips", json={
    "title": "SPRINTC_UI Day tabs",
    "home_currency": "EUR",
    "start_date": start,
    "end_date": end,
    "home_location": "Torino, Italy",
    "has_return": True,
}, timeout=60).json()
tid = trip["trip_id"]

def stop(title, loc, a, b, mode="car"):
    r = s.post(f"{API}/trips/{tid}/stops", json={
        "title": title, "location": loc,
        "start_date": d(a), "end_date": d(b), "transport_mode": mode,
    }, timeout=120)
    r.raise_for_status()
    return r.json()["stop_id"]

roma = stop("Roma", "Roma, Italy", -1, 2)       # first/middle/middle/last
# gap on d(3) -> transit day
milano = stop("Milano", "Milano, Italy", 4, 4, "train")   # only
firenze = stop("Firenze", "Firenze, Italy", 5, 8, "plane")  # first..last(return home)

def att(sid, name, sd=None):
    body = {"name": name}
    if sd:
        body["scheduled_date"] = sd
    r = s.post(f"{API}/trips/{tid}/stops/{sid}/attractions", json=body, timeout=60)
    r.raise_for_status()
    return r.json()["attraction_id"]

a_sched = att(roma, "SPRINTC Colosseo", d(0))
a_un1 = att(roma, "SPRINTC Unsched Roma")
a_un2 = att(firenze, "SPRINTC Unsched Firenze")

exp = s.post(f"{API}/trips/{tid}/expenses", json={
    "label": "SPRINTC Dinner", "cost": 30, "currency": "EUR",
    "stop_id": roma, "expense_date": d(0),
}, timeout=60)
exp.raise_for_status()

out = {
    "email": EMAIL, "session_token": tok, "trip_id": tid,
    "start": start, "end": end,
    "days": [d(i) for i in range(-1, 9)],
    "today": T.isoformat(),
    "stops": {"roma": roma, "milano": milano, "firenze": firenze},
    "attractions": {"scheduled": a_sched, "unsched": [a_un1, a_un2]},
}
json.dump(out, open("/app/test_reports/sprintc_ui_seed.json", "w"), indent=1)
print(json.dumps(out, indent=1))
