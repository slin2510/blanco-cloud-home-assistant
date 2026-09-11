from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from blanco_smart_home_api_client import BlancoApiClient, BlancoApiError

from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import BlancoCloudCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = BlancoApiClient(
        session,
        app_version="0.1.0",
        app_build="1",
        os_version="Home Assistant",
    )
    try:
        await client.register_app(entry.data.get("locale", "en"))
        await client.authenticate(entry.data[CONF_DEVICE_ID])
    except BlancoApiError as err:
        raise ConfigEntryNotReady(f"Unable to connect to BLANCO Cloud: {err}") from err
    coordinator = BlancoCloudCoordinator(hass, client, entry.data[CONF_DEVICE_ID])
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_import_historical_data()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
