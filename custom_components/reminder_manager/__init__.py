import datetime
import logging
import uuid

from homeassistant.components.frontend import async_remove_panel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import ReminderManagerAPI
from .const import DOMAIN, PANEL_URL_PATH, STATUS_ACTIVE, STATUS_DONE, STATUS_EXPIRED
from .panel import async_setup_panel
from .storage import ReminderStorage

_LOGGER = logging.getLogger(__name__)
_DEFAULT_NOTIFY_SERVICE = "notify.notify"


def _get_notify_service(entry: ConfigEntry) -> str:
    """Return the configured notify service for the entry."""
    return entry.options.get(
        "notify_service",
        entry.data.get("notify_service", _DEFAULT_NOTIFY_SERVICE),
    )


def _parse_future_target_time(target_time_str: str):
    """Parse a target time and ensure it is still in the future."""
    if not isinstance(target_time_str, str):
        raise ValueError("Invalid target_time format")
    target_time = dt_util.parse_datetime(target_time_str)
    if not target_time:
        raise ValueError("Invalid target_time format")
    if dt_util.as_utc(target_time) <= dt_util.utcnow():
        raise ValueError("target_time must be in the future")
    return target_time


def _remove_service(hass: HomeAssistant, service_name: str) -> None:
    """Remove a Reminder Manager service if it is still registered."""
    if hass.services.has_service(DOMAIN, service_name):
        hass.services.async_remove(DOMAIN, service_name)


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
        api_view = ReminderManagerAPI(storage)
        hass.http.register_view(api_view)
        domain_data["api_view"] = api_view
    else:
        api_view.set_storage(storage)

    await async_setup_panel(hass)
    entry.async_on_unload(
        lambda: async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    )

    async def check_reminders(_now):
        reminders = storage.get_reminders()
        needs_save = False
        current_time = dt_util.now()
        notify_service = domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE)

        for r in reminders:
            if r.get("status") == STATUS_ACTIVE:
                target_time_str = r.get("target_time")
                if target_time_str:
                    try:
                        target_time = dt_util.parse_datetime(target_time_str)
                        if target_time and current_time >= target_time:
                            # Notifica si apoi marcheaza ca notificat (sa incerce chiar daca pica).
                            await _send_notification(hass, r, notify_service)
                            r["status"] = STATUS_EXPIRED
                            r["notified"] = True
                            needs_save = True
                    except Exception as e:
                        _LOGGER.error(f"Error parsing date {target_time_str}: {e}")

        if needs_save:
            await storage.async_save()

    entry.async_on_unload(
        async_track_time_interval(hass, check_reminders, datetime.timedelta(minutes=1))
    )

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

        reminder = {
            "id": str(uuid.uuid4()),
            "title": title,
            "message": message,
            "start_time": current_time.isoformat(),
            "target_time": target_time.isoformat(),
            "status": STATUS_ACTIVE,
            "notify_mobile": True,
            "notify_persistent": True,
            "notified": False,
        }
        await storage.add_reminder(reminder)

    async def handle_update_service(call):
        reminder_id = call.data.get("id")
        updates = call.data.get("updates", {})
        if not reminder_id:
            return

        if not isinstance(updates, dict):
            raise ValueError("updates must be an object")

        if "target_time" in updates:
            _parse_future_target_time(updates["target_time"])

        updated = await storage.update_reminder(reminder_id, updates)
        if not updated:
            _LOGGER.warning("Cannot update reminder %s because it does not exist.", reminder_id)

    async def handle_delete_service(call):
        reminder_id = call.data.get("id")
        if reminder_id:
            deleted = await storage.delete_reminder(reminder_id)
            if not deleted:
                _LOGGER.warning(
                    "Cannot delete reminder %s because it does not exist.", reminder_id
                )

    async def handle_done_service(call):
        reminder_id = call.data.get("id")
        if reminder_id:
            updated = await storage.update_reminder(reminder_id, {"status": STATUS_DONE})
            if not updated:
                _LOGGER.warning("Cannot complete reminder %s because it does not exist.", reminder_id)

    async def handle_snooze_service(call):
        reminder_id = call.data.get("id")
        minutes = call.data.get("minutes", 10)
        if not reminder_id:
            return

        if minutes <= 0:
            raise ValueError("minutes must be greater than zero")

        new_start = dt_util.now()
        new_target = new_start + datetime.timedelta(minutes=minutes)
        updated = await storage.update_reminder(
            reminder_id,
            {
                "target_time": new_target.isoformat(),
                "start_time": new_start.isoformat(),
                "status": STATUS_ACTIVE,
                "notified": False,
            },
        )
        if not updated:
            _LOGGER.warning("Cannot snooze reminder %s because it does not exist.", reminder_id)

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


async def _send_notification(hass, reminder, notify_service):
    """Send notification for expired reminder."""
    title = reminder.get("title", "Reminder")
    message = reminder.get("message", "Reminder expired!")

    if reminder.get("notify_persistent"):
        hass.components.persistent_notification.async_create(
            message, title=title, notification_id=f"reminder_{reminder.get('id')}"
        )

    if reminder.get("notify_mobile"):
        try:
            domain, service = (
                notify_service.split(".", 1)
                if "." in notify_service
                else ("notify", "notify")
            )
            await hass.services.async_call(
                domain,
                service,
                {
                    "title": title,
                    "message": message,
                },
            )
        except Exception as e:
            _LOGGER.warning(
                "Failed to send mobile notification using %s: %s. Sending persistent notification instead.",
                notify_service,
                e,
            )
            hass.components.persistent_notification.async_create(
                f"Esec notificare telefon: {message}",
                title=title,
                notification_id=f"reminder_err_{reminder.get('id')}",
            )
