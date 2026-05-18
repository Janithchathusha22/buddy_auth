from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import MissingConfigError, get_settings
from app.models import (
    AppRole,
    ApprovalStatus,
    CourseCreateRequest,
    CourseListResponse,
    CourseResponse,
    CourseStudentAssignRequest,
    CourseUpdateRequest,
    CurrentUser,
    DashboardRedirectResponse,
    LessonCreateRequest,
    LessonListResponse,
    LessonProgressListResponse,
    LessonProgressResponse,
    LessonProgressUpsertRequest,
    LessonResponse,
    LessonUpdateRequest,
    QuizAttemptCreateRequest,
    QuizAttemptResponse,
    QuizCreateRequest,
    QuizListResponse,
    QuizResponse,
    QuizUpdateRequest,
    ROLE_GRANT_CLOSURE,
    RoleGrantRequest,
    RoleListResponse,
    UserApprovalRequest,
    UserDirectoryItem,
    UserDirectoryResponse,
    UserResponse,
)
from app.security import get_bearer_token, get_current_user, require_roles
from app.supabase_client import (
    SupabaseDataError,
    approve_user_profile,
    assign_student_to_course,
    create_course,
    create_lesson,
    create_quiz,
    create_quiz_attempt,
    delete_auth_user,
    delete_course,
    delete_lesson,
    delete_quiz,
    fetch_auth_user_by_id,
    fetch_auth_user_from_token,
    fetch_all_user_roles,
    fetch_course,
    fetch_lesson,
    fetch_profile,
    fetch_profiles,
    fetch_quiz,
    fetch_user_roles,
    is_student_assigned_to_course,
    list_all_progress,
    list_auth_users,
    list_assigned_courses,
    list_courses,
    list_lessons,
    list_quizzes,
    list_student_progress,
    sync_profile_from_auth_user,
    set_user_approval_status,
    set_user_active_status,
    update_course,
    update_lesson,
    update_quiz,
    upsert_lesson_progress,
    upsert_user_roles,
)
from app.supabase_client import OWNER_EMAIL


router = APIRouter()


def _user_response(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        auth_provider=user.auth_provider,
        requested_role=user.requested_role,
        approval_status=user.approval_status,
        is_active=user.is_active,
        roles=sorted(user.roles),
    )


def _admin_roles() -> set[AppRole]:
    return {AppRole.ADMIN, AppRole.SUPER_ADMIN}


def _dashboard_destination(roles: set[AppRole]) -> str:
    if AppRole.SUPER_ADMIN in roles:
        return "/super-admin"
    if AppRole.ADMIN in roles:
        return "/admin"
    if AppRole.STUDENT in roles:
        return "/student"
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User has no dashboard role",
    )


def _clean_payload(payload) -> dict:
    return payload.model_dump(exclude_none=True)


async def _settings():
    try:
        return get_settings()
    except MissingConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


async def _fetch_managed_auth_user(settings, user_id: UUID) -> dict:
    target_user = await fetch_auth_user_by_id(settings, user_id)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth user not found",
        )
    return target_user


def _auth_user_email(auth_user: dict) -> str:
    return (auth_user.get("email") or "").strip().lower()


def _is_bootstrap_owner(auth_user: dict) -> bool:
    return _auth_user_email(auth_user) == OWNER_EMAIL


def _ensure_not_protected_account(
    user_id: UUID,
    current_user: CurrentUser,
    target_user: dict,
    action: str,
) -> None:
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You cannot {action} your own super admin account",
        )

    if _is_bootstrap_owner(target_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The bootstrap owner account cannot be {action}",
        )


def _ensure_role_change_safe(
    user_id: UUID,
    current_user: CurrentUser,
    target_user: dict,
    role: AppRole,
) -> None:
    if role == AppRole.SUPER_ADMIN:
        return

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove super_admin from your own account",
        )

    if _is_bootstrap_owner(target_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The bootstrap owner account must stay super_admin",
        )


