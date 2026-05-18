DOMAIN = "reminder_manager"
STORAGE_KEY = "reminder_manager.storage"
STORAGE_VERSION = 1

CONF_NOTIFY_MOBILE = "notify_mobile"
CONF_NOTIFY_PERSISTENT = "notify_persistent"

API_ENDPOINT = "/api/reminder_manager"
PANEL_URL_PATH = "reminder-manager"
PANEL_TITLE = "Reminder Manager"
PANEL_ICON = "mdi:calendar-clock"

STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_DONE = "done"
STATUS_DELETED = "deleted"

REPEAT_NONE = "none"
REPEAT_MONTHLY = "monthly"

TRIGGER_TIME = "time"
TRIGGER_LOCATION = "location"
TRIGGER_TIME_AND_LOCATION = "time_and_location"

ZONE_EVENT_ENTER = "enter"
ZONE_EVENT_LEAVE = "leave"

# A monthly reminder whose target_time is older than this is considered stale
# and gets advanced silently instead of producing a notification storm after a
# long Home Assistant outage.
STALE_RECURRING_THRESHOLD_HOURS = 12
