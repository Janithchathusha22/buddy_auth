# Buddy Auth Frontend

Standalone test UI for Supabase signup, email login, Google login, backend token sync, role checks, admin course tools, and super-admin user approvals.

This is intentionally simple HTML/JavaScript so the auth flow is easy to inspect while learning. It is not a production React app yet.

## Run

Start the backend first:

```powershell
cd D:\buddy2\buddy-auth-api
uv run uvicorn app.main:app --reload
```

Start the frontend:

```powershell
cd D:\buddy2\buddy-auth-api\frontend
.\run-ui.ps1
```

Open:

```text
http://127.0.0.1:5174
```

## Configuration

Edit `config.js`:

```js
export const SUPABASE_URL = "https://your-project-ref.supabase.co";
export const SUPABASE_ANON_KEY = "your-public-anon-or-publishable-key";
export const BACKEND_URL = "http://127.0.0.1:8000";
```

Only use the public Supabase anon/publishable key here. Never put `SUPABASE_SERVICE_ROLE_KEY` in frontend code.

## Auth Flow

1. The user signs up or logs in through Supabase Auth.
2. Supabase returns a browser session with `access_token`.
3. The frontend sends the token to `POST /auth/sync`.
4. The backend verifies the token, syncs `profiles`, reads `user_roles`, and returns actual app access.
5. Pending, rejected, suspended, or inactive users are blocked by the backend.

## Google Login

Configure Google in Supabase and Google Cloud:

Google Cloud authorized redirect URI:

```text
https://qooonyufrtwgxfbfiacg.supabase.co/auth/v1/callback
```

Google Cloud authorized JavaScript origins:

```text
http://127.0.0.1:5174
http://localhost:5174
```

Supabase URL configuration:

```text
Site URL: http://127.0.0.1:5174
Redirect URLs:
http://127.0.0.1:5174
http://127.0.0.1:5174/
http://localhost:5174
http://localhost:5174/
```

The frontend sends only a requested role. Actual roles are assigned by the backend after super-admin approval.
