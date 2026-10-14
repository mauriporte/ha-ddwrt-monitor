"""DD-WRT Monitor: router status, VPN state and clients per WiFi network."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, ConnectError, DdwrtClient, DdwrtData

DOMAIN = "ddwrt_monitor"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)


class DdwrtCoordinator(DataUpdateCoordinator[DdwrtData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=60), config_entry=entry)
        d = entry.data
        self.client = DdwrtClient(d[CONF_HOST], d[CONF_USERNAME], d[CONF_PASSWORD], d.get(CONF_PORT, 80))

    async def _async_update_data(self) -> DdwrtData:
        try:
            return await self.client.fetch()
        except AuthError as err:
            raise ConfigEntryAuthFailed from err
        except ConnectError as err:
            raise UpdateFailed(str(err)) from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = DdwrtCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
