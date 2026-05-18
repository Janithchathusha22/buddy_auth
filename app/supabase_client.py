from typing import Any
from uuid import UUID
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.models import AppRole, ApprovalStatus, ROLE_GRANT_CLOSURE


OWNER_EMAIL = "danu@absolx.com"


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


def _is_owner_email(email: str | None) -> bool:
    return (email or "").strip().lower() == OWNER_EMAIL


PROFILE_SELECT = "id,full_name,avatar_url,auth_provider,requested_role,approval_status,is_active"


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
        "select": PROFILE_SELECT,
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
        "select": f"{PROFILE_SELECT},created_at,updated_at",
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

    is_owner = _is_owner_email(auth_user.get("email"))
    requested_role = (
        AppRole.SUPER_ADMIN
        if is_owner
        else _normalize_requested_role(metadata.get("requested_role"))
    )

    payload = {
        "id": user_id,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "auth_provider": auth_provider,
        "requested_role": requested_role.value,
    }

    if is_owner:
        payload["approval_status"] = ApprovalStatus.APPROVED.value
        payload["is_active"] = True

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

    if is_owner:
        await upsert_user_roles(
            settings=settings,
            user_id=UUID(user_id),
            roles=ROLE_GRANT_CLOSURE[AppRole.SUPER_ADMIN],
            granted_by=UUID(user_id),
        )
    else:
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


async def fetch_auth_user_by_id(
    settings: Settings,
    user_id: UUID,
) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.auth_issuer}/admin/users/{user_id}",
            headers=_service_headers(settings),
        )

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        raise SupabaseDataError("Failed to load auth user from Supabase")

    return response.json()


async def delete_auth_user(settings: Settings, user_id: UUID) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.delete(
            f"{settings.auth_issuer}/admin/users/{user_id}",
            headers=_service_headers(settings),
        )

    if response.status_code not in {200, 204}:
        raise SupabaseDataError("Failed to delete auth user from Supabase")


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


async def replace_user_roles(
    settings: Settings,
    user_id: UUID,
    roles: set[AppRole],
    granted_by: UUID,
) -> set[AppRole]:
    async with httpx.AsyncClient(timeout=10) as client:
        delete_response = await client.delete(
            f"{settings.supabase_url}/rest/v1/user_roles",
            headers=_service_headers(settings) | {"Prefer": "return=minimal"},
            params={"user_id": f"eq.{user_id}"},
        )

    if delete_response.status_code not in {200, 204}:
        raise SupabaseDataError("Failed to replace existing user roles in Supabase")

    return await upsert_user_roles(
        settings=settings,
        user_id=user_id,
        roles=roles,
        granted_by=granted_by,
    )


async def approve_user_profile(
    settings: Settings,
    user_id: UUID,
    role: AppRole,
    granted_by: UUID,
) -> set[AppRole]:
    headers = _service_headers(settings) | {
        "Prefer": "return=minimal",
    }

    payload = {
        "requested_role": role.value,
        "approval_status": "approved",
        "is_active": True,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{settings.supabase_url}/rest/v1/profiles",
            headers=headers,
            params={"id": f"eq.{user_id}"},
            json=payload,
        )

    if response.status_code not in {200, 204}:
        raise SupabaseDataError("Failed to approve user profile in Supabase")

    return await replace_user_roles(
        settings=settings,
        user_id=user_id,
        roles=ROLE_GRANT_CLOSURE[role],
        granted_by=granted_by,
    )


async def set_user_active_status(
    settings: Settings,
    user_id: UUID,
    is_active: bool,
) -> None:
    headers = _service_headers(settings) | {
        "Prefer": "return=minimal",
    }
    payload = {
        "is_active": is_active,
        "approval_status": "approved" if is_active else "suspended",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{settings.supabase_url}/rest/v1/profiles",
            headers=headers,
            params={"id": f"eq.{user_id}"},
            json=payload,
        )

    if response.status_code not in {200, 204}:
        raise SupabaseDataError("Failed to update user active status in Supabase")


