import datetime
import logging
import uuid

from homeassistant.components.frontend import async_remove_panel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import ReminderManagerAPI
from .const import (
    DOMAIN,
    PANEL_URL_PATH,
    STALE_RECURRING_THRESHOLD_HOURS,
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_EXPIRED,
    ZONE_EVENT_ENTER,
    ZONE_EVENT_LEAVE,
)
from .panel import async_setup_panel
from .reminders import (
    build_next_monthly_reminder,
    enrich_repeat_metadata,
    haversine_meters,
    is_monthly_repeat,
    is_within_active_window,
    location_reminder_expired,
    normalize_reminder_payload,
    normalize_reminder_updates,
    reminder_has_location_trigger,
    reminder_has_time_trigger,
    reminder_targets,
    resolve_zone_coordinates,
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


def _notification_tag(reminder_id: str, phase: str = "countdown") -> str:
    """Return the mobile notification tag for a reminder notification phase."""
    return f"reminder_manager_{reminder_id}_{phase}"


def _notification_progress(reminder: dict, now_utc, target_time_utc) -> int | None:
    """Return a 0-100 progress value for Android progress notifications."""
    start_time = reminder.get("start_time")
    if not start_time:
        return None

    parsed_start = dt_util.parse_datetime(start_time)
    if not parsed_start:
        return None

    start_time_utc = dt_util.as_utc(parsed_start)
    total_seconds = int((target_time_utc - start_time_utc).total_seconds())
    if total_seconds <= 0:
        return None

    elapsed_seconds = int((now_utc - start_time_utc).total_seconds())
    progress = round((max(0, min(elapsed_seconds, total_seconds)) / total_seconds) * 100)
    return max(0, min(progress, 100))


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
        await _expire_stale_location_reminders(storage)

    entry.async_on_unload(async_track_time_interval(hass, check_reminders, _CHECK_INTERVAL))
    hass.async_create_task(check_reminders(None))

    @callback
    def handle_tracker_state_change(event: Event) -> None:
        """Schedule a location-trigger evaluation when a tracked entity moves."""
        notify_service = domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE)
        hass.async_create_task(
            _process_location_change(hass, storage, event, notify_service)
        )

    entry.async_on_unload(
        async_track_state_change_event(
            hass,
            _list_tracked_entity_ids(hass),
            handle_tracker_state_change,
        )
    )
    hass.async_create_task(_evaluate_all_location_reminders(hass, storage, domain_data))

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
                "pre_notification_bucket": None,
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
            updates.setdefault("pre_notification_bucket", None)

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
                "pre_notification_bucket": None,
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
                    "pre_notification_bucket": None,
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


async def _clear_mobile_notifications(
    hass,
    reminder,
    notify_service,
    *,
    phases: tuple[str, ...] = ("countdown", "expired"),
):
    """Clear the mobile notification for a reminder across all configured targets."""
    reminder_id = reminder.get("id")
    if not reminder_id:
        return

    tags = [_notification_tag(reminder_id, phase) for phase in phases]
    notify_targets = reminder_targets(reminder) or ([notify_service] if notify_service else [])

    for target in notify_targets:
        for tag in tags:
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
    silent_update: bool = False,
    phase: str = "countdown",
    interruption_level: str | None = None,
    sound=None,
    progress: int | None = None,
):
    """Send a mobile notification to one configured notify target."""
    reminder_id = reminder.get("id")
    tag = _notification_tag(reminder_id, phase)
    data = {
        "tag": tag,
        "group": f"reminder_manager_{reminder_id}",
        "persistent": True,
        "sticky": True,
        "actions": _build_notification_actions(reminder_id),
        "url": f"/{PANEL_URL_PATH}",
        "clickAction": f"/{PANEL_URL_PATH}",
    }

    push_data = {}

    if silent_update:
        data["alert_once"] = True
        push_data["sound"] = "none"
        push_data["interruption-level"] = "passive"
    else:
        data["presentation_options"] = ["alert", "badge", "sound"]

    if interruption_level:
        push_data["interruption-level"] = interruption_level

    if sound is not None:
        push_data["sound"] = sound

    if push_data:
        data["push"] = push_data

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

    if progress is not None:
        data["progress"] = progress
        data["progress_max"] = 100

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


