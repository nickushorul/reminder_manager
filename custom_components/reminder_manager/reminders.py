from __future__ import annotations

import calendar
import math
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    REPEAT_MONTHLY,
    REPEAT_NONE,
    TRIGGER_LOCATION,
    TRIGGER_TIME,
    TRIGGER_TIME_AND_LOCATION,
    ZONE_EVENT_ENTER,
    ZONE_EVENT_LEAVE,
)

_EARTH_RADIUS_METERS = 6_371_000.0
_VALID_TRIGGER_TYPES = {TRIGGER_TIME, TRIGGER_LOCATION, TRIGGER_TIME_AND_LOCATION}
_VALID_ZONE_EVENTS = {ZONE_EVENT_ENTER, ZONE_EVENT_LEAVE}


def normalize_user_ids(value: Any) -> list[str]:
    """Normalize target user ids to a unique list of strings."""
    return _normalize_string_list(value)


def normalize_notify_targets(value: Any) -> list[str]:
    """Normalize notify targets to full notify service names."""
    raw_targets = _normalize_string_list(value)
    normalized: list[str] = []

    for target in raw_targets:
        service_name = target if "." in target else f"notify.{target}"
        if service_name not in normalized:
            normalized.append(service_name)

    return normalized


def normalize_repeat(value: Any) -> str:
    """Normalize the repeat mode for a reminder."""
    if value in (None, ""):
        return REPEAT_NONE

    if not isinstance(value, str):
        raise ValueError("repeat must be a string")

    repeat = value.strip().lower()
    if repeat not in {REPEAT_NONE, REPEAT_MONTHLY}:
        raise ValueError("repeat must be one of: none, monthly")

    return repeat


def normalize_repeat_day(value: Any) -> int | None:
    """Normalize repeat day metadata."""
    if value in (None, ""):
        return None

    try:
        day = int(value)
    except (TypeError, ValueError) as err:
        raise ValueError("repeat_day must be an integer") from err

    if day < 1 or day > 31:
        raise ValueError("repeat_day must be between 1 and 31")

    return day


def normalize_repeat_time(value: Any) -> str | None:
    """Normalize repeat time metadata."""
    if value in (None, ""):
        return None

    if not isinstance(value, str):
        raise ValueError("repeat_time must be a string")

    parsed = dt_util.parse_time(value)
    if parsed is None:
        raise ValueError("repeat_time must be a valid time")

    return parsed.replace(microsecond=0).isoformat()


def normalize_trigger_type(value: Any) -> str:
    """Normalize the trigger type."""
    if value in (None, ""):
        return TRIGGER_TIME

    if not isinstance(value, str):
        raise ValueError("trigger_type must be a string")

    trigger = value.strip().lower()
    if trigger not in _VALID_TRIGGER_TYPES:
        raise ValueError(
            "trigger_type must be one of: time, location, time_and_location"
        )
    return trigger


def normalize_zone_event(value: Any) -> str:
    """Normalize the zone event."""
    if value in (None, ""):
        return ZONE_EVENT_ENTER

    if not isinstance(value, str):
        raise ValueError("zone_event must be a string")

    event = value.strip().lower()
    if event not in _VALID_ZONE_EVENTS:
        raise ValueError("zone_event must be one of: enter, leave")
    return event


def _normalize_iso_or_none(value: Any, field_name: str) -> str | None:
    """Normalize an ISO datetime string, allowing None/empty for absent values."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO datetime string")
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be a valid ISO datetime")
    return parsed.isoformat()


def normalize_zone_entity_id(value: Any) -> str | None:
    """Normalize a HA zone entity id (e.g. zone.home)."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("zone_entity_id must be a string")
    cleaned = value.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("zone."):
        raise ValueError("zone_entity_id must start with 'zone.'")
    return cleaned


