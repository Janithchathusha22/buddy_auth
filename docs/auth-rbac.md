# Auth and RBAC Design

## Rule

The frontend can show or hide menu items, but it must not be the security layer.
The security decision lives in two places:

1. Supabase Postgres RLS for direct database access.
2. FastAPI dependencies for API endpoints.

## Tables

- `auth.users`: Supabase login identity.
- `profiles`: application profile data such as `full_name`, `approval_status`, and `is_active`.
- `user_roles`: many-to-many role assignment for `student`, `admin`, and `super_admin`.

Normal signup receives `student`.
Admin users should have `student + admin`.
The system owner should have `student + admin + super_admin`.

New student/admin signups are `pending` until approved. The default system owner
email is `danu@absolx.com`; once that Supabase Auth user exists, the SQL seeds
`approved + student + admin + super_admin`.

## Access Matrix

| Page | Allowed roles |
| --- | --- |
| Student page | `student`, `admin`, `super_admin` |
| Admin page | `admin`, `super_admin` |
| Super Admin page | `super_admin` |

## Frontend Usage

The frontend should call `GET /auth/me` with the Supabase access token:

```http
Authorization: Bearer <supabase-access-token>
```

Use the returned `roles` only for navigation and UX. A hidden button is not
security. Every sensitive API route still checks roles in the backend.

Never put these values in frontend/public environment variables:

- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`

## Backend Usage

Protected endpoints are implemented with FastAPI dependencies:

- `GET /student`
- `GET /admin`
- `GET /super-admin`
- `GET /super-admin/users`
- `GET /super-admin/users/{user_id}/roles`
- `POST /super-admin/users/{user_id}/approve`
- `POST /super-admin/users/{user_id}/roles`

The API verifies the Supabase access token, loads the user's profile and roles
from Supabase, checks `approval_status = approved` and `is_active`, and then
applies route-level RBAC.

`POST /auth/sync` is used after email/password login or Google login. It verifies
the Supabase token, copies basic Google/Supabase Auth identity data into
`profiles`, and ensures the user has the default `student` role.

## Supabase Setup

Run `docs/full-supabase-setup.sql` in the Supabase SQL editor.

Then configure `.env` from `.env.example`.

Prefer asymmetric JWT signing keys in Supabase. With asymmetric keys, the API
can verify tokens with the Supabase JWKS endpoint. If the project still uses
HS256, the API can validate the token through the Supabase Auth server; local
HS256 verification with `SUPABASE_JWT_SECRET` is supported but should be treated
as a secret-management risk.