async def _send_pre_notification(
    hass,
    reminder,
    notify_service,
    remaining_seconds: int,
    *,
    silent_update: bool,
):
    """Send the pre-reminder mobile notification when the reminder enters the 5-minute window."""
    if not reminder.get("notify_mobile"):
        return

    title = reminder.get("title", "Reminder")
    message = reminder.get("message", "Reminder upcoming!")
    minutes_left = max(1, (remaining_seconds + 59) // 60)
    notify_targets = reminder_targets(reminder) or [notify_service]
    target_time = _parse_target_time(reminder["target_time"])
    progress = _notification_progress(reminder, dt_util.utcnow(), dt_util.as_utc(target_time))

    for target in notify_targets:
        try:
            await _send_mobile_notification(
                hass,
                target,
                reminder,
                f"{title} in curand",
                f"{message} Mai sunt aproximativ {minutes_left} minute.",
                countdown_seconds=remaining_seconds,
                silent_update=silent_update,
                phase="countdown",
                interruption_level="active" if not silent_update else None,
                sound="default" if not silent_update else None,
                progress=progress,
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

    await _clear_mobile_notifications(
        hass,
        reminder,
        notify_service,
        phases=("countdown",),
    )

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
                    f"{title} a expirat",
                    f"{message} Reminderul a expirat acum.",
                    phase="expired",
                    interruption_level="time-sensitive",
                    sound="default",
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

    stale_threshold = datetime.timedelta(hours=STALE_RECURRING_THRESHOLD_HOURS)

    for reminder in reminders:
        if reminder.get("status") != STATUS_ACTIVE or reminder.get("notified"):
            continue

        # Pure location triggers don't fire on time. Time+location reminders are
        # gated by active_from and only fire via the state-change handler.
        if not reminder_has_time_trigger(reminder):
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
            current_bucket = max(1, (remaining_seconds + 59) // 60) if remaining_seconds > 0 else None

            if (
                reminder.get("notify_mobile")
                and current_bucket is not None
                and 0 < remaining_seconds <= int(_PRE_NOTIFICATION_WINDOW.total_seconds())
                and reminder.get("pre_notification_bucket") != current_bucket
            ):
                await _send_pre_notification(
                    hass,
                    reminder,
                    notify_service,
                    remaining_seconds,
                    silent_update=bool(reminder.get("pre_notified")),
                )
                reminder["pre_notified"] = True
                reminder["pre_notification_bucket"] = current_bucket
                needs_save = True

            if current_time >= target_time_utc:
                missed_by = current_time - target_time_utc
                is_stale_recurring = (
                    is_monthly_repeat(reminder) and missed_by > stale_threshold
                )

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

                # Bug #2 fix: when a monthly reminder was missed by more than the
                # stale threshold (e.g. HA was offline), advance silently rather
                # than emitting a notification storm for each skipped occurrence.
                if not is_stale_recurring:
                    await _send_notification(hass, reminder, notify_service)
                else:
                    _LOGGER.info(
                        "Skipping stale recurring notification for reminder %s "
                        "(missed by %s, target was %s)",
                        reminder.get("id"),
                        missed_by,
                        target_time_str,
                    )

                reminder["status"] = STATUS_EXPIRED
                reminder["notified"] = True
                reminder["pre_notification_bucket"] = None
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


def _list_tracked_entity_ids(hass: HomeAssistant) -> list[str]:
    """Return the list of person entity ids to monitor for location changes."""
    return [state.entity_id for state in hass.states.async_all("person")]


def _zone_lookup_for_hass(hass: HomeAssistant):
    """Return a callable that resolves a zone entity id to its coordinates dict."""

    def lookup(zone_entity_id: str):
        state = hass.states.get(zone_entity_id)
        if not state:
            return None
        attrs = state.attributes or {}
        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")
        if latitude is None or longitude is None:
            return None
        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "radius": float(attrs.get("radius", 100)),
        }

    return lookup


def _state_user_id(state) -> str | None:
    """Extract the Home Assistant user_id associated with a tracker state."""
    if not state or not state.attributes:
        return None
    return state.attributes.get("user_id")


def _state_position(state) -> tuple[float, float] | None:
    """Extract (lat, lon) from a tracker state if available."""
    if not state or not state.attributes:
        return None
    latitude = state.attributes.get("latitude")
    longitude = state.attributes.get("longitude")
    if latitude is None or longitude is None:
        return None
    try:
        return float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None


async def _process_location_change(
    hass: HomeAssistant,
    storage: ReminderStorage,
    event: Event,
    notify_service: str,
) -> None:
    """Handle a state change on a tracked entity and fire matching reminders."""
    new_state = event.data.get("new_state")
    if not new_state:
        return
    user_id = _state_user_id(new_state)
    if not user_id:
        return
    position = _state_position(new_state)
    if not position:
        return

    await _evaluate_location_reminders_for_user(
        hass, storage, user_id, position, notify_service
    )


async def _evaluate_location_reminders_for_user(
    hass: HomeAssistant,
    storage: ReminderStorage,
    user_id: str,
    position: tuple[float, float],
    notify_service: str,
) -> None:
    """Evaluate all of a given user's location reminders against `position`."""
    zone_lookup = _zone_lookup_for_hass(hass)
    now = dt_util.utcnow()
    needs_save = False
    user_lat, user_lon = position

    for reminder in storage.get_reminders():
        if reminder.get("status") != STATUS_ACTIVE:
            continue
        if not reminder_has_location_trigger(reminder):
            continue
        target_user_ids = reminder.get("target_user_ids") or []
        if user_id not in target_user_ids:
            continue

        try:
            coords = resolve_zone_coordinates(reminder, zone_lookup)
        except Exception:
            _LOGGER.exception(
                "Failed to resolve zone for reminder %s", reminder.get("id")
            )
            continue
        if not coords:
            _LOGGER.debug(
                "Reminder %s references unknown zone, skipping",
                reminder.get("id"),
            )
            continue

        zone_lat, zone_lon, radius = coords
        distance = haversine_meters(user_lat, user_lon, zone_lat, zone_lon)
        in_zone = distance <= radius
        last_in_zone = bool(reminder.get("last_in_zone"))

        # Always remember the latest in/out state so enter/leave edges are
        # detected on the next move.
        if reminder.get("last_in_zone") != in_zone:
            reminder["last_in_zone"] = in_zone
            needs_save = True

        if not is_within_active_window(reminder, now):
            continue

        zone_event = reminder.get("zone_event") or ZONE_EVENT_ENTER
        crossed_enter = zone_event == ZONE_EVENT_ENTER and in_zone and not last_in_zone
        crossed_leave = zone_event == ZONE_EVENT_LEAVE and last_in_zone and not in_zone
        if not (crossed_enter or crossed_leave):
            continue

        try:
            await _send_notification(hass, reminder, notify_service)
        except Exception:
            _LOGGER.exception(
                "Failed to send location notification for reminder %s",
                reminder.get("id"),
            )
            continue

        if reminder.get("location_recurring"):
            # Recurring location reminder: stay active but mark that we've fired
            # this round; it will re-arm naturally on the next opposite edge.
            reminder["location_triggered"] = True
        else:
            reminder["status"] = STATUS_EXPIRED
            reminder["location_triggered"] = True
        needs_save = True

    if needs_save:
        await storage.async_save()


async def _evaluate_all_location_reminders(
    hass: HomeAssistant,
    storage: ReminderStorage,
    domain_data: dict,
) -> None:
    """Run a first-pass evaluation against current tracker positions on startup."""
    notify_service = domain_data.get("notify_service", _DEFAULT_NOTIFY_SERVICE)
    seen_users: set[str] = set()
    for state in hass.states.async_all("person"):
        user_id = _state_user_id(state)
        if not user_id or user_id in seen_users:
            continue
        position = _state_position(state)
        if not position:
            continue
        seen_users.add(user_id)
        await _evaluate_location_reminders_for_user(
            hass, storage, user_id, position, notify_service
        )


async def _expire_stale_location_reminders(storage: ReminderStorage) -> None:
    """Mark location reminders past their active_until window as expired."""
    needs_save = False
    now = dt_util.utcnow()
    for reminder in storage.get_reminders():
        if reminder.get("status") != STATUS_ACTIVE:
            continue
        if not reminder_has_location_trigger(reminder):
            continue
        if location_reminder_expired(reminder, now):
            reminder["status"] = STATUS_EXPIRED
            needs_save = True
    if needs_save:
        await storage.async_save()