async def set_user_approval_status(
    settings: Settings,
    user_id: UUID,
    approval_status: ApprovalStatus,
    is_active: bool,
) -> None:
    headers = _service_headers(settings) | {
        "Prefer": "return=minimal",
    }
    payload = {
        "approval_status": approval_status.value,
        "is_active": is_active,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{settings.supabase_url}/rest/v1/profiles",
            headers=headers,
            params={"id": f"eq.{user_id}"},
            json=payload,
        )

    if response.status_code not in {200, 204}:
        raise SupabaseDataError("Failed to update user approval status in Supabase")


def _uuid(value: Any) -> UUID | None:
    return UUID(value) if value else None


async def _get_rows(
    settings: Settings,
    table: str,
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.supabase_url}/rest/v1/{table}",
            headers=_service_headers(settings),
            params=params or {},
        )

    if response.status_code != 200:
        raise SupabaseDataError(f"Failed to load {table} from Supabase")

    return response.json()


async def _insert_row(
    settings: Settings,
    table: str,
    payload: dict[str, Any],
    on_conflict: str | None = None,
) -> dict[str, Any]:
    headers = _service_headers(settings) | {
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    params = {"on_conflict": on_conflict} if on_conflict else None

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.supabase_url}/rest/v1/{table}",
            headers=headers,
            params=params,
            json=payload,
        )

    if response.status_code not in {200, 201}:
        raise SupabaseDataError(f"Failed to insert {table} row in Supabase")

    rows = response.json()
    return rows[0] if rows else payload


async def _patch_row(
    settings: Settings,
    table: str,
    row_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers = _service_headers(settings) | {"Prefer": "return=representation"}

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{settings.supabase_url}/rest/v1/{table}",
            headers=headers,
            params={"id": f"eq.{row_id}"},
            json=payload,
        )

    if response.status_code not in {200, 204}:
        raise SupabaseDataError(f"Failed to update {table} row in Supabase")

    rows = response.json()
    if not rows:
        raise SupabaseDataError(f"No {table} row was updated in Supabase")

    return rows[0]


async def _delete_row(settings: Settings, table: str, row_id: UUID) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.delete(
            f"{settings.supabase_url}/rest/v1/{table}",
            headers=_service_headers(settings) | {"Prefer": "return=minimal"},
            params={"id": f"eq.{row_id}"},
        )

    if response.status_code not in {200, 204}:
        raise SupabaseDataError(f"Failed to delete {table} row in Supabase")


async def list_courses(settings: Settings) -> list[dict[str, Any]]:
    return await _get_rows(settings, "courses", {"select": "*", "order": "created_at.desc"})


async def list_assigned_courses(settings: Settings, student_id: UUID) -> list[dict[str, Any]]:
    assignments = await _get_rows(
        settings,
        "course_students",
        {"student_id": f"eq.{student_id}", "select": "course_id"},
    )
    course_ids = [row["course_id"] for row in assignments]
    if not course_ids:
        return []

    return await _get_rows(
        settings,
        "courses",
        {
            "id": f"in.({','.join(course_ids)})",
            "select": "*",
            "order": "created_at.desc",
        },
    )


