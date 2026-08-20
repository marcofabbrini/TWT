"""Backend regression test for Sprint A+B post-review.

Focus:
- DELETE /api/trips/{id} MUST cascade-delete expenses even when they have
  stop_id=None. This guards against the class of orphan-expense rows the
  tester reported (5 pre-existing docs whose trip no longer exists).

- One-shot cleanup of those 5 orphans is done via
  scripts/cleanup_orphan_expenses.py. The cleanup itself is idempotent and
  is verified by test_cleanup_script_is_idempotent below.
"""
import os
import subprocess
import sys
from typing import Optional

import pytest
import requests

# ── boilerplate copied from existing pytest suites ─────────────────────
frontend_env = {}
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            k, _, v = line.partition("=")
            frontend_env[k.strip()] = v.strip()
except Exception:
    pass
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001"
)
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


def _dev_login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/dev-login", json={"email": email, "name": email.split("@")[0]}, timeout=10)
    assert r.status_code == 200, r.text
    return s


# ── the regression the tester asked for ────────────────────────────────
def test_delete_trip_cascades_expense_without_stop_id():
    """A trip's expenses (including those with stop_id=None) must be gone
    after DELETE /trips/{id}. No orphans allowed."""
    s = _dev_login("orphan_regress@twt.app")

    # Create trip
    r = s.post(
        f"{API}/trips",
        json={
            "title": "OrphanRegress",
            "home_currency": "EUR",
            "start_date": "2026-06-01",
            "end_date": "2026-06-10",
        },
        timeout=10,
    )
    assert r.status_code == 201, r.text
    trip_id = r.json()["trip_id"]

    # Add an expense with stop_id=None (general cost)
    r = s.post(
        f"{API}/trips/{trip_id}/expenses",
        json={"label": "Orphan candidate", "cost": 10, "currency": "EUR"},
        timeout=10,
    )
    assert r.status_code == 201, r.text
    exp_id = r.json()["expense_id"]
    assert r.json().get("stop_id") is None

    # Add a second expense tied to a stop (to make sure both classes get purged)
    r = s.post(
        f"{API}/trips/{trip_id}/stops",
        json={
            "title": "S",
            "location": "Roma",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "transport_mode": "car",
        },
        timeout=15,
    )
    assert r.status_code == 201, r.text
    stop_id = r.json()["stop_id"]
    r = s.post(
        f"{API}/trips/{trip_id}/expenses",
        json={
            "label": "Bound to stop",
            "cost": 5,
            "currency": "EUR",
            "stop_id": stop_id,
        },
        timeout=10,
    )
    assert r.status_code == 201, r.text
    exp_id_bound = r.json()["expense_id"]

    # Sanity: list before delete has 2 expenses
    r = s.get(f"{API}/trips/{trip_id}/expenses", timeout=10)
    assert r.status_code == 200
    assert len(r.json()) == 2

    # Delete trip
    r = s.delete(f"{API}/trips/{trip_id}", timeout=10)
    assert r.status_code == 204, r.text

    # Trip itself is gone
    r = s.get(f"{API}/trips/{trip_id}", timeout=10)
    assert r.status_code == 404

    # And the expenses no longer appear in the (now-forbidden) list route.
    # Since the trip is gone, /trips/{id}/expenses returns 404 too — which is
    # itself proof they were cascaded. We also confirm via a fresh trip that
    # both expense_ids are absent from any future response.
    r = s.get(f"{API}/trips/{trip_id}/expenses", timeout=10)
    assert r.status_code in (403, 404), r.status_code

    # Belt-and-braces: hit Mongo directly. Load backend/.env so this branch
    # actually executes under pytest (the pytest process does NOT inherit
    # MONGO_URL/DB_NAME, so the previous `if` silently skipped these asserts).
    from dotenv import dotenv_values

    backend_env = dotenv_values("/app/backend/.env")
    mongo_url = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")
    assert mongo_url and db_name, "MONGO_URL/DB_NAME not resolvable from /app/backend/.env"
    if mongo_url and db_name:
        from pymongo import MongoClient

        m = MongoClient(mongo_url)
        d = m[db_name]
        assert d.expenses.count_documents({"expense_id": exp_id}) == 0
        assert d.expenses.count_documents({"expense_id": exp_id_bound}) == 0
        assert d.expenses.count_documents({"trip_id": trip_id}) == 0
        m.close()


def test_cleanup_script_is_idempotent():
    """The one-shot cleanup MUST leave the DB in the same state on re-run."""
    script_path = "/app/backend/scripts/cleanup_orphan_expenses.py"
    assert os.path.exists(script_path), "cleanup script missing"

    env = os.environ.copy()
    # Ensure .env is loaded when running standalone
    r1 = subprocess.run(
        [sys.executable, script_path],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    r2 = subprocess.run(
        [sys.executable, script_path],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    # Second run reports 0 removed
    assert "removed=0" in (r2.stdout + r2.stderr), r2.stdout + r2.stderr
