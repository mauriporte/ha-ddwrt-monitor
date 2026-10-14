from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, DdwrtCoordinator


class DdwrtEntity(CoordinatorEntity[DdwrtCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DdwrtCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        mac = coordinator.data.router.get("lan_mac")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            connections={(CONNECTION_NETWORK_MAC, mac.lower())} if mac else set(),
            name="DD-WRT",
            manufacturer="DD-WRT",
            configuration_url=f"http://{entry.data['host']}",
        )
