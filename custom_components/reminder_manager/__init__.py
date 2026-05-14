import datetime
import logging
import uuid

from homeassistant.components.frontend import async_remove_panel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import ReminderManagerAPI
from .const import (
    DOMAIN,
    PANEL_URL_PATH,
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_EXPIRED,
)
from .panel import async_setup_panel
from .reminders import (
    build_next_monthly_reminder,
    enrich_repeat_metadata,
    is_monthly_repeat,
    normalize_reminder_payload,
    normalize_reminder_updates,
    reminder_targets,
    split_reminder_per_user,
)
from .storage import ReminderStorage

_LOGGER = logging.getLogger(__name__)
_DEFAULT_NOTIFY_SERVICE = "notify.notify"
_CHECK_INTERVAL = datetime.timedelta(seconds=15)
_PRE_NOTIFICATION_WINDOW = datetime.timedelta(minutes=5)
_MOBILE_NOTIFICATION_ACTION_EVENT = "mobile_app_notification_action"
_ACTION_DONE_PREFIX = "REMINDER_DONE"
_ACTION_SNOOZE_PREFIX = "REMINDER_SNOOZE_10"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _get_notify_service(entry: ConfigEntry) -> str:
    """Return the configured notify service for the entry."""
    return entry.options.get(
        "notify_service",
        entry.data.get("notify_service", _DEFAULT_NOTIFY_SERVICE),
    )


def _parse_target_time(target_time_str: str):
    """Parse a target time string."""
    if not isinstance(target_time_str, str):
        raise ValueError("Invalid target_time format")
    target_time = dt_util.parse_datetime(target_time_str)
    if not target_time:
        raise ValueError("Invalid target_time format")
    return target_time


def _parse_future_target_time(target_time_str: str):
    """Parse a target time and ensure it is still in the future."""
    target_time = _parse_target_time(target_time_str)
    if dt_util.as_utc(target_time) <= dt_util.utcnow():
        raise ValueError("target_time must be in the future")
    return target_time


def _remove_service(hass: HomeAssistant, service_name: str) -> None:
    """Remove a Reminder Manager service if it is still registered."""
    if hass.services.has_service(DOMAIN, service_name):
        hass.services.async_remove(DOMAIN, service_name)


def _notification_tag(reminder_id: str) -> str:
    """Return the shared mobile notification tag for a reminder."""
    return f"reminder_manager_{reminder_id}"


def _build_notification_actions(reminder_id: str) -> list[dict[str, str]]:
    """Build mobile notification action buttons for a reminder."""
    return [
        {"action": f"{_ACTION_DONE_PREFIX}::{reminder_id}", "title": "Done"},
        {"action": f"{_ACTION_SNOOZE_PREFIX}::{reminder_id}", "title": "Snooze 10m"},
    ]


def _parse_notification_action(action: str | None) -> tuple[str | None, str | None]:
    """Parse a mobile notification action identifier."""
    if not action or "::" not in action:
        return None, None

    action_name, reminder_id = action.split("::", 1)
    return action_name, reminder_id


