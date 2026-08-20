"""Seed UI data for Final Polish Task 2 (trip card summary)."""
import json
import os

import httpx
from dotenv import dotenv_values

API = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
EMAIL = "uitrips@twt.app"

c = httpx.Client(base_url=API, timeout=60)
r = c.post("/api/auth/dev-login", json={"email": EMAIL, "name": "UI Trips"})
r.raise_for_status()

# clean previous TEST_UI trips
for t in c.get("/api/trips").json():
    if t["title"].startswith("TEST_UI_"):
        c.delete(f"/api/trips/{t['trip_id']}")

out = {"email": EMAIL}


def mk(title, start, end):
    r = c.post("/api/trips", json={"title": title, "home_currency": "EUR",
                                   "start_date": start, "end_date": end})
    r.raise_for_status()
    return r.json()["trip_id"]


# 1) full trip: km 150.5, cost 245.00
t1 = mk("TEST_UI_Full", "2026-10-01", "2026-10-10")
sids = []
for i, (title, loc, km) in enumerate([("A", "Roma", 100), ("B", "Milano", 50.5)]):
    s = c.post(f"/api/trips/{t1}/stops", json={
        "title": title, "location": loc,
        "start_date": f"2026-10-0{i+1}", "end_date": f"2026-10-0{i+1}",
        "transport_mode": "car"}).json()
    c.patch(f"/api/trips/{t1}/stops/{s['stop_id']}",
            json={"km_from_prev": km, "km_manual_override": True})
    sids.append(s["stop_id"])
c.post(f"/api/trips/{t1}/stops/{sids[0]}/hotels", json={
    "name": "TEST_UI_H", "check_in": "2026-10-01", "check_out": "2026-10-02",
    "cost": 200, "currency": "EUR"}).raise_for_status()
c.put(f"/api/trips/{t1}/exchange-rates",
      json={"from_currency": "USD", "to_currency": "EUR", "rate": 0.9}).raise_for_status()
c.post(f"/api/trips/{t1}/expenses",
       json={"label": "TEST_UI_E", "cost": 50, "currency": "USD"}).raise_for_status()
out["full"] = t1

# 2) missing rates: cost 100.00 + flag
t2 = mk("TEST_UI_Missing", "2026-09-01", "2026-09-05")
s = c.post(f"/api/trips/{t2}/stops", json={
    "title": "S", "location": "Roma", "start_date": "2026-09-01",
    "end_date": "2026-09-02", "transport_mode": "car"}).json()
c.post(f"/api/trips/{t2}/stops/{s['stop_id']}/hotels", json={
    "name": "TEST_UI_H2", "check_in": "2026-09-01", "check_out": "2026-09-02",
    "cost": 100, "currency": "EUR"}).raise_for_status()
c.post(f"/api/trips/{t2}/expenses",
       json={"label": "TEST_UI_GBP", "cost": 30, "currency": "GBP"}).raise_for_status()
out["missing"] = t2

# 3) empty trip
t3 = mk("TEST_UI_Empty", "2026-08-01", "2026-08-03")
out["empty"] = t3

summaries = {t["trip_id"]: t["summary"] for t in c.get("/api/trips").json()}
out["summaries"] = {k: summaries.get(v) for k, v in out.items() if k != "summaries" and k != "email"}
print(json.dumps(out, indent=2))
with open("/app/test_reports/task2_ui_seed.json", "w") as f:
    json.dump(out, f, indent=2)
