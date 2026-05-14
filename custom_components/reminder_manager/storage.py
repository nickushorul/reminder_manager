import logging
from typing import Dict, Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from .const import STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

class ReminderStorage:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: Dict[str, Any] = {"reminders": []}

    async def async_load(self):
        """Load data from storage."""
        data = await self.store.async_load()
        if data:
            self.data = data
        else:
            self.data = {"reminders": []}
            await self.async_save()

    async def async_save(self):
        """Save data to storage."""
        await self.store.async_save(self.data)

    def get_reminders(self):
        return self.data.get("reminders", [])

    def get_reminder(self, reminder_id: str):
        for r in self.get_reminders():
            if r.get("id") == reminder_id:
                return r
        return None

    async def add_reminder(self, reminder: dict):
        reminders = self.get_reminders()
        reminders.append(reminder)
        self.data["reminders"] = reminders
        await self.async_save()

    async def add_reminders(self, reminders_to_add: list[dict]):
        reminders = self.get_reminders()
        reminders.extend(reminders_to_add)
        self.data["reminders"] = reminders
        await self.async_save()

    async def update_reminder(self, reminder_id: str, updates: dict):
        reminders = self.get_reminders()
        updated = False
        for r in reminders:
            if r.get("id") == reminder_id:
                r.update(updates)
                updated = True
                break
        if updated:
            self.data["reminders"] = reminders
            await self.async_save()
        return updated

    async def delete_reminder(self, reminder_id: str):
        reminders = self.get_reminders()
        reminders = [r for r in reminders if r.get("id") != reminder_id]
        if len(reminders) == len(self.get_reminders()):
            return False
        self.data["reminders"] = reminders
        await self.async_save()
        return True