def _prepare_repeat_payload(reminder: dict, target_time) -> dict:
    """Persist repeat metadata derived from the selected target time."""
    return enrich_repeat_metadata(reminder, target_time)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Reminder Manager component."""
    _LOGGER.info("Setting up Reminder Manager (async_setup)")
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Reminder Manager from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    storage = domain_data.get("storage")
    if storage is None:
        storage = ReminderStorage(hass)
        domain_data["storage"] = storage

    await storage.async_load()
    domain_data["notify_service"] = _get_notify_service(entry)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    api_view = domain_data.get("api_view")
    if api_view is None:
        api_view = ReminderManagerAPI(hass, storage)
        hass.http.register_view(api_view)
        domain_data["api_view"] = api_view
    else:
        api_view.set_storage(storage)

    await async_setup_panel(hass)
    entry.async_on_unload(
        lambda: async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    )

    async def check_reminders(_now):
        notify_service = domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE)
        await _process_due_reminders(hass, storage, notify_service)

    entry.async_on_unload(async_track_time_interval(hass, check_reminders, _CHECK_INTERVAL))
    hass.async_create_task(check_reminders(None))

    async def handle_create_service(call):
        title = call.data.get("title", "New Reminder")
        message = call.data.get("message", "Message")
        duration_minutes = call.data.get("duration_minutes")
        target_time_str = call.data.get("target_time")

        current_time = dt_util.now()
        target_time = current_time + datetime.timedelta(minutes=10)

        if target_time_str:
            target_time = _parse_future_target_time(target_time_str)
        elif duration_minutes is not None:
            if duration_minutes <= 0:
                raise ValueError("duration_minutes must be greater than zero")
            target_time = current_time + datetime.timedelta(minutes=duration_minutes)

        reminder = normalize_reminder_payload(
            {
                "id": str(uuid.uuid4()),
                "title": title,
                "message": message,
                "start_time": current_time.isoformat(),
                "target_time": target_time.isoformat(),
                "status": STATUS_ACTIVE,
                "repeat": call.data.get("repeat"),
                "notify_mobile": call.data.get("notify_mobile", True),
                "notify_persistent": call.data.get("notify_persistent", True),
                "target_user_ids": call.data.get("target_user_ids"),
                "notify_targets": call.data.get("notify_targets"),
                "notified": False,
                "pre_notified": False,
                "next_occurrence_scheduled": False,
            },
            call.context.user_id,
        )
        reminder = _prepare_repeat_payload(reminder, target_time)
        await storage.add_reminders(split_reminder_per_user(reminder, lambda: str(uuid.uuid4())))

    async def handle_update_service(call):
        reminder_id = call.data.get("id")
        updates = call.data.get("updates", {})
        if not reminder_id:
            return

        if not isinstance(updates, dict):
            raise ValueError("updates must be an object")

        stored_reminder = storage.get_reminder(reminder_id)
        if not stored_reminder:
            _LOGGER.warning("Cannot update reminder %s because it does not exist.", reminder_id)
            return

        updates = normalize_reminder_updates(updates)
        target_time = None

        if "target_time" in updates:
            target_time = _parse_future_target_time(updates["target_time"])
            updates.setdefault("status", STATUS_ACTIVE)
            updates.setdefault("notified", False)
            updates.setdefault("pre_notified", False)

        if target_time or "repeat" in updates:
            effective_target_time_str = updates.get("target_time", stored_reminder.get("target_time"))
            effective_target_time = target_time or _parse_future_target_time(effective_target_time_str)
            combined = _prepare_repeat_payload({**stored_reminder, **updates}, effective_target_time)
            updates["repeat"] = combined.get("repeat")
            updates["repeat_day"] = combined.get("repeat_day")
            updates["repeat_time"] = combined.get("repeat_time")

        updated = await storage.update_reminder(reminder_id, updates)
        if not updated:
            _LOGGER.warning("Cannot update reminder %s because it does not exist.", reminder_id)

    async def handle_delete_service(call):
        reminder_id = call.data.get("id")
        if reminder_id:
            stored_reminder = storage.get_reminder(reminder_id)
            if stored_reminder:
                await _clear_mobile_notifications(
                    hass,
                    stored_reminder,
                    domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE),
                )
            deleted = await storage.delete_reminder(reminder_id)
            if not deleted:
                _LOGGER.warning(
                    "Cannot delete reminder %s because it does not exist.", reminder_id
                )

    async def handle_done_service(call):
        reminder_id = call.data.get("id")
        if reminder_id:
            stored_reminder = storage.get_reminder(reminder_id)
            if not stored_reminder:
                _LOGGER.warning("Cannot complete reminder %s because it does not exist.", reminder_id)
                return

            if (
                stored_reminder.get("status") == STATUS_ACTIVE
                and is_monthly_repeat(stored_reminder)
                and not stored_reminder.get("next_occurrence_scheduled")
            ):
                await storage.add_reminder(
                    build_next_monthly_reminder(
                        stored_reminder,
                        _parse_target_time(stored_reminder["target_time"]),
                        dt_util.now(),
                        lambda: str(uuid.uuid4()),
                    )
                )

            await _clear_mobile_notifications(
                hass,
                stored_reminder,
                domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE),
            )
            updated = await storage.update_reminder(
                reminder_id,
                {"status": STATUS_DONE, "next_occurrence_scheduled": True},
            )
            if not updated:
                _LOGGER.warning("Cannot complete reminder %s because it does not exist.", reminder_id)

    async def handle_snooze_service(call):
        reminder_id = call.data.get("id")
        minutes = call.data.get("minutes", 10)
        if not reminder_id:
            return

        if minutes <= 0:
            raise ValueError("minutes must be greater than zero")

        stored_reminder = storage.get_reminder(reminder_id)
        if not stored_reminder:
            _LOGGER.warning("Cannot snooze reminder %s because it does not exist.", reminder_id)
            return

        new_start = dt_util.now()
        new_target = new_start + datetime.timedelta(minutes=minutes)
        await _clear_mobile_notifications(
            hass,
            stored_reminder,
            domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE),
        )
        updated = await storage.update_reminder(
            reminder_id,
            {
                "target_time": new_target.isoformat(),
                "start_time": new_start.isoformat(),
                "status": STATUS_ACTIVE,
                "notified": False,
                "pre_notified": False,
            },
        )
        if not updated:
            _LOGGER.warning("Cannot snooze reminder %s because it does not exist.", reminder_id)

    async def handle_mobile_notification_action(event):
        action_name, reminder_id = _parse_notification_action(event.data.get("action"))
        if not reminder_id:
            return

        stored_reminder = storage.get_reminder(reminder_id)
        if not stored_reminder:
            return

        notify_service = domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE)

        if action_name == _ACTION_DONE_PREFIX:
            if (
                stored_reminder.get("status") == STATUS_ACTIVE
                and is_monthly_repeat(stored_reminder)
                and not stored_reminder.get("next_occurrence_scheduled")
            ):
                await storage.add_reminder(
                    build_next_monthly_reminder(
                        stored_reminder,
                        _parse_target_time(stored_reminder["target_time"]),
                        dt_util.now(),
                        lambda: str(uuid.uuid4()),
                    )
                )

            await _clear_mobile_notifications(hass, stored_reminder, notify_service)
            await storage.update_reminder(
                reminder_id,
                {"status": STATUS_DONE, "next_occurrence_scheduled": True},
            )
            return

        if action_name == _ACTION_SNOOZE_PREFIX:
            new_start = dt_util.now()
            new_target = new_start + datetime.timedelta(minutes=10)
            await _clear_mobile_notifications(hass, stored_reminder, notify_service)
            await storage.update_reminder(
                reminder_id,
                {
                    "target_time": new_target.isoformat(),
                    "start_time": new_start.isoformat(),
                    "status": STATUS_ACTIVE,
                    "notified": False,
                    "pre_notified": False,
                },
            )

    service_handlers = {
        "create": handle_create_service,
        "update": handle_update_service,
        "delete": handle_delete_service,
        "done": handle_done_service,
        "snooze": handle_snooze_service,
    }
    for service_name, handler in service_handlers.items():
        _remove_service(hass, service_name)
        hass.services.async_register(DOMAIN, service_name, handler)
        entry.async_on_unload(
            lambda service_name=service_name: _remove_service(hass, service_name)
        )

    entry.async_on_unload(
        hass.bus.async_listen(
            _MOBILE_NOTIFICATION_ACTION_EVENT,
            lambda event: hass.async_create_task(handle_mobile_notification_action(event)),
        )
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload Reminder Manager."""
    domain_data = hass.data.get(DOMAIN, {})
    api_view = domain_data.get("api_view")
    if api_view is not None:
        api_view.set_storage(None)

    domain_data.pop("notify_service", None)
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    hass.data.setdefault(DOMAIN, {})["notify_service"] = _get_notify_service(entry)


