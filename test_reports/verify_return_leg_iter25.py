"""Independent verification of return_leg parity (iteration 25)."""
import json
import os
import requests

env = {}
with open("/app/frontend/.env") as f:
    for line in f:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"')
API = env["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

EXPECTED = {"home_location", "home_coords", "from_stop_id", "transport_mode",
            "geojson", "distance_m", "duration_s"}

s = requests.Session()
r = s.post(f"{API}/auth/dev-login", json={"email": "rl_verify_iter25@twt.app", "name": "RLV"}, timeout=15)
print("dev-login:", r.status_code)

r = s.post(f"{API}/trips", json={
    "title": "RLVerify25", "home_currency": "EUR",
    "start_date": "2026-11-01", "end_date": "2026-11-05",
    "home_location": "Milano, Italia", "has_return": True,
}, timeout=20)
print("create trip:", r.status_code)
trip_id = r.json()["trip_id"]

r = s.post(f"{API}/trips/{trip_id}/stops", json={
    "title": "Roma", "location": "Roma",
    "start_date": "2026-11-01", "end_date": "2026-11-03",
    "transport_mode": "car",
}, timeout=30)
print("create stop:", r.status_code)
stop_id = r.json().get("stop_id") or r.json().get("stop", {}).get("stop_id")
print("stop_id:", stop_id)

tl = s.get(f"{API}/trips/{trip_id}/timeline", timeout=30)
rg = s.get(f"{API}/trips/{trip_id}/route-geometry", timeout=30)
print("timeline:", tl.status_code, "route-geometry:", rg.status_code)
a = tl.json()["return_leg"]
b = rg.json()["return_leg"]
print("TIMELINE return_leg:", json.dumps({k: (v if k != 'geojson' else ('present' if v else None)) for k, v in a.items()}, default=str))
print("ROUTEGEO return_leg:", json.dumps({k: (v if k != 'geojson' else ('present' if v else None)) for k, v in b.items()}, default=str))

ok = True
for name, leg in (("timeline", a), ("route-geometry", b)):
    if set(leg.keys()) != EXPECTED:
        ok = False
        print(f"FAIL keys {name}: extra={set(leg)-EXPECTED} missing={EXPECTED-set(leg)}")
    else:
        print(f"PASS keys {name}")

for k in ("home_location", "from_stop_id", "transport_mode", "home_coords"):
    if a[k] != b[k]:
        ok = False
        print(f"FAIL parity {k}: {a[k]!r} != {b[k]!r}")
    else:
        print(f"PASS parity {k} = {a[k]!r}")

if a["from_stop_id"] != stop_id:
    ok = False
    print(f"FAIL from_stop_id != last stop_id ({a['from_stop_id']} vs {stop_id})")
else:
    print("PASS from_stop_id == last stop_id")

if a["transport_mode"] != "car":
    ok = False
    print("FAIL transport_mode != car")
if a["home_location"] != "Milano, Italia":
    ok = False
    print("FAIL home_location mismatch")

# geometry symmetry
for k in ("geojson", "distance_m", "duration_s"):
    print(f"geom {k}: timeline={'None' if a[k] is None else 'set'} rg={'None' if b[k] is None else 'set'}")

# second stop → from_stop_id must follow the new last stop
r = s.post(f"{API}/trips/{trip_id}/stops", json={
    "title": "Firenze", "location": "Firenze",
    "start_date": "2026-11-03", "end_date": "2026-11-05",
    "transport_mode": "train",
}, timeout=30)
stop2 = r.json().get("stop_id") or r.json().get("stop", {}).get("stop_id")
a2 = s.get(f"{API}/trips/{trip_id}/timeline", timeout=30).json()["return_leg"]
b2 = s.get(f"{API}/trips/{trip_id}/route-geometry", timeout=30).json()["return_leg"]
print("after 2nd stop -> timeline.from_stop_id:", a2["from_stop_id"], "rg:", b2["from_stop_id"], "expected:", stop2)
if not (a2["from_stop_id"] == b2["from_stop_id"] == stop2):
    ok = False
    print("FAIL from_stop_id not updated to new last stop")
else:
    print("PASS from_stop_id follows last stop in both")
if a2["home_coords"] != b2["home_coords"]:
    ok = False
    print("FAIL home_coords mismatch after 2nd stop")

s.delete(f"{API}/trips/{trip_id}", timeout=15)
print("\nRESULT:", "ALL PASS" if ok else "FAILURES FOUND")
