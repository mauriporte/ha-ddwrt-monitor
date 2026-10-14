from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import DdwrtEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DdwrtVpnSensor(entry.runtime_data)])


class DdwrtVpnSensor(DdwrtEntity, BinarySensorEntity):
    _attr_name = "VPN"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator):
        super().__init__(coordinator, "vpn_connected")

    @property
    def is_on(self):
        return self.coordinator.data.vpn.get("connected")
