from datetime import datetime, timedelta, timezone

from app.models import PresenceStatus


ONLINE_WINDOW_SECONDS = 60


def parse_last_seen(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        seen_at = value
    else:
        text = value.strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"

        try:
            seen_at = datetime.fromisoformat(text)
        except ValueError:
            return None

    if seen_at.tzinfo is None:
        return seen_at.replace(tzinfo=timezone.utc)

    return seen_at.astimezone(timezone.utc)


def presence_status_from_last_seen(
    last_seen_at: str | datetime | None,
    now: datetime | None = None,
) -> PresenceStatus:
    seen_at = parse_last_seen(last_seen_at)
    if seen_at is None:
        return PresenceStatus.OFFLINE

    current_time = now or datetime.now(timezone.utc)
    online_after = current_time - timedelta(seconds=ONLINE_WINDOW_SECONDS)
    return PresenceStatus.ONLINE if seen_at >= online_after else PresenceStatus.OFFLINE
