from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import MissingConfigError, get_settings
from app.models import (
    AppRole,
    CurrentUser,
    ROLE_GRANT_CLOSURE,
    RoleGrantRequest,
    RoleListResponse,
    UserDirectoryItem,
    UserDirectoryResponse,
    UserResponse,
)
from app.security import get_bearer_token, get_current_user, require_roles
from app.supabase_client import (
    SupabaseDataError,
    fetch_auth_user_from_token,
    fetch_all_user_roles,
    fetch_profile,
    fetch_profiles,
    fetch_user_roles,
    list_auth_users,
    sync_profile_from_auth_user,
    upsert_user_roles,
)


router = APIRouter()


def _user_response(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        auth_provider=user.auth_provider,
        requested_role=user.requested_role,
        is_active=user.is_active,
        roles=sorted(user.roles),
    )


@router.get("/auth/me", response_model=UserResponse, tags=["auth"])
async def me(user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    return _user_response(user)


@router.post("/auth/sync", response_model=UserResponse, tags=["auth"])
async def sync_authenticated_user(
    token: str = Depends(get_bearer_token),
) -> UserResponse:
    try:
        settings = get_settings()
        auth_user = await fetch_auth_user_from_token(token, settings)
        user_id = UUID(auth_user["id"])
        await sync_profile_from_auth_user(settings, auth_user)
        profile = await fetch_profile(settings, user_id)
        roles = await fetch_user_roles(settings, user_id)
    except MissingConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase auth user",
        ) from exc
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Profile sync did not create a profile",
        )

    return UserResponse(
        id=user_id,
        email=auth_user.get("email"),
        full_name=profile.get("full_name"),
        avatar_url=profile.get("avatar_url"),
        auth_provider=profile.get("auth_provider"),
        requested_role=profile.get("requested_role"),
        is_active=profile.get("is_active", True),
        roles=sorted(roles),
    )


@router.get("/student", response_model=UserResponse, tags=["rbac examples"])
async def student_page(
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> UserResponse:
    return _user_response(user)


@router.get("/admin", response_model=UserResponse, tags=["rbac examples"])
async def admin_page(
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> UserResponse:
    return _user_response(user)


@router.get("/super-admin", response_model=UserResponse, tags=["rbac examples"])
async def super_admin_page(
    user: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> UserResponse:
    return _user_response(user)


@router.get(
    "/admin/users",
    response_model=UserDirectoryResponse,
    tags=["user management"],
)
async def list_users(
    _: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> UserDirectoryResponse:
    try:
        settings = get_settings()
        auth_users = await list_auth_users(settings)
        profiles = await fetch_profiles(settings)
        roles_by_user = await fetch_all_user_roles(settings)
    except MissingConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    users: list[UserDirectoryItem] = []
    for auth_user in auth_users:
        user_id = auth_user.get("id")
        if not user_id:
            continue

        profile = profiles.get(user_id, {})
        users.append(
            UserDirectoryItem(
                id=UUID(user_id),
                email=auth_user.get("email"),
                full_name=profile.get("full_name"),
                avatar_url=profile.get("avatar_url"),
                auth_provider=profile.get("auth_provider"),
                requested_role=profile.get("requested_role"),
                is_active=profile.get("is_active", False),
                roles=sorted(roles_by_user.get(user_id, set())),
                created_at=auth_user.get("created_at"),
                last_sign_in_at=auth_user.get("last_sign_in_at"),
                email_confirmed_at=auth_user.get("email_confirmed_at"),
            )
        )

    users.sort(key=lambda item: item.email or str(item.id))
    return UserDirectoryResponse(users=users)


@router.get(
    "/admin/users/{user_id}/roles",
    response_model=RoleListResponse,
    tags=["user management"],
)
async def read_user_roles(
    user_id: UUID,
    _: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> RoleListResponse:
    try:
        settings = get_settings()
        roles = await fetch_user_roles(settings, user_id)
    except MissingConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return RoleListResponse(user_id=user_id, roles=sorted(roles))


@router.post(
    "/super-admin/users/{user_id}/roles",
    response_model=RoleListResponse,
    tags=["user management"],
)
async def grant_user_role(
    user_id: UUID,
    payload: RoleGrantRequest,
    current_user: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> RoleListResponse:
    roles_to_grant = ROLE_GRANT_CLOSURE[payload.role]

    try:
        settings = get_settings()
        roles = await upsert_user_roles(
            settings=settings,
            user_id=user_id,
            roles=roles_to_grant,
            granted_by=current_user.id,
        )
    except MissingConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return RoleListResponse(user_id=user_id, roles=sorted(roles))
