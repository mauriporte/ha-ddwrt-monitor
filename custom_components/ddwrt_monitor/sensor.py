from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfDataRate, UnitOfInformation
from homeassistant.util import dt as dt_util

from .entity import DdwrtEntity

ROUTER_SENSORS = {
    # key: (name, icon, diagnostic)
    "lan_ip": ("LAN IP", "mdi:ip-network", False),
    "lan_mac": ("MAC", "mdi:network-outline", True),
    "gateway": ("Gateway", "mdi:router-network", True),
    "connections": ("Active connections", "mdi:lan-connect", True),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = [DdwrtRouterSensor(coordinator, k, *v) for k, v in ROUTER_SENSORS.items()]
    entities += [DdwrtUptimeSensor(coordinator), DdwrtTunnelIpSensor(coordinator)]
    entities += [DdwrtNetworkSensor(coordinator, iface) for iface in coordinator.data.networks]
    entities += [DdwrtPublicIpSensor(coordinator, "wan", "Public IP"), DdwrtPublicIpSensor(coordinator, "vpn", "VPN public IP")]
    entities += [DdwrtTrafficSensor(coordinator, iface, k, *v) for iface in coordinator.data.networks for k, v in TRAFFIC_SENSORS.items()]
    async_add_entities(entities)


class DdwrtPublicIpSensor(DdwrtEntity, SensorEntity):
    _attr_icon = "mdi:earth"

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, f"public_ip_{key}")
        self._key, self._attr_name = key, name

    @property
    def native_value(self):
        return (self.coordinator.data.public.get(self._key) or {}).get("ip")

    @property
    def extra_state_attributes(self):
        info = dict(self.coordinator.data.public.get(self._key) or {})
        info.pop("ip", None)
        updated = self.coordinator.data.public.get("updated")
        info["checked"] = dt_util.utc_from_timestamp(updated).isoformat() if updated else None
        return info


class DdwrtRouterSensor(DdwrtEntity, SensorEntity):
    def __init__(self, coordinator, key, name, icon, diagnostic):
        super().__init__(coordinator, key)
        self._key = key
        self._attr_name, self._attr_icon = name, icon
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return self.coordinator.data.router.get(self._key)


class DdwrtUptimeSensor(DdwrtEntity, SensorEntity):
    _attr_name = "Last boot"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, "last_boot")
        self._boot = None

    @property
    def native_value(self):
        secs = self.coordinator.data.router.get("uptime")
        if secs is None:
            return None
        boot = (dt_util.utcnow() - timedelta(seconds=secs)).replace(second=0, microsecond=0)
        # Uptime only has minute resolution: keep the previous value unless it moved by more than 2 min (= a reboot).
        if self._boot is None or abs((boot - self._boot).total_seconds()) > 120:
            self._boot = boot
        return self._boot

    @property
    def extra_state_attributes(self):
        secs = self.coordinator.data.router.get("uptime")
        return {"uptime_seconds": secs, "router_time": self.coordinator.data.router.get("router_time")}


class DdwrtTunnelIpSensor(DdwrtEntity, SensorEntity):
    _attr_name = "VPN tunnel IP"
    _attr_icon = "mdi:vpn"

    def __init__(self, coordinator):
        super().__init__(coordinator, "vpn_tunnel_ip")

    @property
    def native_value(self):
        return self.coordinator.data.vpn.get("tunnel_ip")

    @property
    def extra_state_attributes(self):
        return {"status": self.coordinator.data.vpn.get("status")}


class DdwrtNetworkSensor(DdwrtEntity, SensorEntity):
    """State = number of clients on this WiFi; attributes = the client list."""

    _attr_icon = "mdi:wifi"
    _attr_native_unit_of_measurement = "clients"

    def __init__(self, coordinator, iface):
        super().__init__(coordinator, f"clients_{iface}")
        self._iface = iface
        self._attr_name = f"{coordinator.data.networks[iface]['ssid']} clients"

    def _clients(self):
        return [c for c in self.coordinator.data.clients if c["iface"] == self._iface]

    @property
    def native_value(self):
        return len(self._clients())

    @property
    def extra_state_attributes(self):
        net = self.coordinator.data.networks.get(self._iface, {})
        return {
            "ssid": net.get("ssid"),
            "interface": self._iface,
            "subnet": f"{net['ip']}/{net['prefix']}" if net.get("ip") else None,
            "clients": [
                {**{k: c[k] for k in ("name", "ip", "mac", "signal", "connected")},
                 "downloaded_kb": _kb(c["down"]), "uploaded_kb": _kb(c["up"]),
                 "download_kbs": _kb(c["down_rate"]), "upload_kbs": _kb(c["up_rate"])}
                for c in self._clients()
            ],
        }


def _kb(value):
    return None if value is None else round(value / 1000, 1)


TRAFFIC_SENSORS = {
    # key: (name suffix, icon, is_rate)
    "down": ("downloaded", "mdi:download", False),
    "up": ("uploaded", "mdi:upload", False),
    "down_rate": ("download speed", "mdi:download-network", True),
    "up_rate": ("upload speed", "mdi:upload-network", True),
}


class DdwrtTrafficSensor(DdwrtEntity, SensorEntity):
    """Per-WiFi traffic from the interface byte counters (totals since router boot, speeds averaged over 1 min)."""

    def __init__(self, coordinator, iface, key, suffix, icon, is_rate):
        super().__init__(coordinator, f"{key}_{iface}")
        self._iface, self._key = iface, key
        self._attr_name = f"{coordinator.data.networks[iface]['ssid']} {suffix}"
        self._attr_icon = icon
        if is_rate:
            self._attr_device_class = SensorDeviceClass.DATA_RATE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfDataRate.KILOBYTES_PER_SECOND
        else:
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_native_unit_of_measurement = UnitOfInformation.KILOBYTES

    @property
    def native_value(self):
        return _kb((self.coordinator.data.traffic.get(self._iface) or {}).get(self._key))
