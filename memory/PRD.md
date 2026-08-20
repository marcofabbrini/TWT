# TWT — Trip Without Trap

## Original problem statement
Build TWT (Trip Without Trap), a FARM-stack web app (FastAPI + React + MongoDB) for planning trips. 5 phases total. Phase 1: foundations + dashboard. Phase 2: stops + attractions + drag&drop. Phase 3: hotels. Phase 4: collaborators. Phase 5: expenses + KM auto-calc + currency conversion.

## Design
- Dark mode by default (no toggle).
- Glassmorphism: blurred surfaces, subtle borders, dark gradients.
- Accent color: **Teal-mint (#5EEAD4)**; Amber (#F5B841) reserved for state badges (cost, editor role).
- Font: **Sniglet** (400 / 800) as global sans + display — rounded, playful, distinctive.
- Localized override: `.font-nunito` for the "Iberian Loop" mock title on the Landing hero (per user request, line 120 of Landing.jsx).
- Icons: lucide-react. Motion: framer-motion. Drag&Drop: @dnd-kit.

## Architecture
- Backend `/app/backend/`
  - `server.py` — app bootstrap, CORS, index init, `openapi_url=/api/openapi.json`.
  - `db.py` — Motor client + `ensure_indexes()`.
  - `models.py` — Pydantic models (User, Trip, TripMember, Stop, Attraction) + reorder DTOs.
  - `auth.py` — Emergent Google Auth + `require_auth` (cookie + Bearer) + `dev-login` (ENV=dev only).
  - `permissions.py` — `get_trip_or_404`, `get_membership_or_404`, `require_role` (viewer<editor<owner).
  - `trips.py` — POST/GET/DELETE `/api/trips`. **Delete cascades attractions → stops → trip_members → trip.**
  - `stops.py` — CRUD + reorder (full-permutation required).
  - `attractions.py` — CRUD + cross-stop atomic reorder (pre-validate + bulk_write).
- Frontend `/app/frontend/src/`
  - Pages: `Landing`, `Dashboard`, `Trip`, `AuthCallback`.
  - Components: `Header`, `TripCard`, `CreateTripModal`, `StopCard`, `StopModal`, `AttractionItem`, `AttractionModal`, `ProtectedRoute`.
  - Libs: `api.js`, `permissions.js` (canEdit), `transport.js` (icon map).

## Collections + indexes
- `users` (user_id unique, email unique, google_id sparse)
- `user_sessions` (session_token unique, user_id, TTL on expires_at)
- `trips` (trip_id unique, owner_id, start_date desc)
- `trip_members` (member_id unique, (trip_id,user_id), user_id, invited_email)
- `stops` (stop_id unique, (trip_id, order))
- `attractions` (attraction_id unique, (trip_id, stop_id, order))

## User personas
- Solo traveler drafting a next trip.
- Small group of friends splitting a shared route (Phase 4+).

## Core static requirements
1. Google OAuth via Emergent — httpOnly cookie `twt_session`, secure, SameSite=None.
2. All trip-scoped routes require membership check via `trip_members`.
3. `home_currency` is immutable (no PATCH endpoint on that field).
4. Data isolation: user A cannot see user B's trips/stops/attractions.
5. `/api/openapi.json` exposed.
6. `POST /api/auth/dev-login` active only when `ENV=dev`.
7. Editor+Owner can create/update/delete stops/attractions; Viewer read-only.
8. Trip delete cascades **all** related data (verified: 0 orphans).
9. Booking link URLs must start with `http://` or `https://` (rejects `javascript:`, `data:`, etc.).

## Implemented

### Phase 1 (2026-02, verified 23/23 backend + all frontend)
- Emergent Google Auth end-to-end + dev-login.
- Users upsert-by-email; TTL sessions; cookie clear on logout.
- Trip CRUD (list sorted by start_date desc). Membership auto-created on trip create.
- Dashboard: glass trip cards, empty state, create modal, delete confirmation.
- Landing hero + feature grid.

### Phase 5 (2026-02, verified 211/211 backend + all frontend)
- Trip PATCH (owner only): title, dates, cover. `home_currency` is not in the update model → truly immutable. Date changes are refused with 422 + `stops_out_of_range` list if any stop would fall outside the new range.
- KM auto-calc via **OpenRouteService**: geocode + directions for car/walk (train uses driving-car fallback), Haversine for plane. Cached geocoding (30d TTL). ORS_MOCK=1 provides deterministic pairs for tests. Graceful fallback to null on missing key / timeout — never blocks a mutation.
- Triggers: recompute on stop create, on location/transport change, and on reorder (whole trip). `km_manual_override=true` freezes user-provided value.
- `POST /trips/{id}/recompute-km` (editor+) forces a full trip refresh; response `{updated_count, errors[]}`.
- `GET /trips/{id}/summary.total_km` now aggregates real km.
- Cancellation-deadline alerts: `GET /notifications/cancellation-alerts` aggregates hotels across all user's trips with deadline ≤ 7 days (or past) with severity red/yellow. Dashboard `<NotificationsBell/>` with badge + popover linking to each trip. `<HotelList/>` shows an inline red/yellow/green DeadlineBadge with a steady scale pulse on red.

### Phase 4 (2026-02, verified 181/181 backend + all frontend)
- Members mgmt: `POST /trips/{id}/invites` (owner-only, generates share link), `GET/POST/decline /invites/{token}` public accept flow with email match.
- Roles enforced everywhere: viewer read-only, editor CRUD but no members/rates/delete-trip, owner full access. `require_role` returns 403 for member-without-perm, 404 for non-member.
- Transfer ownership on leave: oldest editor promoted; if no editors, trip is hard-deleted with full cascade.
- Sync polling: `GET /trips/{id}/version` bumped by every mutation; frontend `useTripSync` polls 5s with silent refetch, stops on 401/403/404.
- Presence: `GET/POST /trips/{id}/presence` with 60s TTL index; `useTripPresence` heartbeat 10s + list 5s; `PresencePod` shows online avatars.
- Split expenses: `split_between` validated against accepted members; `GET /trips/{id}/debts` returns balances + minimum-cash-flow settlements.
- `POST /api/auth/dev-login-as` (ENV=dev) creates user + membership in one call for tests.

### Phase 3 (2026-02, verified 145/145 backend + all frontend)
- Hotels CRUD per stop (multipli supportati), inside StopCard with edit/delete on hover.
- Expenses CRUD tied to optional stop_id, defaults `paid_by` and `split_between` to current user (Phase 4 will expand to collaborators).
- Manual Exchange Rates (per-trip, owner-only upsert, viewer read). Unidirectional — no automatic inversion.
- Trip Summary aggregate endpoint: totals per bucket (hotels/attractions/expenses) in home_currency; items with missing rates are excluded and listed in `missing_rates` with affected item ids.
- Trip sub-header shows `Spend total` and an amber warning badge (with popover + CTA) when rates are missing; live refresh after any mutation including rate save/delete.
- Trip delete now cascades all 6 child collections (attractions, stops, hotels, expenses, exchange_rates, trip_members).
- Legacy data migration: `/app/backend/scripts/normalize_orders.py` renormalized pre-fix duplicate orders; idempotent.
- Refactor: `useDndReorder` hook + reusable `ConfirmDeleteDialog` extracted from Trip.jsx.

### Phase 2 (2026-02, verified 104/104 backend + all frontend, 0 orphans, 0 duplicate orders)
- Stops CRUD (create/list/patch/delete) with cascade on stop delete and full-permutation reorder.
- Attractions CRUD with atomic cross-stop reorder (computes canonical final layout in Python + single bulk_write).
- **Order canonicalization**: after every mutation (reorder, delete-attraction, delete-stop) orders are guaranteed contiguous 0..N-1 within each container; multi-item batch moves stay contiguous.
- Timeline UI with numbered stop bubbles, transport icon, KM chip between stops (placeholder), sticky trip sub-header with role badge and totals placeholders.
- @dnd-kit drag & drop for attractions: same-stop reorder + cross-stop move; optimistic UI with rollback on failure.
- Role-gated UI: viewer sees no edit buttons/drag handles.
- Global font swap to Sniglet (removed Instrument Serif + Sora). Localized Nunito override on Landing "Iberian Loop" title.
- Booking link scheme validation (server + client fed by 422).
- Trip delete now cascade-deletes attractions + stops + trip_members + trip.

## Backlog

### P0 (Phase 3)
- Hotels per stop: name, check_in/out (within stop range), price, currency, booking URL.
- Small dashboard for hotels inside `StopCard`.

### P1 (Phase 4)
- Collaborators: invite by email, roles editor/viewer, pending → accepted flow.
- Notification when invite is accepted.
- Trip export (PDF / shareable public read-only page).

### P2 (Phase 5)
- Expenses with automatic conversion to `home_currency` via `exchange_rates` collection (CoinGecko or Alpha Vantage integration).
- KM auto-calc via geocoding + routing (OpenRouteService or Mapbox).
- Map view with route polyline + stop pins.
- Profile page (change avatar, home_currency_default).

## Known limitations (non-blocking)
- `stops` order is not renormalized after a single-stop delete (gaps remain; cosmetic — timeline uses index-based numbering).
- Attractions reorder uses bulk_write without a Mongo session/transaction (safe under pre-validation; edge case only if crash mid-write).
- Trip.jsx is ~600 lines — split before Phase 4 (state + DnD logic).
- Native `<input type=date>` in modals — not shadcn Calendar (kept simple for now).

## Testing
- Regression suite: `/app/backend/tests/backend_test.py` (Phase 1, 23 tests) + `/app/backend/tests/phase2_test.py` (Phase 2 + fixes, 66 tests). All green. Run: `cd /app/backend && python -m pytest tests/ -v`.
- Orphan integrity check: `/app/test_reports/orphan_check.py`.
- Test credentials + auth playbook: `/app/memory/test_credentials.md`, `/app/memory/auth_testing.md`.

## Final Polish (Feb 2026)
- **Task 1 — ORS Live**: `ORS_MOCK=0` with production `ORS_API_KEY` in `/app/backend/.env`. Verified live (Barcelona → Madrid = 611.6 km). Note: free-tier ORS is rate-limited (HTTP 429 possible in preview); mock stays available via `ORS_MOCK=1`.
- **Task 2 — Dashboard summary**: `GET /api/trips` now returns per-trip `summary` `{ total_km, total_cost_home_currency, home_currency, has_missing_rates }` computed in bounded queries (1 trip_members + 1 trips + 5 batched children via `asyncio.gather` — no N+1). `TripCard.jsx` renders km with locale thousands separator (`— km` when null), cost via `Intl.NumberFormat` currency, and amber `AlertTriangle` + tooltip "Alcuni costi esclusi (tassi mancanti)" when rates missing.
- **Regression**: 241/241 backend tests pass (9 new in `tests/trip_summary_test.py`). Frontend Playwright verified all three states (full / missing / empty).
- **Cancelled**: Phase 6 (Emails + FX API). MVP delivered.

## Trip Map (Feb 2026)
- **New collection `route_cache`**: 30-day TTL, compound unique index on quantised coords (round 4 decimals) + transport_mode. Persists ORS Directions geometry to avoid re-hitting the rate-limited API.
- **New endpoint `GET /api/trips/{trip_id}/route-geometry`**: returns `{ stops: [{stop_id, order, title, location, transport_mode, coords, ...}], routes: [{from_stop_id, to_stop_id, transport_mode, geojson, distance_m, duration_s}] }`.
  - car/walk/train → ORS Directions (train uses driving-car), cache-through.
  - plane → NO ORS call, haversine only, `geojson=null` (frontend draws arc).
  - other → no ORS call, all null.
  - ORS timeout 4s; on failure `geojson=null`, falls back to `stops.km_from_prev * 1000` as distance if available.
- **Frontend `TripMap.jsx`** (lazy-loaded): shadcn Collapsible with `defaultOpen=true`, state persisted in `localStorage.tripmap-open-<tripId>`. Uses `react-leaflet` + OSM tiles.
  - Custom numbered `L.divIcon` markers (teal glass pill).
  - Legend chips per transport mode present.
  - Marker click → auto-scroll to `[data-testid=stop-card-<id>]` + popup with title/location/dates/"Go to stop" button.
  - Polyline click → popup with `From → To`, transport label, distance (Intl km) and duration (h m).
  - Plane routes render as bezier arcs computed locally (pink `#EC4899`).
  - Car teal, walk amber, train violet, plane pink; fallback = dashed color of the mode.
  - Auto fit-bounds on data change.
  - Legal OSM attribution kept visible (styled dark).
- **Bundle**: leaflet + react-leaflet added to package.json; lazy-loaded so it does not enter the Dashboard bundle.
