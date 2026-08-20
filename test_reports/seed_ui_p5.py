"""Phase 5 UI seed — trip with Roma/Milano/Firenze stops, manual km leg, hotels with deadlines."""
import json
import os
import uuid
from datetime import date, timedelta

import requests
from dotenv import dotenv_values

API = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
TODAY = date.today()
email = f"p5ui_{uuid.uuid4().hex[:6]}@twt.app"

s = requests.Session()
r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": "P5 UI"}, timeout=30)
r.raise_for_status()
s.headers.update({"Authorization": f"Bearer {r.json()['session_token']}"})

start = TODAY - timedelta(days=2)
end = TODAY + timedelta(days=40)
trip = s.post(f"{API}/trips", json={"title": "TEST_P5 UI Trip", "home_currency": "EUR",
                                    "start_date": start.isoformat(), "end_date": end.isoformat()}, timeout=30).json()
tid = trip["trip_id"]


def stop(title, loc, d0, d1, mode="car"):
    r = s.post(f"{API}/trips/{tid}/stops", json={"title": title, "location": loc,
               "start_date": (start + timedelta(days=d0)).isoformat(),
               "end_date": (start + timedelta(days=d1)).isoformat(), "transport_mode": mode}, timeout=60)
    r.raise_for_status()
    return r.json()


a = stop("TEST_Roma", "Roma, IT", 0, 2)
b = stop("TEST_Milano", "Milano, IT", 2, 4, "car")
c = stop("TEST_Firenze", "Firenze, IT", 4, 6, "plane")
# manual override on Firenze leg
s.patch(f"{API}/trips/{tid}/stops/{c['stop_id']}", json={"km_from_prev": 999, "km_manual_override": True}, timeout=60).raise_for_status()
# a leg with no computable km (unknown city) -> null leg so KmTotal shows '+'
d = stop("TEST_Unknown", "Zzyzxville, XX", 6, 7, "car")


def hotel(sid, name, deadline_delta):
    r = s.post(f"{API}/trips/{tid}/stops/{sid}/hotels", json={
        "name": name, "check_in": start.isoformat(), "check_out": (start + timedelta(days=1)).isoformat(),
        "cost": 120, "cancellation_deadline": (TODAY + timedelta(days=deadline_delta)).isoformat()}, timeout=30)
    r.raise_for_status()
    return r.json()


h_red = hotel(a["stop_id"], "TEST_Hotel Red 2d", 2)
h_yellow = hotel(a["stop_id"], "TEST_Hotel Yellow 5d", 5)
h_green = hotel(a["stop_id"], "TEST_Hotel Green 30d", 30)
h_past = hotel(a["stop_id"], "TEST_Hotel Expired", -4)

out = {"email": email, "trip_id": tid, "stops": {"roma": a["stop_id"], "milano": b["stop_id"],
       "firenze": c["stop_id"], "unknown": d["stop_id"]},
       "hotels": {"red": h_red["hotel_id"], "yellow": h_yellow["hotel_id"],
                  "green": h_green["hotel_id"], "past": h_past["hotel_id"]}}
print(json.dumps(out, indent=1))
with open("/app/test_reports/p5_ui_seed.json", "w") as f:
    json.dump(out, f)
