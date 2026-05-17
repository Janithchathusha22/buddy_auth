# Developer Handoff Prompt

Use this prompt when handing the project to another developer or asking an AI coding agent to continue development.

```text
You are taking over the Buddy Auth API project.

Project type:
- Python 3.13 FastAPI backend
- Supabase Auth for identity
- Supabase Postgres for profiles and database-backed RBAC
- uv for dependency management

Business goal:
Build and maintain a backend auth service that supports normal students, admins, and super admins. The frontend authenticates users with Supabase Auth and sends the Supabase access token to the backend. The backend verifies the token, syncs basic auth identity data into application tables, reads actual roles from the database, and enforces route-level permissions.

Core architecture:
- Supabase Auth `auth.users` stores login accounts.
- `public.profiles` stores application profile fields: full name, avatar URL, auth provider, requested role, active status, timestamps.
- `public.user_roles` stores actual roles as rows: `student`, `admin`, `super_admin`.
- A normal signup should receive only the real role `student`.
- `requested_role` is user-supplied metadata and must not be trusted as authorization in production.
- Admin users should have `student + admin`.
- Super admins should have `student + admin + super_admin`.

Important files:
- `app/main.py`: FastAPI app, CORS, routers, health check.
- `app/auth_routes.py`: `/auth/sync`, `/auth/me`, RBAC examples, admin user and role routes.
- `app/security.py`: bearer token extraction, Supabase JWT verification, current-user dependency, role guard dependency.
- `app/supabase_client.py`: HTTPX integration with Supabase Auth and PostgREST.
- `app/models.py`: roles, role grant hierarchy, Pydantic request/response models.
- `app/config.py`: environment settings.
- `docs/auth-rbac.sql`: production-safe Supabase database schema, RLS policies, triggers, and backfills.
- `docs/demo-public-role-selection.sql`: demo-only SQL that allows frontend role selection to become actual roles.
- `.env.example`: required backend environment variables.
- `README.md`: setup, endpoints, architecture, and operational notes.

Endpoints:
- `GET /`: public health check.
- `POST /auth/sync`: authenticated user sync after login/signup/OAuth.
- `GET /auth/me`: current profile and actual roles.
- `GET /student`: allowed for student, admin, super_admin.
- `GET /admin`: allowed for admin, super_admin.
- `GET /super-admin`: allowed for super_admin only.
- `GET /admin/users`: list auth users with profiles and roles, allowed for admin and super_admin.
- `GET /admin/users/{user_id}/roles`: read roles for a user, allowed for admin and super_admin.
- `POST /super-admin/users/{user_id}/roles`: grant role hierarchy, allowed for super_admin only.

Environment requirements:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- optional `SUPABASE_JWT_SECRET`
- optional `SUPABASE_JWT_AUDIENCE`
- optional `CORS_ORIGINS`

Security constraints:
- Never expose `SUPABASE_SERVICE_ROLE_KEY` in frontend code.
- Do not trust frontend-selected roles.
- Keep Supabase RLS enabled.
- Use backend dependencies to enforce route permissions.
- In production, use `docs/auth-rbac.sql`, not the demo SQL.

Current known development context:
- A separate simple frontend can use Supabase Auth and then call this backend with the Supabase access token.
- Google OAuth must be configured in Supabase and Google Cloud using the real Google OAuth Web Client ID and Client Secret.
- The Supabase callback URL for this project is:
  `https://qooonyufrtwgxfbfiacg.supabase.co/auth/v1/callback`

Before making changes:
- Read the README and all files under `app/`.
- Verify whether the project is using production-safe SQL or demo SQL.
- Run `uv run python -m compileall app`.
- Keep changes scoped and do not commit real `.env` secrets.
```
