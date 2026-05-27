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
- `public.profiles` stores application profile fields: full name, avatar URL, auth provider, requested role, approval status, active status, `last_seen_at`, and timestamps.
- `public.user_roles` stores actual roles as rows: `student`, `admin`, `super_admin`.
- A normal signup should receive only the real role `student` and should remain `pending` until approved.
- `requested_role` is user-supplied metadata and must not be trusted as authorization in production.
- Admin users should have `student + admin`.
- Super admins should have `student + admin + super_admin`.
- The default owner email is `danu@absolx.com`; the password must be managed in Supabase Auth, not stored in SQL or Git.

Important files:
- `app/main.py`: FastAPI app, CORS, routers, health check.
- `app/auth_routes.py`: `/auth/sync`, `/auth/me`, RBAC examples, super-admin user approval routes, and LMS routes.
- `app/presence.py`: online/offline threshold helpers.
- `app/presence_routes.py`: `/auth/heartbeat` endpoint that updates `profiles.last_seen_at`.
- `app/security.py`: bearer token extraction, Supabase JWT verification, current-user dependency, role guard dependency.
- `app/supabase_client.py`: HTTPX integration with Supabase Auth and PostgREST.
- `app/models.py`: roles, role grant hierarchy, Pydantic request/response models.
- `app/config.py`: environment settings.
- `docs/full-supabase-setup.sql`: production-safe Supabase database schema, RLS policies, triggers, owner bootstrap, and LMS tables.
- `docs/add-presence-last-seen.sql`: one-time migration for existing databases that need `profiles.last_seen_at`.
- `.env.example`: required backend environment variables.
- `frontend/index.html`: standalone test UI for signup/login, Google login, role checks, course tools, and super-admin approvals.
- `frontend/config.js`: public frontend configuration only.
- `README.md`: setup, endpoints, architecture, and operational notes.

Endpoints:
- `GET /`: public health check.
- `POST /auth/sync`: authenticated user sync after login/signup/OAuth.
- `POST /auth/heartbeat`: update current user's `last_seen_at` for online/offline dashboard presence.
- `GET /auth/me`: current profile and actual roles.
- `GET /student`: allowed for student, admin, super_admin.
- `GET /admin`: allowed for admin, super_admin.
- `GET /super-admin`: allowed for super_admin only.
- `GET /super-admin/users`: list auth users with profiles and roles, allowed for super_admin only.
- `GET /super-admin/users/{user_id}/roles`: read roles for a user, allowed for super_admin only.
- `POST /super-admin/users/{user_id}/approve`: approve a user as student, admin, or super_admin.
- `POST /super-admin/users/{user_id}/roles`: replace role hierarchy, allowed for super_admin only.
- LMS routes include course create/edit/delete, lesson create/edit/delete, quiz create/edit/delete, course student assignment, progress save, quiz attempt submit, and admin progress viewing.

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
- Block application access until `approval_status = approved`.
- In production, use `docs/full-supabase-setup.sql`.

Current known development context:
- The repository includes a simple frontend under `frontend/`.
- Google OAuth must be configured in Supabase and Google Cloud using the real Google OAuth Web Client ID and Client Secret.
- The Supabase callback URL for this project is:
  `https://qooonyufrtwgxfbfiacg.supabase.co/auth/v1/callback`

Before making changes:
- Read the README and all files under `app/`.
- Verify that the project is using the production-safe three-role SQL.
- Run `uv run python -m compileall app`.
- Keep changes scoped and do not commit real `.env` secrets.
```
