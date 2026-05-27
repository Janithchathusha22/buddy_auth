from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import MissingConfigError, get_settings
from app.models import PresenceHeartbeatResponse
from app.presence import presence_status_from_last_seen
from app.security import get_bearer_token
from app.supabase_client import (
    SupabaseAuthError,
    SupabaseDataError,
    fetch_auth_user_from_token,
    mark_user_seen,
)


router = APIRouter()


@router.post(
    "/auth/heartbeat",
    response_model=PresenceHeartbeatResponse,
    tags=["presence"],
)
async def heartbeat(token: str = Depends(get_bearer_token)) -> PresenceHeartbeatResponse:
    try:
        settings = get_settings()
        auth_user = await fetch_auth_user_from_token(token, settings)
        user_id = UUID(auth_user["id"])
        last_seen_at = await mark_user_seen(settings, user_id)
    except MissingConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase access token",
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

    return PresenceHeartbeatResponse(
        user_id=user_id,
        last_seen_at=last_seen_at,
        presence_status=presence_status_from_last_seen(last_seen_at),
    )