def normalize_custom_zone(value: Any) -> dict[str, Any] | None:
    """Normalize a custom (ad-hoc) zone dictionary with lat/lon/radius."""
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise ValueError("custom_zone must be an object")

    try:
        latitude = float(value.get("latitude"))
        longitude = float(value.get("longitude"))
    except (TypeError, ValueError):
        raise ValueError("custom_zone latitude and longitude are required numbers") from None

    if not -90 <= latitude <= 90:
        raise ValueError("custom_zone latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("custom_zone longitude must be between -180 and 180")

    radius_value = value.get("radius", 100)
    try:
        radius = float(radius_value)
    except (TypeError, ValueError):
        raise ValueError("custom_zone radius must be a number") from None
    if radius <= 0 or radius > 50_000:
        raise ValueError("custom_zone radius must be between 1 and 50000 meters")

    name = value.get("name")
    if name is not None and not isinstance(name, str):
        raise ValueError("custom_zone name must be a string")

    return {
        "name": (name or "").strip() or "Locatie personalizata",
        "latitude": latitude,
        "longitude": longitude,
        "radius": radius,
    }


def validate_location_payload(reminder: dict[str, Any]) -> None:
    """Validate that a location-based reminder has the required fields."""
    zone_entity_id = reminder.get("zone_entity_id")
    custom_zone = reminder.get("custom_zone")
    if not zone_entity_id and not custom_zone:
        raise ValueError("Location reminders require zone_entity_id or custom_zone")
    if zone_entity_id and custom_zone:
        raise ValueError("Set either zone_entity_id or custom_zone, not both")

    if reminder.get("trigger_type") == TRIGGER_TIME_AND_LOCATION:
        if not reminder.get("active_from"):
            raise ValueError(
                "time_and_location reminders require active_from (the earliest moment "
                "the location trigger is armed)"
            )


def normalize_reminder_payload(reminder: dict[str, Any], owner_user_id: str | None) -> dict[str, Any]:
    """Normalize a full reminder payload coming from the API/UI."""
    normalized = dict(reminder)
    normalized["trigger_type"] = normalize_trigger_type(normalized.get("trigger_type"))
    normalized["repeat"] = normalize_repeat(normalized.get("repeat"))
    normalized["repeat_day"] = normalize_repeat_day(normalized.get("repeat_day"))
    normalized["repeat_time"] = normalize_repeat_time(normalized.get("repeat_time"))
    normalized["target_user_ids"] = normalize_user_ids(normalized.get("target_user_ids"))
    normalized["notify_targets"] = normalize_notify_targets(normalized.get("notify_targets"))
    normalized["zone_event"] = normalize_zone_event(normalized.get("zone_event"))
    normalized["zone_entity_id"] = normalize_zone_entity_id(normalized.get("zone_entity_id"))
    normalized["custom_zone"] = normalize_custom_zone(normalized.get("custom_zone"))
    normalized["active_from"] = _normalize_iso_or_none(normalized.get("active_from"), "active_from")
    normalized["active_until"] = _normalize_iso_or_none(normalized.get("active_until"), "active_until")
    normalized["location_recurring"] = bool(normalized.get("location_recurring", False))

    if owner_user_id and not normalized.get("owner_user_id"):
        normalized["owner_user_id"] = owner_user_id

    if owner_user_id and not normalized["target_user_ids"]:
        normalized["target_user_ids"] = [owner_user_id]

    return normalized


def normalize_reminder_updates(updates: dict[str, Any]) -> dict[str, Any]:
    """Normalize a partial reminder update payload."""
    normalized = dict(updates)

    if "trigger_type" in normalized:
        normalized["trigger_type"] = normalize_trigger_type(normalized.get("trigger_type"))

    if "repeat" in normalized:
        normalized["repeat"] = normalize_repeat(normalized.get("repeat"))

    if "repeat_day" in normalized:
        normalized["repeat_day"] = normalize_repeat_day(normalized.get("repeat_day"))

    if "repeat_time" in normalized:
        normalized["repeat_time"] = normalize_repeat_time(normalized.get("repeat_time"))

    if "target_user_ids" in normalized:
        normalized["target_user_ids"] = normalize_user_ids(normalized.get("target_user_ids"))

    if "notify_targets" in normalized:
        normalized["notify_targets"] = normalize_notify_targets(normalized.get("notify_targets"))

    if "zone_event" in normalized:
        normalized["zone_event"] = normalize_zone_event(normalized.get("zone_event"))

    if "zone_entity_id" in normalized:
        normalized["zone_entity_id"] = normalize_zone_entity_id(normalized.get("zone_entity_id"))

    if "custom_zone" in normalized:
        normalized["custom_zone"] = normalize_custom_zone(normalized.get("custom_zone"))

    if "active_from" in normalized:
        normalized["active_from"] = _normalize_iso_or_none(normalized.get("active_from"), "active_from")

    if "active_until" in normalized:
        normalized["active_until"] = _normalize_iso_or_none(normalized.get("active_until"), "active_until")

    if "location_recurring" in normalized:
        normalized["location_recurring"] = bool(normalized.get("location_recurring"))

    return normalized


def reminder_has_location_trigger(reminder: dict[str, Any]) -> bool:
    """Return True if the reminder uses location (alone or combined with time)."""
    trigger = reminder.get("trigger_type") or TRIGGER_TIME
    return trigger in (TRIGGER_LOCATION, TRIGGER_TIME_AND_LOCATION)


def reminder_has_time_trigger(reminder: dict[str, Any]) -> bool:
    """Return True if the reminder fires purely on time."""
    trigger = reminder.get("trigger_type") or TRIGGER_TIME
    return trigger == TRIGGER_TIME


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two lat/lon pairs."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_METERS * c


def resolve_zone_coordinates(
    reminder: dict[str, Any], zone_lookup
) -> tuple[float, float, float] | None:
    """Resolve a reminder's zone to a (latitude, longitude, radius) triple.

    `zone_lookup` is a callable that takes a zone entity_id and returns a dict
    with keys latitude/longitude/radius — or None if the zone is unknown.
    """
    custom_zone = reminder.get("custom_zone")
    if custom_zone:
        return (
            float(custom_zone["latitude"]),
            float(custom_zone["longitude"]),
            float(custom_zone.get("radius", 100)),
        )

    zone_entity_id = reminder.get("zone_entity_id")
    if not zone_entity_id:
        return None

    zone = zone_lookup(zone_entity_id) if callable(zone_lookup) else None
    if not zone:
        return None
    return (
        float(zone["latitude"]),
        float(zone["longitude"]),
        float(zone.get("radius", 100)),
    )


def is_within_active_window(
    reminder: dict[str, Any], now: datetime | None = None
) -> bool:
    """Return True if `now` falls inside the reminder's active_from/until window."""
    now = now or dt_util.utcnow()
    now_utc = dt_util.as_utc(now)

    active_from = reminder.get("active_from")
    if active_from:
        parsed = dt_util.parse_datetime(active_from)
        if parsed and dt_util.as_utc(parsed) > now_utc:
            return False

    active_until = reminder.get("active_until")
    if active_until:
        parsed = dt_util.parse_datetime(active_until)
        if parsed and dt_util.as_utc(parsed) < now_utc:
            return False

    return True


def location_reminder_expired(reminder: dict[str, Any], now: datetime | None = None) -> bool:
    """Return True if a location reminder's active_until has passed."""
    active_until = reminder.get("active_until")
    if not active_until:
        return False
    parsed = dt_util.parse_datetime(active_until)
    if not parsed:
        return False
    now = now or dt_util.utcnow()
    return dt_util.as_utc(parsed) < dt_util.as_utc(now)


def reminder_is_visible_to_user(reminder: dict[str, Any], user_id: str | None) -> bool:
    """Return True if the reminder should be visible to the given user."""
    if user_id is None:
        return True

    owner_user_id = reminder.get("owner_user_id")
    target_user_ids = normalize_user_ids(reminder.get("target_user_ids"))

    if not owner_user_id and not target_user_ids:
        return True

    return owner_user_id == user_id or user_id in target_user_ids


def reminder_targets(reminder: dict[str, Any]) -> list[str]:
    """Return normalized notify targets for a reminder."""
    return normalize_notify_targets(reminder.get("notify_targets"))


def enrich_repeat_metadata(reminder: dict[str, Any], target_time: datetime) -> dict[str, Any]:
    """Persist recurrence metadata derived from the selected target time."""
    normalized = dict(reminder)
    repeat = normalize_repeat(normalized.get("repeat"))
    normalized["repeat"] = repeat

    if repeat == REPEAT_MONTHLY:
        local_target = _to_local_datetime(target_time)
        normalized["repeat_day"] = normalize_repeat_day(normalized.get("repeat_day")) or local_target.day
        normalized["repeat_time"] = (
            normalize_repeat_time(normalized.get("repeat_time"))
            or local_target.time().replace(microsecond=0).isoformat()
        )
    else:
        normalized.pop("repeat_day", None)
        normalized.pop("repeat_time", None)

    return normalized


def is_monthly_repeat(reminder: dict[str, Any]) -> bool:
    """Return True when the reminder repeats every month."""
    return normalize_repeat(reminder.get("repeat")) == REPEAT_MONTHLY


def build_next_monthly_reminder(
    reminder: dict[str, Any],
    current_target_time: datetime,
    start_time: datetime,
    new_id_factory,
) -> dict[str, Any]:
    """Create the next monthly occurrence for a recurring reminder."""
    next_target = next_monthly_target(reminder, current_target_time)
    next_reminder = dict(reminder)
    next_reminder["id"] = new_id_factory()
    next_reminder["start_time"] = _to_local_datetime(start_time).isoformat()
    next_reminder["target_time"] = next_target.isoformat()
    next_reminder["status"] = "active"
    next_reminder["notified"] = False
    next_reminder["pre_notified"] = False
    next_reminder["pre_notification_bucket"] = None
    next_reminder["next_occurrence_scheduled"] = False
    return next_reminder


def next_monthly_target(reminder: dict[str, Any], current_target_time: datetime) -> datetime:
    """Return the next monthly target while keeping the configured day and time."""
    local_current = _to_local_datetime(current_target_time)
    repeat_day = reminder.get("repeat_day", local_current.day)

    try:
        day = max(1, int(repeat_day))
    except (TypeError, ValueError):
        day = local_current.day

    repeat_time = dt_util.parse_time(reminder.get("repeat_time")) if reminder.get("repeat_time") else None
    hour = repeat_time.hour if repeat_time else local_current.hour
    minute = repeat_time.minute if repeat_time else local_current.minute
    second = repeat_time.second if repeat_time else local_current.second

    year = local_current.year
    month = local_current.month + 1
    if month > 12:
        year += 1
        month = 1

    day = min(day, calendar.monthrange(year, month)[1])

    return local_current.replace(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        microsecond=0,
    )


def _to_local_datetime(value: datetime) -> datetime:
    """Convert a datetime to Home Assistant's configured local timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.UTC)
    return value.astimezone(dt_util.DEFAULT_TIME_ZONE)


def split_reminder_per_user(
    reminder: dict[str, Any], new_id_factory
) -> list[dict[str, Any]]:
    """Split a reminder into separate independent reminders per target user."""
    target_user_ids = normalize_user_ids(reminder.get("target_user_ids"))
    if len(target_user_ids) <= 1:
        return [dict(reminder)]

    reminders: list[dict[str, Any]] = []
    for index, user_id in enumerate(target_user_ids):
        item = dict(reminder)
        item["id"] = item.get("id") if index == 0 else new_id_factory()
        item["target_user_ids"] = [user_id]
        reminders.append(item)

    return reminders


def _normalize_string_list(value: Any) -> list[str]:
    """Normalize a single string or list of strings into a unique list."""
    if value is None or value == "":
        return []

    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("Expected a string or list of strings")

    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("Expected a string or list of strings")

        cleaned = item.strip()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)

    return normalized
