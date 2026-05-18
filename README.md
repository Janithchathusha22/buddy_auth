# Buddy Auth

Buddy Auth is a Supabase Auth + FastAPI + Supabase Postgres authentication and authorization project for a learning platform.

It includes:

- FastAPI backend for token verification, profile sync, RBAC, user approval, and LMS APIs
- Supabase SQL schema with RLS, triggers, roles, profiles, courses, lessons, quizzes, progress, and attempts
- Standalone frontend test UI for signup, login, Google login, role checks, course tools, and super-admin approvals

## Tech Stack

| Area | Technology |
| --- | --- |
| Backend | Python 3.13, FastAPI, Uvicorn |
| Auth | Supabase Auth, Google OAuth through Supabase |
| Database | Supabase Postgres with Row Level Security |
| HTTP Client | HTTPX |
| Models | Pydantic v2 |
| JWT | PyJWT |
| Env | python-dotenv |
| Package Manager | uv |
| Frontend Test UI | HTML, CSS, JavaScript, Supabase JS CDN |

## Project Structure

```text
buddy-auth-api/
  app/
    main.py              FastAPI app, CORS, health route
    auth_routes.py       Auth sync, RBAC, super-admin user management, LMS APIs
    security.py          Bearer token validation and role dependencies
    supabase_client.py   Supabase Auth and PostgREST HTTP integration
    models.py            Roles, request models, response models
    config.py            Environment-based settings
  docs/
    full-supabase-setup.sql
    auth-rbac.md
    developer-handoff-prompt.md
  frontend/
    index.html           Standalone auth dashboard
    config.js            Public Supabase URL/key and backend URL
    run-ui.ps1           Local static server helper
  .env.example
  pyproject.toml
  uv.lock
```

## Roles

Only three roles are used:

| Role | Meaning |
| --- | --- |
| `student` | Learner account |
| `admin` | Course, lesson, quiz, content, and student-progress manager |
| `super_admin` | System owner and user/role manager |

There is no separate `teacher` role. In this project, `admin` performs teacher/admin duties.

Role hierarchy:

| Approved As | Stored Roles |
| --- | --- |
| `student` | `student` |
| `admin` | `student`, `admin` |
| `super_admin` | `student`, `admin`, `super_admin` |

## Signup and Approval Rules

- Any user can sign up.
- New public signups are created as `pending`.
- Every new signup gets only the real role `student`.
- `requested_role` from the frontend is only a request, not permission.
- Pending, rejected, suspended, or inactive users cannot enter protected app routes.
- Only `super_admin` can approve users, reject users, suspend users, delete users, or create another `super_admin`.
- `admin` can manage learning content but cannot approve users.
- The bootstrap owner email is `danu@absolx.com`.
- When that owner account exists in Supabase Auth, it is approved and receives `student + admin + super_admin`.
- Passwords are never stored in SQL or Git. Supabase Auth owns passwords.

## Supabase Setup

Run this single SQL file in Supabase SQL Editor:

```text
docs/full-supabase-setup.sql
```

This creates:

- `public.app_role`
- `public.approval_status`
- `public.course_status`
- `public.lesson_progress_status`
- `public.profiles`
- `public.user_roles`
- `public.courses`
- `public.course_students`
- `public.lessons`
- `public.quizzes`
- `public.lesson_progress`
- `public.quiz_attempts`
- triggers for new users and `updated_at`
- helper functions
- RLS policies
- owner bootstrap/backfill logic

## Backend Environment

Create `.env` from `.env.example`:

```powershell
cd D:\buddy2\buddy-auth-api
copy .env.example .env
```

Fill real values:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-or-publishable-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=
SUPABASE_JWT_AUDIENCE=authenticated
CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174
```

Security notes:

- Never commit `.env`.
- Never expose `SUPABASE_SERVICE_ROLE_KEY` in frontend code.
- Rotate keys if a secret was shared in chat, screenshots, GitHub, or frontend files.

## Run Backend

```powershell
cd D:\buddy2\buddy-auth-api
uv sync
uv run uvicorn app.main:app --reload
```

Backend URLs:

```text
API:  http://127.0.0.1:8000
Docs: http://127.0.0.1:8000/docs
```

Health check:

```http
GET /
```

## Run Frontend Test UI

Edit `frontend/config.js` and keep only public frontend-safe values:

```js
export const SUPABASE_URL = "https://your-project-ref.supabase.co";
export const SUPABASE_ANON_KEY = "your-public-anon-or-publishable-key";
export const BACKEND_URL = "http://127.0.0.1:8000";
```

Run:

```powershell
cd D:\buddy2\buddy-auth-api\frontend
.\run-ui.ps1
```

Open:

```text
http://127.0.0.1:5174
```

## Google OAuth Setup

Supabase:

1. Go to Authentication -> Providers -> Google.
2. Enable Google.
3. Add your Google OAuth Web Client ID.
4. Add the matching Google OAuth Client Secret.

Current Web Client ID used during development:

```text
265685837645-sniif4ph5apapfv0s7k1cgfmtisnebuq.apps.googleusercontent.com
```

Google Cloud OAuth client:

Authorized JavaScript origins:

```text
http://127.0.0.1:5174
http://localhost:5174
```

Authorized redirect URI:

```text
https://qooonyufrtwgxfbfiacg.supabase.co/auth/v1/callback
```

Supabase Authentication -> URL Configuration:

```text
Site URL:
http://127.0.0.1:5174

