"""ORS-unreachable fallback check for return_leg (requires ORS_MOCK=1)."""
import requests
from datetime import date, timedelta
from dotenv import dotenv_values

B = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{B}/api"
s = requests.Session()
tok = s.post(f"{API}/auth/dev-login", json={"email": "sprint_ab@twt.app"}, timeout=30).json()["session_token"]
s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})

st = date.today().isoformat()
en = (date.today() + timedelta(days=3)).isoformat()
t = s.post(f"{API}/trips", json={"title": "TEST_ORSFB", "home_currency": "EUR",
                                 "start_date": st, "end_date": en,
                                 "home_location": "Lisbon", "has_return": True}, timeout=30).json()
tid = t["trip_id"]
s.post(f"{API}/trips/{tid}/stops", json={"title": "TEST_Venezia", "location": "Venezia, Italy",
                                         "order": 0, "start_date": st, "end_date": st,
                                         "transport_mode": "car"}, timeout=60)
r = s.get(f"{API}/trips/{tid}/route-geometry", timeout=60)
leg = r.json().get("return_leg")
print("status", r.status_code)
print("return_leg:", {k: (v if k != "geojson" else ("LineString" if v else None)) for k, v in (leg or {}).items()})
ok = leg and leg["geojson"] is None and leg["distance_m"] and leg["distance_m"] > 0
print("FALLBACK_OK" if ok else "FALLBACK_FAIL")
s.delete(f"{API}/trips/{tid}", timeout=30)
