from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class AppRole(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


ROLE_GRANT_CLOSURE: dict[AppRole, set[AppRole]] = {
    AppRole.STUDENT: {AppRole.STUDENT},
    AppRole.ADMIN: {AppRole.STUDENT, AppRole.ADMIN},
    AppRole.SUPER_ADMIN: {AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN},
}


class CurrentUser(BaseModel):
    id: UUID
    email: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    auth_provider: str | None = None
    requested_role: AppRole | None = None
    is_active: bool = True
    roles: set[AppRole] = Field(default_factory=set)

    def has_any_role(self, allowed_roles: set[AppRole]) -> bool:
        return bool(self.roles.intersection(allowed_roles))


class UserResponse(BaseModel):
    id: UUID
    email: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    auth_provider: str | None = None
    requested_role: AppRole | None = None
    is_active: bool
    roles: list[AppRole]


class RoleGrantRequest(BaseModel):
    role: AppRole


class RoleListResponse(BaseModel):
    user_id: UUID
    roles: list[AppRole]


class UserDirectoryItem(BaseModel):
    id: UUID
    email: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    auth_provider: str | None = None
    requested_role: AppRole | None = None
    is_active: bool
    roles: list[AppRole]
    created_at: str | None = None
    last_sign_in_at: str | None = None
    email_confirmed_at: str | None = None


class UserDirectoryResponse(BaseModel):
    users: list[UserDirectoryItem]