async def _ensure_course_access(
    course_id: UUID,
    user: CurrentUser,
    manage: bool = False,
) -> dict:
    settings = await _settings()
    try:
        course = await fetch_course(settings, course_id)
        if course is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        if user.has_any_role(_admin_roles()):
            return course

        if manage:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin or super_admin can manage course content",
            )

        if await is_student_assigned_to_course(settings, course_id, user.id):
            return course
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Course access denied",
    )


async def _ensure_lesson_access(
    lesson_id: UUID,
    user: CurrentUser,
    manage: bool = False,
) -> dict:
    settings = await _settings()
    try:
        lesson = await fetch_lesson(settings, lesson_id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found",
        )

    await _ensure_course_access(UUID(lesson["course_id"]), user, manage=manage)

    if not manage and not user.has_any_role(_admin_roles()) and not lesson["is_published"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lesson is not published",
        )

    return lesson


async def _ensure_quiz_access(
    quiz_id: UUID,
    user: CurrentUser,
    manage: bool = False,
) -> dict:
    settings = await _settings()
    try:
        quiz = await fetch_quiz(settings, quiz_id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if quiz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    await _ensure_lesson_access(UUID(quiz["lesson_id"]), user, manage=manage)
    return quiz


@router.get("/auth/me", response_model=UserResponse, tags=["auth"])
async def me(user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    return _user_response(user)


@router.get(
    "/dashboard/redirect",
    response_model=DashboardRedirectResponse,
    tags=["auth"],
)
async def dashboard_redirect(
    user: CurrentUser = Depends(get_current_user),
) -> DashboardRedirectResponse:
    return DashboardRedirectResponse(
        destination=_dashboard_destination(user.roles),
        roles=sorted(user.roles),
    )


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
        approval_status=profile.get("approval_status", "pending"),
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
@router.get(
    "/super-admin/users",
    response_model=UserDirectoryResponse,
    tags=["user management"],
)
async def list_users(
    _: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
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
                approval_status=profile.get("approval_status", "pending"),
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
    _: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
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


@router.post(
    "/super-admin/users/{user_id}/approve",
    response_model=RoleListResponse,
    tags=["user management"],
)
async def approve_user(
    user_id: UUID,
    payload: UserApprovalRequest,
    current_user: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> RoleListResponse:
    try:
        settings = get_settings()
        target_user = await _fetch_managed_auth_user(settings, user_id)
        _ensure_role_change_safe(user_id, current_user, target_user, payload.role)
        roles = await approve_user_profile(
            settings=settings,
            user_id=user_id,
            role=payload.role,
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


@router.post(
    "/super-admin/users/{user_id}/activate",
    tags=["user management"],
)
async def activate_user(
    user_id: UUID,
    _: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> dict[str, str | bool]:
    try:
        settings = get_settings()
        await set_user_active_status(settings, user_id, True)
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

    return {"user_id": str(user_id), "is_active": True}


@router.post(
    "/super-admin/users/{user_id}/deactivate",
    tags=["user management"],
)
async def deactivate_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> dict[str, str | bool]:
    try:
        settings = get_settings()
        target_user = await _fetch_managed_auth_user(settings, user_id)
        _ensure_not_protected_account(
            user_id,
            current_user,
            target_user,
            "deactivate",
        )
        await set_user_active_status(settings, user_id, False)
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

    return {"user_id": str(user_id), "is_active": False}


@router.post(
    "/super-admin/users/{user_id}/suspend",
    tags=["user management"],
)
async def suspend_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> dict[str, str | bool]:
    try:
        settings = get_settings()
        target_user = await _fetch_managed_auth_user(settings, user_id)
        _ensure_not_protected_account(
            user_id,
            current_user,
            target_user,
            "suspend",
        )
        await set_user_approval_status(
            settings,
            user_id,
            ApprovalStatus.SUSPENDED,
            False,
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

    return {"user_id": str(user_id), "approval_status": "suspended", "is_active": False}


@router.post(
    "/super-admin/users/{user_id}/reject",
    tags=["user management"],
)
async def reject_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> dict[str, str | bool]:
    try:
        settings = get_settings()
        target_user = await _fetch_managed_auth_user(settings, user_id)
        _ensure_not_protected_account(
            user_id,
            current_user,
            target_user,
            "reject",
        )
        await set_user_approval_status(
            settings,
            user_id,
            ApprovalStatus.REJECTED,
            False,
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

    return {"user_id": str(user_id), "approval_status": "rejected", "is_active": False}


@router.delete(
    "/super-admin/users/{user_id}",
    tags=["user management"],
)
async def delete_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_roles(AppRole.SUPER_ADMIN)),
) -> dict[str, str]:
    try:
        settings = get_settings()
        target_user = await _fetch_managed_auth_user(settings, user_id)
        _ensure_not_protected_account(user_id, current_user, target_user, "delete")
        await delete_auth_user(settings, user_id)
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

    return {"deleted_user_id": str(user_id)}


@router.get("/courses", response_model=CourseListResponse, tags=["lms"])
async def read_courses(
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> CourseListResponse:
    try:
        settings = await _settings()
        rows = (
            await list_courses(settings)
            if user.has_any_role(_admin_roles())
            else await list_assigned_courses(settings, user.id)
        )
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return CourseListResponse(courses=[CourseResponse(**row) for row in rows])


@router.post("/courses", response_model=CourseResponse, tags=["lms"])
async def add_course(
    payload: CourseCreateRequest,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> CourseResponse:
    try:
        settings = await _settings()
        row = await create_course(settings, _clean_payload(payload), user.id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return CourseResponse(**row)


@router.get("/courses/{course_id}", response_model=CourseResponse, tags=["lms"])
async def read_course(
    course_id: UUID,
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> CourseResponse:
    return CourseResponse(**await _ensure_course_access(course_id, user))


@router.patch("/courses/{course_id}", response_model=CourseResponse, tags=["lms"])
async def edit_course(
    course_id: UUID,
    payload: CourseUpdateRequest,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> CourseResponse:
    await _ensure_course_access(course_id, user, manage=True)
    try:
        settings = await _settings()
        row = await update_course(settings, course_id, _clean_payload(payload))
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return CourseResponse(**row)


@router.delete("/courses/{course_id}", tags=["lms"])
async def remove_course(
    course_id: UUID,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> dict[str, str]:
    await _ensure_course_access(course_id, user, manage=True)
    try:
        settings = await _settings()
        await delete_course(settings, course_id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return {"deleted": str(course_id)}


@router.post("/courses/{course_id}/students", tags=["lms"])
async def assign_course_student(
    course_id: UUID,
    payload: CourseStudentAssignRequest,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> dict:
    await _ensure_course_access(course_id, user, manage=True)
    try:
        settings = await _settings()
        return await assign_student_to_course(
            settings,
            course_id,
            payload.student_id,
            user.id,
        )
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/courses/{course_id}/lessons",
    response_model=LessonListResponse,
    tags=["lms"],
)
async def read_lessons(
    course_id: UUID,
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> LessonListResponse:
    await _ensure_course_access(course_id, user)
    try:
        settings = await _settings()
        rows = await list_lessons(
            settings,
            course_id,
            published_only=not user.has_any_role(_admin_roles()),
        )
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return LessonListResponse(lessons=[LessonResponse(**row) for row in rows])


@router.post(
    "/courses/{course_id}/lessons",
    response_model=LessonResponse,
    tags=["lms"],
)
async def add_lesson(
    course_id: UUID,
    payload: LessonCreateRequest,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> LessonResponse:
    await _ensure_course_access(course_id, user, manage=True)
    try:
        settings = await _settings()
        row = await create_lesson(settings, course_id, _clean_payload(payload), user.id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return LessonResponse(**row)


@router.patch("/lessons/{lesson_id}", response_model=LessonResponse, tags=["lms"])
async def edit_lesson(
    lesson_id: UUID,
    payload: LessonUpdateRequest,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> LessonResponse:
    await _ensure_lesson_access(lesson_id, user, manage=True)
    try:
        settings = await _settings()
        row = await update_lesson(settings, lesson_id, _clean_payload(payload))
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return LessonResponse(**row)


@router.delete("/lessons/{lesson_id}", tags=["lms"])
async def remove_lesson(
    lesson_id: UUID,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> dict[str, str]:
    await _ensure_lesson_access(lesson_id, user, manage=True)
    try:
        settings = await _settings()
        await delete_lesson(settings, lesson_id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return {"deleted": str(lesson_id)}


@router.get(
    "/lessons/{lesson_id}/quizzes",
    response_model=QuizListResponse,
    tags=["lms"],
)
async def read_quizzes(
    lesson_id: UUID,
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> QuizListResponse:
    await _ensure_lesson_access(lesson_id, user)
    try:
        settings = await _settings()
        rows = await list_quizzes(settings, lesson_id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return QuizListResponse(quizzes=[QuizResponse(**row) for row in rows])


@router.post(
    "/lessons/{lesson_id}/quizzes",
    response_model=QuizResponse,
    tags=["lms"],
)
async def add_quiz(
    lesson_id: UUID,
    payload: QuizCreateRequest,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> QuizResponse:
    await _ensure_lesson_access(lesson_id, user, manage=True)
    try:
        settings = await _settings()
        row = await create_quiz(settings, lesson_id, _clean_payload(payload), user.id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return QuizResponse(**row)


@router.patch("/quizzes/{quiz_id}", response_model=QuizResponse, tags=["lms"])
async def edit_quiz(
    quiz_id: UUID,
    payload: QuizUpdateRequest,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> QuizResponse:
    await _ensure_quiz_access(quiz_id, user, manage=True)
    try:
        settings = await _settings()
        row = await update_quiz(settings, quiz_id, _clean_payload(payload))
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return QuizResponse(**row)


@router.delete("/quizzes/{quiz_id}", tags=["lms"])
async def remove_quiz(
    quiz_id: UUID,
    user: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> dict[str, str]:
    await _ensure_quiz_access(quiz_id, user, manage=True)
    try:
        settings = await _settings()
        await delete_quiz(settings, quiz_id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return {"deleted": str(quiz_id)}


@router.put(
    "/lessons/{lesson_id}/progress",
    response_model=LessonProgressResponse,
    tags=["lms"],
)
async def save_lesson_progress(
    lesson_id: UUID,
    payload: LessonProgressUpsertRequest,
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> LessonProgressResponse:
    await _ensure_lesson_access(lesson_id, user)
    try:
        settings = await _settings()
        row = await upsert_lesson_progress(
            settings,
            lesson_id,
            user.id,
            _clean_payload(payload),
        )
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return LessonProgressResponse(**row)


@router.get(
    "/progress/me",
    response_model=LessonProgressListResponse,
    tags=["lms"],
)
async def read_my_progress(
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> LessonProgressListResponse:
    try:
        settings = await _settings()
        rows = await list_student_progress(settings, user.id)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return LessonProgressListResponse(
        progress=[LessonProgressResponse(**row) for row in rows]
    )


@router.get(
    "/admin/student-progress",
    response_model=LessonProgressListResponse,
    tags=["lms"],
)
async def read_student_progress(
    _: CurrentUser = Depends(require_roles(AppRole.ADMIN, AppRole.SUPER_ADMIN)),
) -> LessonProgressListResponse:
    try:
        settings = await _settings()
        rows = await list_all_progress(settings)
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return LessonProgressListResponse(
        progress=[LessonProgressResponse(**row) for row in rows]
    )


@router.post(
    "/quizzes/{quiz_id}/attempts",
    response_model=QuizAttemptResponse,
    tags=["lms"],
)
async def submit_quiz_attempt(
    quiz_id: UUID,
    payload: QuizAttemptCreateRequest,
    user: CurrentUser = Depends(
        require_roles(AppRole.STUDENT, AppRole.ADMIN, AppRole.SUPER_ADMIN)
    ),
) -> QuizAttemptResponse:
    await _ensure_quiz_access(quiz_id, user)
    try:
        settings = await _settings()
        row = await create_quiz_attempt(
            settings,
            quiz_id,
            user.id,
            _clean_payload(payload),
        )
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return QuizAttemptResponse(**row)
