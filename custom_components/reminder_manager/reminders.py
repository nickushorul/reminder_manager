from __future__ import annotations

import calendar
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import REPEAT_MONTHLY, REPEAT_NONE


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


def normalize_reminder_payload(reminder: dict[str, Any], owner_user_id: str | None) -> dict[str, Any]:
    """Normalize a full reminder payload coming from the API/UI."""
    normalized = dict(reminder)
    normalized["repeat"] = normalize_repeat(normalized.get("repeat"))
    normalized["target_user_ids"] = normalize_user_ids(normalized.get("target_user_ids"))
    normalized["notify_targets"] = normalize_notify_targets(normalized.get("notify_targets"))

    if owner_user_id and not normalized.get("owner_user_id"):
        normalized["owner_user_id"] = owner_user_id

    if owner_user_id and not normalized["target_user_ids"]:
        normalized["target_user_ids"] = [owner_user_id]

    return normalized


def normalize_reminder_updates(updates: dict[str, Any]) -> dict[str, Any]:
    """Normalize a partial reminder update payload."""
    normalized = dict(updates)

    if "repeat" in normalized:
        normalized["repeat"] = normalize_repeat(normalized.get("repeat"))

    if "target_user_ids" in normalized:
        normalized["target_user_ids"] = normalize_user_ids(normalized.get("target_user_ids"))

    if "notify_targets" in normalized:
        normalized["notify_targets"] = normalize_notify_targets(normalized.get("notify_targets"))

    return normalized


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
        local_target = dt_util.as_local(target_time)
        normalized["repeat_day"] = local_target.day
        normalized["repeat_time"] = local_target.time().replace(microsecond=0).isoformat()
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
    next_reminder["start_time"] = dt_util.as_local(start_time).isoformat()
    next_reminder["target_time"] = next_target.isoformat()
    next_reminder["status"] = "active"
    next_reminder["notified"] = False
    next_reminder["pre_notified"] = False
    next_reminder["next_occurrence_scheduled"] = False
    return next_reminder


def next_monthly_target(reminder: dict[str, Any], current_target_time: datetime) -> datetime:
    """Return the next monthly target while keeping the configured day and time."""
    local_current = dt_util.as_local(current_target_time)
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
