import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

class ReminderManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Reminder Manager."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Reminder Manager", data=user_input)

        data_schema = vol.Schema({
            vol.Optional("notify_service", default="notify.notify"): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ReminderManagerOptionsFlowHandler()


class ReminderManagerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Reminder Manager.

    Note: starting with Home Assistant 2024.11 the framework injects
    ``self.config_entry`` automatically and explicitly assigning to it in
    ``__init__`` was removed in 2025.12 (causes HTTP 500 when the user
    opens the integration's settings cog). We rely on the inherited
    attribute and avoid overriding the constructor.
    """

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_notify_service = self.config_entry.options.get(
            "notify_service",
            self.config_entry.data.get("notify_service", "notify.notify"),
        )

        data_schema = vol.Schema({
            vol.Optional("notify_service", default=current_notify_service): str,
        })

        return self.async_show_form(
            step_id="init", data_schema=data_schema
        )