async def _clear_mobile_notifications(hass, reminder, notify_service):
    """Clear the mobile notification for a reminder across all configured targets."""
    reminder_id = reminder.get("id")
    if not reminder_id:
        return

    tag = _notification_tag(reminder_id)
    notify_targets = reminder_targets(reminder) or ([notify_service] if notify_service else [])

    for target in notify_targets:
        try:
            domain, service = target.split(".", 1) if "." in target else ("notify", "notify")
            await hass.services.async_call(
                domain,
                service,
                {
                    "message": "clear_notification",
                    "data": {
                        "tag": tag,
                    },
                },
                blocking=True,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to clear mobile notification using %s for reminder %s.",
                target,
                reminder_id,
            )


async def _send_mobile_notification(
    hass,
    target: str,
    reminder: dict,
    title: str,
    message: str,
    *,
    countdown_seconds: int | None = None,
):
    """Send a mobile notification to one configured notify target."""
    reminder_id = reminder.get("id")
    tag = _notification_tag(reminder_id)
    data = {
        "tag": tag,
        "group": "reminder_manager",
        "persistent": True,
        "actions": _build_notification_actions(reminder_id),
    }

    if countdown_seconds is not None and countdown_seconds > 0:
        data.update(
            {
                "chronometer": True,
                "when": max(1, countdown_seconds),
                "when_relative": True,
                "live_update": True,
                "critical_text": f"{max(1, (countdown_seconds + 59) // 60)}m",
            }
        )

    domain, service = target.split(".", 1) if "." in target else ("notify", "notify")
    await hass.services.async_call(
        domain,
        service,
        {
            "title": title,
            "message": message,
            "data": data,
        },
        blocking=True,
    )


