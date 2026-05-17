# Buddy Auth API

FastAPI backend for Supabase Auth, profile synchronization, and database-backed role-based access control.

This service is designed to sit behind a frontend that authenticates users with Supabase Auth. The frontend sends the Supabase access token to this API. The API verifies the token, loads the application profile and roles from Supabase Postgres, and enforces role access at the backend route level.

## Tech Stack

- Python 3.13
- FastAPI
- Uvicorn
- HTTPX
- Pydantic v2
- PyJWT with cryptography support
- python-dotenv
- Supabase Auth
- Supabase Postgres with Row Level Security
- uv for dependency management

## Package Dependencies

The runtime dependencies are declared in `pyproject.toml`:

| Package | Purpose |
| --- | --- |
| `fastapi` | API framework and dependency-based authorization |
| `uvicorn` | ASGI development server |
| `httpx` | Async HTTP calls to Supabase Auth and PostgREST APIs |
| `pydantic` | Request and response schemas |
| `pyjwt[crypto]` | Supabase JWT verification through HS256 or JWKS-backed algorithms |
| `python-dotenv` | Local environment variable loading |

## Architecture

```text
Frontend
  |
  | Supabase email/password or Google login
  v
Supabase Auth
  |
  | access_token
  v
FastAPI Backend
  |
  | verifies token
  | syncs profile
  | reads roles
  v
Supabase Postgres
  |
  | profiles
  | user_roles
  v
Backend RBAC response
```

Core modules:

| File | Responsibility |
| --- | --- |
| `app/main.py` | FastAPI app creation, CORS, router registration, health route |
| `app/auth_routes.py` | Auth sync, current-user route, RBAC example routes, admin user/role endpoints |
| `app/security.py` | Bearer token extraction, Supabase JWT validation, current-user dependency, role guard dependency |
| `app/supabase_client.py` | Supabase Auth and PostgREST integration through HTTPX |
| `app/models.py` | Role enum, role grant rules, API request/response models |
| `app/config.py` | Environment-driven settings |
| `docs/auth-rbac.sql` | Production-safe Supabase schema, RLS policies, triggers, and default role setup |
| `docs/demo-public-role-selection.sql` | Demo-only SQL for allowing the frontend role dropdown to create elevated roles |
| `docs/auth-rbac.md` | RBAC design notes |
| `docs/developer-handoff-prompt.md` | English handoff prompt for another developer |

## Role Model

The application supports three roles:

| Role | Meaning |
| --- | --- |
| `student` | Normal learning user |
| `admin` | User, course, or content management user |
| `super_admin` | System owner with full role-management access |

Role hierarchy:

| User Type | Stored Roles |
| --- | --- |
| Normal signup | `student` |
| Admin | `student`, `admin` |
| Super Admin | `student`, `admin`, `super_admin` |

Access rules:

| Page or API Area | Allowed Roles |
| --- | --- |
| Student area | `student`, `admin`, `super_admin` |
| Admin area | `admin`, `super_admin` |
| Super admin area | `super_admin` |

The frontend may use the returned `roles` array to show or hide navigation, but security must remain in the backend and Supabase RLS. Never trust a frontend dropdown or local state as authorization.

## Supabase Database Design

Tables:

| Table | Purpose |
| --- | --- |
| `auth.users` | Supabase-managed login identity |
| `public.profiles` | Application profile data such as name, provider, avatar, requested role, and active status |
| `public.user_roles` | Many-to-many role assignments for each user |

`docs/auth-rbac.sql` creates:

- `public.app_role` enum
- `public.profiles`
- `public.user_roles`
- indexes
- RLS policies
- helper functions for role checks
- `handle_new_user()` trigger for automatic profile creation
- default `student` role assignment for new users
- backfill logic for existing Supabase Auth users

Production behavior:

- Public signup creates a profile and grants only `student`.
- `requested_role` is stored for review, but it is not trusted as an actual role.
- Higher roles must be granted by a trusted backend flow.

Demo behavior:

- `docs/demo-public-role-selection.sql` changes the trigger so the frontend selected role becomes the actual role.
- This is useful for learning and UI testing.
- Do not use the demo SQL in production.

## Environment Variables

Create a local `.env` file from `.env.example`:

```powershell
copy .env.example .env
```

Required variables:

| Variable | Required | Notes |
| --- | --- | --- |
| `SUPABASE_URL` | Yes | Supabase project URL, for example `https://project-ref.supabase.co` |
| `SUPABASE_ANON_KEY` | Yes | Public anon or publishable key used to validate user tokens through Supabase Auth |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Backend-only service role key used for profile and role reads/writes |
| `SUPABASE_JWT_SECRET` | Optional | Only needed for local HS256 JWT verification; leave empty to validate HS256 tokens through Supabase Auth |
| `SUPABASE_JWT_AUDIENCE` | Optional | Defaults to `authenticated` |
| `CORS_ORIGINS` | Optional | Comma-separated frontend origins |

Security rules:

- Never expose `SUPABASE_SERVICE_ROLE_KEY` in frontend code.
- Never commit a real `.env` file.
- Rotate keys if they were shared publicly.

