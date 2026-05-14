import uuid

from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import API_ENDPOINT
from .reminders import (
    enrich_repeat_metadata,
    normalize_reminder_payload,
    normalize_reminder_updates,
    reminder_is_visible_to_user,
    split_reminder_per_user,
)


def _parse_target_time(target_time_str):
    """Parse and validate a reminder target time string."""
    if not isinstance(target_time_str, str):
        raise ValueError("Invalid target_time format")
    target_time = dt_util.parse_datetime(target_time_str)
    if not target_time:
        raise ValueError("Invalid target_time format")
    return target_time


def _is_future_target_time(target_time):
    """Return True if the target time is still in the future."""
    return dt_util.as_utc(target_time) > dt_util.utcnow()


class ReminderManagerAPI(HomeAssistantView):
    url = API_ENDPOINT
    name = "api:reminder_manager"
    requires_auth = True

    def __init__(self, hass, storage):
        self.hass = hass
        self.storage = storage

    def set_storage(self, storage):
        """Update the active storage reference for the API view."""
        self.storage = storage

    async def get(self, request):
        """Get all reminders, sorted by target_time."""
        if self.storage is None:
            return self.json({"error": "Reminder Manager is not loaded"}, status_code=503)

        current_user = request.get(KEY_HASS_USER)
        current_user_id = current_user.id if current_user else None
        reminders = [
            reminder
            for reminder in self.storage.get_reminders()
            if reminder_is_visible_to_user(reminder, current_user_id)
        ]
        reminders = sorted(reminders, key=lambda x: x.get("target_time", ""))
        if request.query.get("include_meta") == "1":
            return self.json(
                {
                    "reminders": reminders,
                    "current_user": self._serialize_user(current_user),
                    "available_users": await self._get_available_users(),
                    "available_notify_targets": self._get_available_notify_targets(),
                }
            )
        return self.json(reminders)

    async def post(self, request):
        """Add, update, or delete a reminder."""
        if self.storage is None:
            return self.json({"error": "Reminder Manager is not loaded"}, status_code=503)

        try:
            data = await request.json()
        except ValueError:
            return self.json({"error": "Invalid JSON payload"}, status_code=400)

        action = data.get("action")
        current_user = request.get(KEY_HASS_USER)
        current_user_id = current_user.id if current_user else None

        if action == "add":
            reminder = data.get("reminder")
            if not isinstance(reminder, dict):
                return self.json({"error": "Invalid reminder payload"}, status_code=400)

            # Backend validation
            if not reminder.get("title") or not reminder.get("message"):
                return self.json({"error": "Title and message are required"}, status_code=400)

            target_time_str = reminder.get("target_time")
            if not target_time_str:
                return self.json({"error": "target_time is required"}, status_code=400)

            try:
                target_time = _parse_target_time(target_time_str)
            except ValueError:
                return self.json({"error": "Invalid target_time format"}, status_code=400)

            if not _is_future_target_time(target_time):
                return self.json({"error": "target_time must be in the future"}, status_code=400)

            try:
                reminder = normalize_reminder_payload(reminder, current_user_id)
            except ValueError as err:
                return self.json({"error": str(err)}, status_code=400)

            reminder.setdefault("pre_notified", False)
            reminder.setdefault("pre_notification_bucket", None)
            reminder.setdefault("next_occurrence_scheduled", False)
            reminder = enrich_repeat_metadata(reminder, target_time)

            if not reminder.get("id"):
                reminder["id"] = str(uuid.uuid4())
            reminders_to_add = split_reminder_per_user(reminder, lambda: str(uuid.uuid4()))
            await self.storage.add_reminders(reminders_to_add)
            return self.json({"success": True, "created": len(reminders_to_add)})

        if action in ["update", "done"]:
            reminder_id = data.get("id")
            if not reminder_id:
                return self.json({"error": "Missing reminder ID"}, status_code=400)

            stored_reminder = self.storage.get_reminder(reminder_id)
            if not stored_reminder or not reminder_is_visible_to_user(stored_reminder, current_user_id):
                return self.json({"error": "Reminder not found"}, status_code=404)

            if action == "update":
                updates = data.get("updates", {})
                if not isinstance(updates, dict):
                    return self.json({"error": "Invalid updates payload"}, status_code=400)

                try:
                    updates = normalize_reminder_updates(updates)
                except ValueError as err:
                    return self.json({"error": str(err)}, status_code=400)

                target_time = None
                if "target_time" in updates:
                    try:
                        target_time = _parse_target_time(updates["target_time"])
                    except ValueError:
                        return self.json({"error": "Invalid target_time format"}, status_code=400)

                    if not _is_future_target_time(target_time):
                        return self.json(
                            {"error": "target_time must be in the future"},
                            status_code=400,
                        )
                    updates.setdefault("status", "active")
                    updates.setdefault("notified", False)
                    updates.setdefault("pre_notified", False)
                    updates.setdefault("pre_notification_bucket", None)

                if "target_time" in updates or "repeat" in updates:
                    effective_target_time = target_time if "target_time" in updates else _parse_target_time(
                        stored_reminder["target_time"]
                    )
                    combined = enrich_repeat_metadata({**stored_reminder, **updates}, effective_target_time)
                    updates["repeat"] = combined.get("repeat")
                    updates["repeat_day"] = combined.get("repeat_day")
                    updates["repeat_time"] = combined.get("repeat_time")

                updated = await self.storage.update_reminder(reminder_id, updates)
            else:
                updated = await self.storage.update_reminder(reminder_id, {"status": "done"})

            if not updated:
                return self.json({"error": "Reminder not found"}, status_code=404)

            return self.json({"success": True})

        if action == "delete":
            reminder_id = data.get("id")
            if not reminder_id:
                return self.json({"error": "Missing reminder ID"}, status_code=400)

            stored_reminder = self.storage.get_reminder(reminder_id)
            if not stored_reminder or not reminder_is_visible_to_user(stored_reminder, current_user_id):
                return self.json({"error": "Reminder not found"}, status_code=404)

            deleted = await self.storage.delete_reminder(reminder_id)
            if not deleted:
                return self.json({"error": "Reminder not found"}, status_code=404)
            return self.json({"success": True})

        return self.json({"error": "Unknown action"}, status_code=400)

    async def _get_available_users(self):
        """Return the list of active Home Assistant users."""
        users = []
        for user in await self.hass.auth.async_get_users():
            if getattr(user, "system_generated", False) or not getattr(user, "is_active", True):
                continue
            users.append(self._serialize_user(user))
        return sorted(users, key=lambda item: item["name"].lower())

    def _get_available_notify_targets(self):
        """Return available notify services for per-reminder routing."""
        notify_domain = self.hass.services.async_services().get("notify", {})
        targets = []

        for service_name in sorted(notify_domain):
            if service_name in {"notify", "persistent_notification"}:
                continue
            full_service = f"notify.{service_name}"
            targets.append(
                {
                    "service": full_service,
                    "label": self._format_notify_target_label(service_name),
                }
            )

        return targets

    @staticmethod
    def _serialize_user(user):
        """Serialize a Home Assistant user for the frontend."""
        if user is None:
            return None

        return {
            "id": user.id,
            "name": user.name,
        }

    @staticmethod
    def _format_notify_target_label(service_name):
        """Format a notify service into a readable device label."""
        label = service_name
        if label.startswith("mobile_app_"):
            label = label.removeprefix("mobile_app_")
        return label.replace("_", " ").strip().title()