Redirect URLs:
http://127.0.0.1:5174
http://127.0.0.1:5174/
http://localhost:5174
http://localhost:5174/
```

Common OAuth errors:

| Error | Fix |
| --- | --- |
| `Unsupported provider: provider is not enabled` | Enable Google provider in Supabase |
| `invalid_client` | Use the real Google Web Client ID and matching secret |
| `redirect_uri_mismatch` | Add the exact Supabase callback URL in Google Cloud |

## API Endpoints

All protected endpoints require:

```http
Authorization: Bearer <supabase-access-token>
```

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| `GET` | `/` | Public | Health check |
| `POST` | `/auth/sync` | Authenticated Supabase user | Sync Supabase Auth identity into app profile |
| `GET` | `/auth/me` | Approved active user | Current profile and roles |
| `GET` | `/dashboard/redirect` | Approved active user | Return `/super-admin`, `/admin`, or `/student` |
| `GET` | `/student` | `student`, `admin`, `super_admin` | Student access check |
| `GET` | `/admin` | `admin`, `super_admin` | Admin access check |
| `GET` | `/super-admin` | `super_admin` | Super-admin access check |
| `GET` | `/super-admin/users` | `super_admin` | List auth users with profiles and roles |
| `GET` | `/super-admin/users/{user_id}/roles` | `super_admin` | Read one user's roles |
| `POST` | `/super-admin/users/{user_id}/roles` | `super_admin` | Replace role hierarchy |
| `POST` | `/super-admin/users/{user_id}/approve` | `super_admin` | Approve as student/admin/super_admin |
| `POST` | `/super-admin/users/{user_id}/reject` | `super_admin` | Reject user |
| `POST` | `/super-admin/users/{user_id}/suspend` | `super_admin` | Suspend and deactivate user |
| `POST` | `/super-admin/users/{user_id}/activate` | `super_admin` | Activate approved user |
| `POST` | `/super-admin/users/{user_id}/deactivate` | `super_admin` | Deactivate user |
| `DELETE` | `/super-admin/users/{user_id}` | `super_admin` | Delete user except self/bootstrap owner |
| `GET` | `/courses` | `student`, `admin`, `super_admin` | Students see assigned courses; admins see all |
| `POST` | `/courses` | `admin`, `super_admin` | Create course |
| `PATCH` | `/courses/{course_id}` | `admin`, `super_admin` | Edit course |
| `DELETE` | `/courses/{course_id}` | `admin`, `super_admin` | Delete course |
| `POST` | `/courses/{course_id}/students` | `admin`, `super_admin` | Assign student to course |
| `GET` | `/courses/{course_id}/lessons` | `student`, `admin`, `super_admin` | List lessons |
| `POST` | `/courses/{course_id}/lessons` | `admin`, `super_admin` | Create lesson |
| `PATCH` | `/lessons/{lesson_id}` | `admin`, `super_admin` | Edit lesson |
| `DELETE` | `/lessons/{lesson_id}` | `admin`, `super_admin` | Delete lesson |
| `GET` | `/lessons/{lesson_id}/quizzes` | `student`, `admin`, `super_admin` | List quizzes |
| `POST` | `/lessons/{lesson_id}/quizzes` | `admin`, `super_admin` | Create quiz |
| `PATCH` | `/quizzes/{quiz_id}` | `admin`, `super_admin` | Edit quiz |
| `DELETE` | `/quizzes/{quiz_id}` | `admin`, `super_admin` | Delete quiz |
| `PUT` | `/lessons/{lesson_id}/progress` | `student`, `admin`, `super_admin` | Save own progress |
| `GET` | `/progress/me` | `student`, `admin`, `super_admin` | View own progress |
| `POST` | `/quizzes/{quiz_id}/attempts` | `student`, `admin`, `super_admin` | Submit quiz attempt |
| `GET` | `/admin/student-progress` | `admin`, `super_admin` | View student progress |

## Development Checks

```powershell
cd D:\buddy2\buddy-auth-api
uv run python -m compileall app
uv run python -c "from app.main import app; print([route.path for route in app.routes])"
git status --short
```

## Git Push

This repository is intended to push backend and frontend together:

```powershell
cd D:\buddy2\buddy-auth-api
git add .
git commit -m "Update Buddy auth backend and frontend"
git branch -M main
git remote add origin https://github.com/Janithchathusha22/buddy_auth.git
git push -u origin main
```

If `origin` already exists, use:

```powershell
git remote set-url origin https://github.com/Janithchathusha22/buddy_auth.git
git push -u origin main
```

## Production Notes

- Keep authorization in backend and Supabase RLS.
- Do not trust frontend role dropdowns.
- Keep service role key backend-only.
- Use HTTPS in production.
- Restrict CORS to real frontend domains.
- Keep only the three roles: `student`, `admin`, `super_admin`.
