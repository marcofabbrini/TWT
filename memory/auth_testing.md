# TWT — Auth Testing Playbook

App uses **Emergent-managed Google Auth** with httpOnly cookie sessions on web.

## Cookie name
`twt_session` (configurable via `SESSION_COOKIE_NAME` env var)

## Testing options

### Option A — Dev login endpoint (recommended for automated tests)
An endpoint `POST /api/auth/dev-login` is active **only when `ENV=dev`** in `/app/backend/.env`. It creates or upserts a user by email and issues a session cookie in one call.

```bash
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
curl -c /tmp/twt_cookie.txt -X POST "$API_URL/api/auth/dev-login" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@twt.app","name":"Alice Test"}'

# Verify session
curl -b /tmp/twt_cookie.txt "$API_URL/api/auth/me"
```

The response also returns `session_token` which can be used as `Authorization: Bearer <token>` if cookies are inconvenient.

### Option B — Browser (Playwright)
Seed a session directly in Mongo, then set the cookie:

```javascript
await page.context.addCookies([{
  name: "twt_session",
  value: "<session_token from mongo>",
  domain: new URL(process.env.REACT_APP_BACKEND_URL).hostname,
  path: "/",
  httpOnly: true,
  secure: true,
  sameSite: "None"
}]);
await page.goto(`${process.env.REACT_APP_BACKEND_URL}/dashboard`);
```

Or just navigate to landing and call `POST /api/auth/dev-login` from the page context.

### Option C — Real Google OAuth
Frontend button on `/` redirects the browser to `https://auth.emergentagent.com/?redirect=<origin>/dashboard`. After Google login, user comes back with `#session_id=<id>`; the frontend AuthCallback route posts to `POST /api/auth/session` which sets the cookie.

## Endpoints summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | /api/auth/google/login?redirect=... | none | 302 redirect to Emergent auth |
| POST | /api/auth/session | none | Exchange session_id → cookie |
| GET | /api/auth/me | cookie/Bearer | Current user |
| POST | /api/auth/logout | cookie/Bearer | Clear session |
| POST | /api/auth/dev-login | none (dev only) | Fake login for tests |
| POST | /api/trips | cookie/Bearer | Create trip |
| GET | /api/trips | cookie/Bearer | List trips (all where user is member) |
| GET | /api/trips/{trip_id} | cookie/Bearer | Trip detail (membership required) |
| DELETE | /api/trips/{trip_id} | cookie/Bearer | Owner-only hard delete |

## Isolation check
Create two users via dev-login, create a trip as A, list trips as B — B must NOT see A's trip.

```bash
curl -c /tmp/a.txt -X POST "$API_URL/api/auth/dev-login" -H "Content-Type: application/json" -d '{"email":"a@twt.app"}'
curl -b /tmp/a.txt -X POST "$API_URL/api/trips" -H "Content-Type: application/json" \
  -d '{"title":"A trip","home_currency":"EUR","start_date":"2026-05-01","end_date":"2026-05-10"}'

curl -c /tmp/b.txt -X POST "$API_URL/api/auth/dev-login" -H "Content-Type: application/json" -d '{"email":"b@twt.app"}'
curl -b /tmp/b.txt "$API_URL/api/trips"   # must return []
```