async def fetch_course(settings: Settings, course_id: UUID) -> dict[str, Any] | None:
    rows = await _get_rows(
        settings,
        "courses",
        {"id": f"eq.{course_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


async def create_course(
    settings: Settings,
    payload: dict[str, Any],
    created_by: UUID,
) -> dict[str, Any]:
    return await _insert_row(
        settings,
        "courses",
        payload | {"created_by": str(created_by)},
    )


async def update_course(
    settings: Settings,
    course_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await _patch_row(settings, "courses", course_id, payload)


async def delete_course(settings: Settings, course_id: UUID) -> None:
    await _delete_row(settings, "courses", course_id)


async def assign_student_to_course(
    settings: Settings,
    course_id: UUID,
    student_id: UUID,
    assigned_by: UUID,
) -> dict[str, Any]:
    return await _insert_row(
        settings,
        "course_students",
        {
            "course_id": str(course_id),
            "student_id": str(student_id),
            "assigned_by": str(assigned_by),
        },
        on_conflict="course_id,student_id",
    )


async def is_student_assigned_to_course(
    settings: Settings,
    course_id: UUID,
    student_id: UUID,
) -> bool:
    rows = await _get_rows(
        settings,
        "course_students",
        {
            "course_id": f"eq.{course_id}",
            "student_id": f"eq.{student_id}",
            "select": "course_id",
            "limit": "1",
        },
    )
    return bool(rows)


async def list_lessons(
    settings: Settings,
    course_id: UUID,
    published_only: bool = False,
) -> list[dict[str, Any]]:
    params = {
        "course_id": f"eq.{course_id}",
        "select": "*",
        "order": "sort_order.asc,created_at.asc",
    }
    if published_only:
        params["is_published"] = "eq.true"

    return await _get_rows(settings, "lessons", params)


async def fetch_lesson(settings: Settings, lesson_id: UUID) -> dict[str, Any] | None:
    rows = await _get_rows(
        settings,
        "lessons",
        {"id": f"eq.{lesson_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


async def create_lesson(
    settings: Settings,
    course_id: UUID,
    payload: dict[str, Any],
    created_by: UUID,
) -> dict[str, Any]:
    return await _insert_row(
        settings,
        "lessons",
        payload | {"course_id": str(course_id), "created_by": str(created_by)},
    )


async def update_lesson(
    settings: Settings,
    lesson_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await _patch_row(settings, "lessons", lesson_id, payload)


async def delete_lesson(settings: Settings, lesson_id: UUID) -> None:
    await _delete_row(settings, "lessons", lesson_id)


async def list_quizzes(settings: Settings, lesson_id: UUID) -> list[dict[str, Any]]:
    return await _get_rows(
        settings,
        "quizzes",
        {"lesson_id": f"eq.{lesson_id}", "select": "*", "order": "created_at.asc"},
    )


async def fetch_quiz(settings: Settings, quiz_id: UUID) -> dict[str, Any] | None:
    rows = await _get_rows(
        settings,
        "quizzes",
        {"id": f"eq.{quiz_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


async def create_quiz(
    settings: Settings,
    lesson_id: UUID,
    payload: dict[str, Any],
    created_by: UUID,
) -> dict[str, Any]:
    return await _insert_row(
        settings,
        "quizzes",
        payload | {"lesson_id": str(lesson_id), "created_by": str(created_by)},
    )


async def update_quiz(
    settings: Settings,
    quiz_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await _patch_row(settings, "quizzes", quiz_id, payload)


async def delete_quiz(settings: Settings, quiz_id: UUID) -> None:
    await _delete_row(settings, "quizzes", quiz_id)


async def upsert_lesson_progress(
    settings: Settings,
    lesson_id: UUID,
    student_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    progress_payload = payload | {
        "lesson_id": str(lesson_id),
        "student_id": str(student_id),
    }

    if payload.get("status") == "completed":
        progress_payload["completed_at"] = datetime.now(timezone.utc).isoformat()

    return await _insert_row(
        settings,
        "lesson_progress",
        progress_payload,
        on_conflict="student_id,lesson_id",
    )


async def list_student_progress(
    settings: Settings,
    student_id: UUID,
) -> list[dict[str, Any]]:
    return await _get_rows(
        settings,
        "lesson_progress",
        {"student_id": f"eq.{student_id}", "select": "*", "order": "updated_at.desc"},
    )


async def list_all_progress(settings: Settings) -> list[dict[str, Any]]:
    return await _get_rows(
        settings,
        "lesson_progress",
        {"select": "*", "order": "updated_at.desc"},
    )


async def create_quiz_attempt(
    settings: Settings,
    quiz_id: UUID,
    student_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await _insert_row(
        settings,
        "quiz_attempts",
        payload | {"quiz_id": str(quiz_id), "student_id": str(student_id)},
    )