## Setup

1. Install uv.
2. Configure the Supabase database by running `docs/auth-rbac.sql` in the Supabase SQL Editor.
3. Copy `.env.example` to `.env`.
4. Fill in the real Supabase values.
5. Start the API.

```powershell
cd D:\buddy2\buddy-auth-api
uv sync
uv run uvicorn app.main:app --reload
```

Default local API URL:

```text
http://127.0.0.1:8000
```

Interactive API docs:

```text
http://127.0.0.1:8000/docs
```

Health check:

```http
GET /
```

Response:

```json
{
  "status": "ok",
  "service": "buddy-auth-api"
}
```

## Frontend Integration

The frontend should:

1. Authenticate with Supabase Auth.
2. Read `session.access_token`.
3. Send that token to this backend as a bearer token.
4. Call `POST /auth/sync` after login/signup/OAuth redirect.
5. Call `GET /auth/me` to load the current app profile and roles.

Authorization header:

```http
Authorization: Bearer <supabase-access-token>
```

Example JavaScript:

```js
const response = await fetch("http://127.0.0.1:8000/auth/me", {
  headers: {
    Authorization: `Bearer ${session.access_token}`,
  },
});
```

## Google OAuth Notes

Google login is configured in Supabase and Google Cloud, not in this backend.

Supabase Google provider:

- Authentication -> Providers -> Google
- Enable Google
- Add the real Google OAuth Web Client ID
- Add the matching Google OAuth Client Secret

Google Cloud OAuth client:

- Application type: Web application
- Authorized JavaScript origins:

```text
http://127.0.0.1:5174
http://localhost:5174
```

- Authorized redirect URI:

```text
https://<project-ref>.supabase.co/auth/v1/callback
```

For this project ref:

```text
https://qooonyufrtwgxfbfiacg.supabase.co/auth/v1/callback
```

Common errors:

| Error | Meaning | Fix |
| --- | --- | --- |
| `Unsupported provider: provider is not enabled` | Google provider is not enabled in Supabase | Enable Google and save provider settings |
| `Error 401: invalid_client` | Google Client ID or Client Secret is wrong or fake | Use a real Google Cloud OAuth Web Client ID and matching secret |
| `redirect_uri_mismatch` | Callback URL is not registered in Google Cloud | Add the exact Supabase callback URL |

## API Endpoints

All protected endpoints require:

```http
Authorization: Bearer <supabase-access-token>
```

| Method | Path | Auth Required | Roles | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/` | No | Public | Health check |
| `POST` | `/auth/sync` | Yes | Any authenticated Supabase user | Sync Supabase Auth identity into `profiles`, ensure default `student` role, return current app user |
| `GET` | `/auth/me` | Yes | Any active user with at least one role | Return current app profile and roles |
| `GET` | `/student` | Yes | `student`, `admin`, `super_admin` | Student-access example route |
| `GET` | `/admin` | Yes | `admin`, `super_admin` | Admin-access example route |
| `GET` | `/super-admin` | Yes | `super_admin` | Super-admin-only example route |
| `GET` | `/admin/users` | Yes | `admin`, `super_admin` | List Supabase Auth users with app profiles and roles |
| `GET` | `/admin/users/{user_id}/roles` | Yes | `admin`, `super_admin` | Read roles for a user |
| `POST` | `/super-admin/users/{user_id}/roles` | Yes | `super_admin` | Grant a role hierarchy to a user |

## Response Models

`UserResponse`:

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "Saman Perera",
  "avatar_url": "https://example.com/avatar.png",
  "auth_provider": "google",
  "requested_role": "admin",
  "is_active": true,
  "roles": ["student", "admin"]
}
```

`RoleGrantRequest`:

```json
{
  "role": "admin"
}
```

Role grant behavior:

| Requested Grant | Roles Written |
| --- | --- |
| `student` | `student` |
| `admin` | `student`, `admin` |
| `super_admin` | `student`, `admin`, `super_admin` |

## Development Checks

Compile check:

```powershell
uv run python -m compileall app
```

List routes:

```powershell
uv run python -c "from app.main import app; print([route.path for route in app.routes])"
```

Check git status:

```powershell
git status --short
```

## Production Notes

- Keep role grants server-side.
- Use the production-safe `docs/auth-rbac.sql`.
- Do not run `docs/demo-public-role-selection.sql` in production.
- Keep the service role key only on the backend.
- Use HTTPS outside local development.
- Restrict `CORS_ORIGINS` to real frontend domains.
- Prefer Supabase asymmetric JWT signing keys where possible.
- Keep Supabase RLS enabled.

## Developer Handoff Summary

This backend verifies Supabase Auth tokens and maps them to application roles stored in Supabase Postgres. Supabase Auth owns login identity. `profiles` owns application profile data. `user_roles` owns actual authorization. The frontend can request a role during signup, but in production that value is stored only as `requested_role`; actual elevated roles must be granted by a trusted backend route.

For a full handoff prompt, see `docs/developer-handoff-prompt.md`.
