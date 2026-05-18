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
| `app/auth_routes.py` | Auth sync, current-user route, RBAC routes, super-admin user approval, LMS endpoints |
| `app/security.py` | Bearer token extraction, Supabase JWT validation, current-user dependency, role guard dependency |
| `app/supabase_client.py` | Supabase Auth and PostgREST integration through HTTPX |
| `app/models.py` | Role enum, role grant rules, API request/response models |
| `app/config.py` | Environment-driven settings |
| `docs/full-supabase-setup.sql` | Complete Supabase schema, RLS policies, triggers, owner bootstrap, and LMS tables |
| `docs/auth-rbac.sql` | Same production SQL kept for compatibility |
| `docs/lms-learning-schema.sql` | Note that LMS schema is now included in the full setup SQL |
| `docs/auth-rbac.md` | RBAC design notes |
| `docs/developer-handoff-prompt.md` | English handoff prompt for another developer |

## Role Model

The application supports three roles:

| Role | Meaning |
| --- | --- |
| `student` | Normal learning user |
| `admin` | Course, lesson, quiz, and student-progress management user |
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

`docs/full-supabase-setup.sql` creates:

- `public.app_role` enum
- `public.profiles`
- `public.user_roles`
- LMS tables for courses, course assignments, lessons, quizzes, progress, and quiz attempts
- indexes
- RLS policies
- helper functions for role checks
- `handle_new_user()` trigger for automatic profile creation
- default `student` role assignment for new users
- backfill logic for existing Supabase Auth users

Production behavior:

- Public signup creates a profile, grants only `student`, and keeps the profile `pending`.
- `requested_role` is stored for review, but it is not trusted as an actual role.
- Higher roles and approvals must be granted by a trusted super-admin backend flow.

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
2. Configure the Supabase database by running `docs/full-supabase-setup.sql` in the Supabase SQL Editor.
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
- Add the real Google OAuth Web Client ID:

```text
636044689877-itm8g0g9n0d740ss11pd3p3oom2gc827.apps.googleusercontent.com
```

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

Do not commit the Google OAuth client secret or Supabase service role key.

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
| `GET` | `/dashboard/redirect` | Yes | Approved active user | Return `/super-admin`, `/admin`, or `/student` based on highest role |
| `GET` | `/student` | Yes | `student`, `admin`, `super_admin` | Student-access example route |
| `GET` | `/admin` | Yes | `admin`, `super_admin` | Admin-access example route |
| `GET` | `/super-admin` | Yes | `super_admin` | Super-admin-only example route |
| `GET` | `/super-admin/users` | Yes | `super_admin` | List Supabase Auth users with app profiles and roles |
| `GET` | `/admin/users` | Yes | `super_admin` | Compatibility alias for user list |
| `GET` | `/admin/users/{user_id}/roles` | Yes | `super_admin` | Read roles for a user |
| `POST` | `/super-admin/users/{user_id}/roles` | Yes | `super_admin` | Grant a role hierarchy to a user |
| `POST` | `/super-admin/users/{user_id}/approve` | Yes | `super_admin` | Approve a user as `student`, `admin`, or `super_admin` |
| `POST` | `/super-admin/users/{user_id}/reject` | Yes | `super_admin` | Reject a pending user |
| `POST` | `/super-admin/users/{user_id}/suspend` | Yes | `super_admin` | Suspend and deactivate a user |
| `POST` | `/super-admin/users/{user_id}/activate` | Yes | `super_admin` | Activate an approved user |
| `POST` | `/super-admin/users/{user_id}/deactivate` | Yes | `super_admin` | Deactivate and suspend a user |
| `DELETE` | `/super-admin/users/{user_id}` | Yes | `super_admin` | Delete a Supabase Auth user except self or bootstrap owner |
| `GET` | `/courses` | Yes | `student`, `admin`, `super_admin` | Students see assigned courses; admins see all courses |
| `POST` | `/courses` | Yes | `admin`, `super_admin` | Create course |
| `PATCH` | `/courses/{course_id}` | Yes | `admin`, `super_admin` | Edit course |
| `DELETE` | `/courses/{course_id}` | Yes | `admin`, `super_admin` | Delete course |
| `POST` | `/courses/{course_id}/students` | Yes | `admin`, `super_admin` | Assign student to course |
| `GET` | `/courses/{course_id}/lessons` | Yes | `student`, `admin`, `super_admin` | Students see published lessons only |
| `POST` | `/courses/{course_id}/lessons` | Yes | `admin`, `super_admin` | Create lesson |
| `PATCH` | `/lessons/{lesson_id}` | Yes | `admin`, `super_admin` | Edit lesson |
| `DELETE` | `/lessons/{lesson_id}` | Yes | `admin`, `super_admin` | Delete lesson |
| `POST` | `/lessons/{lesson_id}/quizzes` | Yes | `admin`, `super_admin` | Create quiz |
| `PATCH` | `/quizzes/{quiz_id}` | Yes | `admin`, `super_admin` | Edit quiz |
| `DELETE` | `/quizzes/{quiz_id}` | Yes | `admin`, `super_admin` | Delete quiz |
| `PUT` | `/lessons/{lesson_id}/progress` | Yes | `student`, `admin`, `super_admin` | Save own lesson progress |
| `POST` | `/quizzes/{quiz_id}/attempts` | Yes | `student`, `admin`, `super_admin` | Submit own quiz attempt |
| `GET` | `/admin/student-progress` | Yes | `admin`, `super_admin` | View student progress |

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
  "approval_status": "approved",
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

Approval behavior:

| User | Signup Result | App Access |
| --- | --- | --- |
| Normal student | `approval_status = pending`, role `student` | Blocked until approved |
| Admin request | `approval_status = pending`, role `student`, `requested_role = admin` | Blocked until approved and granted `admin` |
| `danu@absolx.com` | `approval_status = approved`, roles `student`, `admin`, `super_admin` | Full access after Supabase Auth account exists |

Approve a user from Supabase SQL Editor:

```sql
select public.approve_user_by_email('student@example.com', 'student');
select public.approve_user_by_email('admin@example.com', 'admin');
select public.approve_user_by_email('owner@example.com', 'super_admin');
```

The LMS database tables and RLS policies are included in `docs/full-supabase-setup.sql`.

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
- Use the production-safe `docs/full-supabase-setup.sql`.
- Keep the service role key only on the backend.
- Use HTTPS outside local development.
- Restrict `CORS_ORIGINS` to real frontend domains.
- Prefer Supabase asymmetric JWT signing keys where possible.
- Keep Supabase RLS enabled.

## Developer Handoff Summary

This backend verifies Supabase Auth tokens and maps them to application roles stored in Supabase Postgres. Supabase Auth owns login identity. `profiles` owns application profile data. `user_roles` owns actual authorization. The frontend can request a role during signup, but in production that value is stored only as `requested_role`; actual elevated roles must be granted by a trusted backend route.

For a full handoff prompt, see `docs/developer-handoff-prompt.md`.
