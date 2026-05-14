from __future__ import annotations

from typing import Any


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


def normalize_reminder_payload(reminder: dict[str, Any], owner_user_id: str | None) -> dict[str, Any]:
    """Normalize a full reminder payload coming from the API/UI."""
    normalized = dict(reminder)
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
