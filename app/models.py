from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AppRole(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class PresenceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"


ROLE_GRANT_CLOSURE: dict[AppRole, set[AppRole]] = {
    AppRole.STUDENT: {AppRole.STUDENT},
    AppRole.ADMIN: {AppRole.STUDENT, AppRole.ADMIN},
    AppRole.SUPER_ADMIN: {AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN},
}


class CourseStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class LessonProgressStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class CurrentUser(BaseModel):
    id: UUID
    email: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    auth_provider: str | None = None
    requested_role: AppRole | None = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    is_active: bool = True
    last_seen_at: str | None = None
    presence_status: PresenceStatus = PresenceStatus.OFFLINE
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
    approval_status: ApprovalStatus
    is_active: bool
    last_seen_at: str | None = None
    presence_status: PresenceStatus = PresenceStatus.OFFLINE
    roles: list[AppRole]


class RoleGrantRequest(BaseModel):
    role: AppRole


class UserApprovalRequest(BaseModel):
    role: AppRole


class RoleListResponse(BaseModel):
    user_id: UUID
    roles: list[AppRole]


class PresenceHeartbeatResponse(BaseModel):
    user_id: UUID
    last_seen_at: str
    presence_status: PresenceStatus


class UserDirectoryItem(BaseModel):
    id: UUID
    email: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    auth_provider: str | None = None
    requested_role: AppRole | None = None
    approval_status: ApprovalStatus
    is_active: bool
    last_seen_at: str | None = None
    presence_status: PresenceStatus = PresenceStatus.OFFLINE
    roles: list[AppRole]
    created_at: str | None = None
    last_sign_in_at: str | None = None
    email_confirmed_at: str | None = None


class UserDirectoryResponse(BaseModel):
    users: list[UserDirectoryItem]


class DashboardRedirectResponse(BaseModel):
    destination: str
    roles: list[AppRole]


class CourseCreateRequest(BaseModel):
    title: str
    description: str | None = None
    status: CourseStatus = CourseStatus.DRAFT


class CourseUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: CourseStatus | None = None


class CourseResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    status: CourseStatus
    created_by: UUID | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CourseListResponse(BaseModel):
    courses: list[CourseResponse]


class CourseStudentAssignRequest(BaseModel):
    student_id: UUID


class LessonCreateRequest(BaseModel):
    title: str
    content: str | None = None
    sort_order: int = 0
    is_published: bool = False


class LessonUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    sort_order: int | None = None
    is_published: bool | None = None


class LessonResponse(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    content: str | None = None
    sort_order: int
    is_published: bool
    created_by: UUID | None = None
    created_at: str | None = None
    updated_at: str | None = None


class LessonListResponse(BaseModel):
    lessons: list[LessonResponse]


class QuizCreateRequest(BaseModel):
    title: str
    instructions: str | None = None
    max_score: float = 100


class QuizUpdateRequest(BaseModel):
    title: str | None = None
    instructions: str | None = None
    max_score: float | None = None


class QuizResponse(BaseModel):
    id: UUID
    lesson_id: UUID
    title: str
    instructions: str | None = None
    max_score: float
    created_by: UUID | None = None
    created_at: str | None = None
    updated_at: str | None = None


class QuizListResponse(BaseModel):
    quizzes: list[QuizResponse]


class LessonProgressUpsertRequest(BaseModel):
    status: LessonProgressStatus = LessonProgressStatus.IN_PROGRESS
    progress_percent: int = Field(default=0, ge=0, le=100)


class LessonProgressResponse(BaseModel):
    student_id: UUID
    lesson_id: UUID
    status: LessonProgressStatus
    progress_percent: int
    completed_at: str | None = None
    updated_at: str | None = None


class LessonProgressListResponse(BaseModel):
    progress: list[LessonProgressResponse]


class QuizAttemptCreateRequest(BaseModel):
    score: float | None = None
    answers: dict[str, Any] = Field(default_factory=dict)


class QuizAttemptResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    student_id: UUID
    score: float | None = None
    answers: dict[str, Any]
    submitted_at: str


class QuizAttemptListResponse(BaseModel):
    attempts: list[QuizAttemptResponse]
