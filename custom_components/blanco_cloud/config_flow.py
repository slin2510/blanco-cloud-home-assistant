from __future__ import annotations

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from blanco_smart_home_api_client import BlancoApiClient, BlancoApiError

from .const import DOMAIN

DEVICE_ID_RE = re.compile(r"^[0-9a-fA-F]{64}$")


async def _validate_device(hass: HomeAssistant, device_id: str) -> None:
    client = BlancoApiClient(
        async_get_clientsession(hass),
        app_version="0.1.0",
        app_build="1",
        os_version="Home Assistant",
    )
    await client.register_app("en")
    await client.authenticate(device_id)


class BlancoCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip()
            if not DEVICE_ID_RE.fullmatch(device_id):
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            else:
                await self.async_set_unique_id(device_id.lower())
                self._abort_if_unique_id_configured()
                try:
                    await _validate_device(self.hass, device_id)
                except BlancoApiError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=f"BLANCO {device_id[-8:]}",
                        data={CONF_DEVICE_ID: device_id, "locale": "en"},
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID): str}),
            errors=errors,
        )
