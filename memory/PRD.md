# TWT — Trip Without Trap

## Original problem statement
Build TWT (Trip Without Trap), a FARM-stack web app (FastAPI + React + MongoDB) for planning trips. This is **Phase 1 of 5**: foundations + dashboard + trip creation only. No stops, no attractions, no currency conversion, no collaborators yet.

## Design
- Dark mode by default (no toggle).
- Glassmorphism: blurred surfaces, subtle borders, dark gradients.
- Accent color: **Teal-mint (#5EEAD4)** as primary; Amber (#F5B841) reserved for badges/state.
- Fonts: **Instrument Serif** (display) + **Sora** (body). Both loaded via Google Fonts.
- Icons: lucide-react. Motion: framer-motion.

## Architecture
- Backend `/app/backend/` — FastAPI. All routes prefixed `/api`. Modules:
  - `server.py` — app bootstrap, CORS, index init, health/openapi.
  - `db.py` — Motor Mongo client + `ensure_indexes()`.
  - `models.py` — Pydantic models for User, Trip, TripMember + documented future schemas (Stop, Attraction, Hotel, Expense, ExchangeRate).
  - `auth.py` — Emergent-managed Google Auth. Endpoints: `/auth/google/login`, `/auth/session`, `/auth/me`, `/auth/logout`, `/auth/dev-login` (ENV=dev only). `require_auth` supports cookie + Bearer.
  - `trips.py` — POST/GET/DELETE `/api/trips` with membership enforcement.
- Frontend `/app/frontend/src/` — React + CRACO. AuthContext, ProtectedRoute, glass utility classes in `index.css`, brand tokens in `tailwind.config.js`.

## Collections + indexes
- `users` (user_id unique, email unique, google_id sparse)
- `user_sessions` (session_token unique, user_id, TTL on expires_at)
- `trips` (trip_id unique, owner_id, start_date desc)
- `trip_members` (member_id unique, (trip_id,user_id), user_id, invited_email)

## User personas
- Solo traveler mapping their next trip.
- Small group of friends splitting a shared route (Phase 3+).

## Core static requirements
1. Google OAuth via Emergent — httpOnly cookie `twt_session`, secure, SameSite=None.
2. All `/api/trips/*` require membership check via `trip_members`.
3. Trip `home_currency` is immutable (no PATCH endpoint on that field).
4. Data isolation: user A cannot see user B's trips.
5. `/api/openapi.json` exposed.
6. `POST /api/auth/dev-login` active only when `ENV=dev`.

## Implemented (2026-02)
- Emergent Google Auth end-to-end + dev-login for tests.
- Users upsert-by-email; sessions with TTL and cookie clear on logout.
- Trip CRUD (create/list/detail/delete). List sorted by start_date desc.
- Membership auto-created on trip creation (role=owner).
- Cascade delete of trip_members on trip delete (owner-only).
- Dashboard: glass trip cards, empty state, create-trip modal (title/currency/dates/cover URL), delete confirmation.
- `/trip/{id}` placeholder for Phase 2 with membership check.
- Landing hero with mock trip preview, animated ambient orbs, feature grid.
- Tests: 23/23 backend pytest, all frontend flows verified via Playwright.

## Backlog

### P0 (blocking Phase 2 start)
- Stops CRUD (`stops` collection + `/api/trips/{id}/stops`).
- Route ordering (drag & drop).
- Map view (Leaflet or Mapbox) with stop pins.

### P1
- Attractions per stop (category, schedule).
- Hotels per stop with price + booking URL.
- Cover image upload (Emergent Object Storage, not URL field).

### P2
- Expenses with automatic conversion to `home_currency` via `exchange_rates` collection.
- Collaborators: invite by email, roles editor/viewer, pending → accepted flow.
- Trip export (PDF / shareable public read-only page).
- Profile page (change avatar, home_currency_default).

## Known limitations
- No pagination on `/api/trips` (in-memory sort acceptable for Phase 1).
- Native date inputs in create-trip modal (not shadcn Calendar) — kept simple; can be upgraded in P2.
- CORS is wildcard with `allow_credentials=true` in dev — pin origins before production.

## Testing
- Regression pytest suite: `/app/backend/tests/backend_test.py` (`cd /app/backend && python -m pytest tests/backend_test.py -v`).
- Test credentials + auth playbook: `/app/memory/test_credentials.md`, `/app/memory/auth_testing.md`.
