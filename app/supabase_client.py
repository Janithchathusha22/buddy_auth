from typing import Any
from uuid import UUID

import httpx

from app.config import Settings
from app.models import AppRole


class SupabaseAuthError(RuntimeError):
    pass


class SupabaseDataError(RuntimeError):
    pass


def _service_headers(settings: Settings) -> dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _normalize_requested_role(value: str | None) -> AppRole:
    if value in {role.value for role in AppRole}:
        return AppRole(value)

    return AppRole.STUDENT


async def fetch_auth_user_from_token(
    token: str,
    settings: Settings,
) -> dict[str, Any]:
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{settings.auth_issuer}/user", headers=headers)

    if response.status_code != 200:
        raise SupabaseAuthError("Invalid Supabase access token")

    return response.json()


async def validate_token_with_auth_server(
    token: str,
    settings: Settings,
) -> dict[str, Any]:
    user = await fetch_auth_user_from_token(token, settings)
    return {
        "sub": user.get("id"),
        "email": user.get("email"),
        "role": "authenticated",
        "user_metadata": user.get("user_metadata") or {},
        "app_metadata": user.get("app_metadata") or {},
    }


async def fetch_profile(settings: Settings, user_id: UUID) -> dict[str, Any] | None:
    params = {
        "id": f"eq.{user_id}",
        "select": "id,full_name,avatar_url,auth_provider,requested_role,is_active",
        "limit": "1",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.supabase_url}/rest/v1/profiles",
            headers=_service_headers(settings),
            params=params,
        )

    if response.status_code != 200:
        raise SupabaseDataError("Failed to load profile from Supabase")

    rows = response.json()
    return rows[0] if rows else None


async def fetch_user_roles(settings: Settings, user_id: UUID) -> set[AppRole]:
    params = {
        "user_id": f"eq.{user_id}",
        "select": "role",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.supabase_url}/rest/v1/user_roles",
            headers=_service_headers(settings),
            params=params,
        )

    if response.status_code != 200:
        raise SupabaseDataError("Failed to load user roles from Supabase")

    roles: set[AppRole] = set()
    for row in response.json():
        roles.add(AppRole(row["role"]))

    return roles


async def fetch_profiles(settings: Settings) -> dict[str, dict[str, Any]]:
    params = {
        "select": "id,full_name,avatar_url,auth_provider,requested_role,is_active,created_at,updated_at",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.supabase_url}/rest/v1/profiles",
            headers=_service_headers(settings),
            params=params,
        )

    if response.status_code != 200:
        raise SupabaseDataError("Failed to load profiles from Supabase")

    return {row["id"]: row for row in response.json()}


async def fetch_all_user_roles(settings: Settings) -> dict[str, set[AppRole]]:
    params = {
        "select": "user_id,role",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.supabase_url}/rest/v1/user_roles",
            headers=_service_headers(settings),
            params=params,
        )

    if response.status_code != 200:
        raise SupabaseDataError("Failed to load user roles from Supabase")

    roles_by_user: dict[str, set[AppRole]] = {}
    for row in response.json():
        roles_by_user.setdefault(row["user_id"], set()).add(AppRole(row["role"]))

    return roles_by_user


async def sync_profile_from_auth_user(
    settings: Settings,
    auth_user: dict[str, Any],
) -> dict[str, Any]:
    user_id = auth_user.get("id")
    if not user_id:
        raise SupabaseDataError("Supabase auth user response is missing id")

    metadata = auth_user.get("user_metadata") or {}
    app_metadata = auth_user.get("app_metadata") or {}
    full_name = (
        metadata.get("full_name")
        or metadata.get("name")
        or metadata.get("display_name")
        or auth_user.get("email")
    )
    avatar_url = metadata.get("avatar_url") or metadata.get("picture")
    auth_provider = app_metadata.get("provider")
    if not auth_provider and app_metadata.get("providers"):
        auth_provider = app_metadata["providers"][0]

    requested_role = _normalize_requested_role(metadata.get("requested_role"))

    payload = {
        "id": user_id,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "auth_provider": auth_provider,
        "requested_role": requested_role.value,
    }

    headers = _service_headers(settings) | {
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.supabase_url}/rest/v1/profiles",
            headers=headers,
            params={"on_conflict": "id"},
            json=payload,
        )

    if response.status_code not in {200, 201}:
        raise SupabaseDataError("Failed to sync profile from Supabase auth user")

    await ensure_student_role(settings, UUID(user_id))
    rows = response.json()
    return rows[0] if rows else payload


async def ensure_student_role(settings: Settings, user_id: UUID) -> None:
    headers = _service_headers(settings) | {
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.supabase_url}/rest/v1/user_roles",
            headers=headers,
            params={"on_conflict": "user_id,role"},
            json={"user_id": str(user_id), "role": AppRole.STUDENT.value},
        )

    if response.status_code not in {200, 201, 204}:
        raise SupabaseDataError("Failed to ensure default student role")


async def list_auth_users(settings: Settings) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.auth_issuer}/admin/users",
            headers=_service_headers(settings),
            params={"page": "1", "per_page": "1000"},
        )

    if response.status_code != 200:
        raise SupabaseDataError("Failed to load auth users from Supabase")

    payload = response.json()
    if isinstance(payload, list):
        return payload

    users = payload.get("users", [])
    if not isinstance(users, list):
        raise SupabaseDataError("Unexpected Supabase auth users response")

    return users


async def upsert_user_roles(
    settings: Settings,
    user_id: UUID,
    roles: set[AppRole],
    granted_by: UUID,
) -> set[AppRole]:
    payload = [
        {
            "user_id": str(user_id),
            "role": role.value,
            "granted_by": str(granted_by),
        }
        for role in sorted(roles)
    ]

    headers = _service_headers(settings) | {
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.supabase_url}/rest/v1/user_roles",
            headers=headers,
            params={"on_conflict": "user_id,role"},
            json=payload,
        )

    if response.status_code not in {200, 201}:
        raise SupabaseDataError("Failed to grant user role in Supabase")

    return await fetch_user_roles(settings, user_id)
