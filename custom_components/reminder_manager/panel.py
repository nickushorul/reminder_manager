import logging

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_URL_PATH, PANEL_TITLE, PANEL_ICON

_LOGGER = logging.getLogger(__name__)

async def async_setup_panel(hass: HomeAssistant):
    """Register the custom panel."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    if not domain_data.get("static_path_registered"):
        static_path = hass.config.path("custom_components/reminder_manager/www")
        await hass.http.async_register_static_paths(
            [StaticPathConfig("/reminder_manager_static", static_path, cache_headers=False)]
        )
        domain_data["static_path_registered"] = True

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "reminder-manager-panel",
                "module_url": "/reminder_manager_static/reminder-manager.js"
            }
        },
        require_admin=True,
        update=True,
    )
    _LOGGER.info("Reminder Manager panel registered.")