async def _send_pre_notification(hass, reminder, notify_service, remaining_seconds: int):
    """Send the pre-reminder mobile notification when the reminder enters the 5-minute window."""
    if not reminder.get("notify_mobile"):
        return

    title = reminder.get("title", "Reminder")
    message = reminder.get("message", "Reminder upcoming!")
    minutes_left = max(1, (remaining_seconds + 59) // 60)
    notify_targets = reminder_targets(reminder) or [notify_service]

    for target in notify_targets:
        try:
            await _send_mobile_notification(
                hass,
                target,
                reminder,
                f"{title} in curand",
                f"{message} Mai sunt aproximativ {minutes_left} minute.",
                countdown_seconds=remaining_seconds,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to send pre-notification using %s for reminder %s.",
                target,
                reminder.get("id"),
            )


async def _send_notification(hass, reminder, notify_service):
    """Send notification for expired reminder."""
    title = reminder.get("title", "Reminder")
    message = reminder.get("message", "Reminder expired!")
    reminder_id = reminder.get("id")
    persistent_sent = False

    if reminder.get("notify_persistent"):
        try:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": message,
                    "title": title,
                    "notification_id": f"reminder_{reminder_id}",
                },
                blocking=True,
            )
            persistent_sent = True
        except Exception:
            _LOGGER.exception(
                "Failed to create persistent notification for reminder %s.",
                reminder_id,
            )

    if reminder.get("notify_mobile"):
        notify_targets = reminder_targets(reminder) or [notify_service]
        for target in notify_targets:
            try:
                await _send_mobile_notification(
                    hass,
                    target,
                    reminder,
                    title,
                    message,
                )
            except Exception as e:
                _LOGGER.warning(
                    "Failed to send mobile notification using %s: %s. Sending persistent notification instead.",
                    target,
                    e,
                )
                if not persistent_sent:
                    try:
                        await hass.services.async_call(
                            "persistent_notification",
                            "create",
                            {
                                "message": f"Esec notificare telefon: {message}",
                                "title": title,
                                "notification_id": f"reminder_err_{reminder_id}",
                            },
                            blocking=True,
                        )
                    except Exception:
                        _LOGGER.exception(
                            "Failed to create fallback persistent notification for reminder %s.",
                            reminder_id,
                        )


async def _process_due_reminders(
    hass: HomeAssistant, storage: ReminderStorage, notify_service: str
) -> None:
    """Process active reminders and notify for due items."""
    reminders = storage.get_reminders()
    reminders_to_add: list[dict] = []
    needs_save = False
    current_time = dt_util.utcnow()

    for reminder in reminders:
        if reminder.get("status") != STATUS_ACTIVE or reminder.get("notified"):
            continue

        target_time_str = reminder.get("target_time")
        if not target_time_str:
            continue

        try:
            target_time = dt_util.parse_datetime(target_time_str)
            if not target_time:
                raise ValueError("Invalid target_time format")

            target_time_utc = dt_util.as_utc(target_time)
            remaining_seconds = int((target_time_utc - current_time).total_seconds())

            if (
                reminder.get("notify_mobile")
                and not reminder.get("pre_notified")
                and 0 < remaining_seconds <= int(_PRE_NOTIFICATION_WINDOW.total_seconds())
            ):
                await _send_pre_notification(hass, reminder, notify_service, remaining_seconds)
                reminder["pre_notified"] = True
                needs_save = True

            if current_time >= target_time_utc:
                if is_monthly_repeat(reminder) and not reminder.get("next_occurrence_scheduled"):
                    reminders_to_add.append(
                        build_next_monthly_reminder(
                            reminder,
                            target_time,
                            dt_util.now(),
                            lambda: str(uuid.uuid4()),
                        )
                    )
                    reminder["next_occurrence_scheduled"] = True

                await _send_notification(hass, reminder, notify_service)
                reminder["status"] = STATUS_EXPIRED
                reminder["notified"] = True
                needs_save = True
        except Exception:
            _LOGGER.exception(
                "Failed to process reminder %s with target_time=%s.",
                reminder.get("id"),
                target_time_str,
            )

    if reminders_to_add:
        reminders.extend(reminders_to_add)
        storage.data["reminders"] = reminders
        needs_save = True

    if needs_save:
        await storage.async_save()
