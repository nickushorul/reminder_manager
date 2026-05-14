import uuid

from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import API_ENDPOINT


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

    def __init__(self, storage):
        self.storage = storage

    def set_storage(self, storage):
        """Update the active storage reference for the API view."""
        self.storage = storage

    async def get(self, request):
        """Get all reminders, sorted by target_time."""
        if self.storage is None:
            return self.json({"error": "Reminder Manager is not loaded"}, status_code=503)

        reminders = self.storage.get_reminders()
        reminders = sorted(reminders, key=lambda x: x.get("target_time", ""))
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

            if not reminder.get("id"):
                reminder["id"] = str(uuid.uuid4())
            await self.storage.add_reminder(reminder)
            return self.json({"success": True})

        if action in ["update", "done"]:
            reminder_id = data.get("id")
            if not reminder_id:
                return self.json({"error": "Missing reminder ID"}, status_code=400)

            if action == "update":
                updates = data.get("updates", {})
                if not isinstance(updates, dict):
                    return self.json({"error": "Invalid updates payload"}, status_code=400)

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
            deleted = await self.storage.delete_reminder(reminder_id)
            if not deleted:
                return self.json({"error": "Reminder not found"}, status_code=404)
            return self.json({"success": True})

        return self.json({"error": "Unknown action"}, status_code=400)
