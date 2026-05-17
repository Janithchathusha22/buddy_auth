from functools import lru_cache
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import InvalidTokenError, PyJWKClient

from app.config import MissingConfigError, Settings, get_settings
from app.models import AppRole, CurrentUser
from app.supabase_client import (
    SupabaseAuthError,
    SupabaseDataError,
    fetch_profile,
    fetch_user_roles,
    validate_token_with_auth_server,
)


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


async def verify_supabase_jwt(token: str, settings: Settings) -> dict:
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise _unauthorized("Invalid bearer token") from exc

    algorithm = header.get("alg")
    if algorithm == "HS256":
        if settings.supabase_jwt_secret:
            try:
                return jwt.decode(
                    token,
                    settings.supabase_jwt_secret,
                    algorithms=["HS256"],
                    audience=settings.supabase_jwt_audience,
                    issuer=settings.auth_issuer,
                )
            except InvalidTokenError as exc:
                raise _unauthorized("Invalid Supabase access token") from exc

        try:
            return await validate_token_with_auth_server(token, settings)
        except SupabaseAuthError as exc:
            raise _unauthorized("Invalid Supabase access token") from exc

    if algorithm in {"RS256", "ES256"}:
        try:
            signing_key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(
                token
            )
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=settings.supabase_jwt_audience,
                issuer=settings.auth_issuer,
            )
        except InvalidTokenError as exc:
            raise _unauthorized("Invalid Supabase access token") from exc

    raise _unauthorized("Unsupported Supabase JWT signing algorithm")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    try:
        settings = get_settings()
    except MissingConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    token = get_bearer_token(credentials)
    claims = await verify_supabase_jwt(token, settings)
    subject = claims.get("sub")
    if not subject:
        raise _unauthorized("Supabase token does not contain a subject")

    try:
        user_id = UUID(subject)
        profile = await fetch_profile(settings, user_id)
        roles = await fetch_user_roles(settings, user_id)
    except ValueError as exc:
        raise _unauthorized("Supabase token subject is not a valid user id") from exc
    except SupabaseDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if profile is None:
        raise _forbidden("User profile is missing")

    if not profile.get("is_active", False):
        raise _forbidden("User account is inactive")

    if not roles:
        raise _forbidden("User has no application roles")

    return CurrentUser(
        id=user_id,
        email=claims.get("email"),
        full_name=profile.get("full_name"),
        avatar_url=profile.get("avatar_url"),
        auth_provider=profile.get("auth_provider"),
        requested_role=profile.get("requested_role"),
        is_active=profile["is_active"],
        roles=roles,
    )


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise _unauthorized("Missing bearer token")

    return credentials.credentials


def require_roles(*allowed_roles: AppRole):
    allowed = set(allowed_roles)

    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_any_role(allowed):
            allowed_names = ", ".join(sorted(role.value for role in allowed))
            raise _forbidden(f"Requires one of these roles: {allowed_names}")
        return user

    return dependency
