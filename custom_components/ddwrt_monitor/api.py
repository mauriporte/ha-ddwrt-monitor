"""DD-WRT web status client. Reads the same *.live.asp pages the DD-WRT web UI and HA's ddwrt tracker use."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass, field

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
IFACE_RE = re.compile(r"^(wlan|ath|wl|eth)\d+(\.\d+)?$")
KV_RE = re.compile(r"\{(\w+)::(.*?)\}", re.S)


class AuthError(Exception):
    """Wrong username or password."""


class ConnectError(Exception):
    """Router unreachable or unexpected answer."""


def parse_kv(text: str) -> dict[str, str]:
    return {k: v.strip() for k, v in KV_RE.findall(text)}


def split_list(value: str) -> list[str]:
    """DD-WRT lists look like: 'a','b','c' (sometimes with spaces/newlines)."""
    return re.findall(r"'([^']*)'", value or "")


def parse_uptime(value: str) -> int | None:
    """' 17:16:33 up 3 days,  2:48, load average: ...' -> seconds."""
    m = re.search(r"up\s+(.*?),\s+load", value or "")
    if not m:
        return None
    secs = 0
    for part in m.group(1).split(","):
        part = part.strip()
        if d := re.match(r"(\d+)\s+days?", part):
            secs += int(d.group(1)) * 86400
        elif hm := re.match(r"(\d+):(\d+)$", part):
            secs += int(hm.group(1)) * 3600 + int(hm.group(2)) * 60
        elif mn := re.match(r"(\d+)\s+min", part):
            secs += int(mn.group(1)) * 60
    return secs


def parse_leases(value: str) -> dict[str, dict]:
    """dhcp_leases: groups of 5 -> hostname, ip, mac, lease time, index. Keyed by MAC."""
    items = split_list(value)
    out = {}
    for i in range(0, len(items) - 2, 5):
        name, ip, mac = items[i], items[i + 1], items[i + 2]
        if MAC_RE.match(mac):
            out[mac.upper()] = {"name": None if name in ("", "*") else name, "ip": ip}
    return out


def parse_arp(value: str) -> dict[str, dict]:
    """arp_table: groups of 8 -> hostname, ip, mac, conns, iface, in, out, total. Keyed by MAC.

    in/out are bytes downloaded/uploaded by that client (DD-WRT per-IP accounting; accurate only with SFE off).
    """
    items = split_list(value)
    out = {}
    for i, item in enumerate(items):
        if MAC_RE.match(item) and i >= 1:
            name = items[i - 2] if i >= 2 else ""
            j = next((k for k in range(i + 1, min(i + 4, len(items))) if IFACE_RE.match(items[k]) or items[k].startswith("br")), None)
            nums = items[j + 1 : j + 3] if j is not None else []
            down, up = (int(n) for n in nums) if len(nums) == 2 and all(n.isdigit() for n in nums) else (None, None)
            out[item.upper()] = {"ip": items[i - 1], "name": None if name in ("", "*") else name,
                                 "iface": items[j] if j is not None else None, "down": down, "up": up}
    return out


def parse_wireless(value: str) -> list[dict]:
    """active_wireless: one record per client, starting with its MAC; field count varies by build."""
    items = split_list(value)
    starts = [i for i, x in enumerate(items) if MAC_RE.match(x)]
    clients = []
    for n, s in enumerate(starts):
        rec = items[s : starts[n + 1] if n + 1 < len(starts) else len(items)]
        iface = next((x for x in rec[1:] if IFACE_RE.match(x)), None)
        uptime = next((x for x in rec[1:] if re.match(r"^\d+:\d{2}:\d{2}$|^\d+ days?", x)), None)
        signal = next((int(x) for x in rec[1:] if re.match(r"^-\d{2,3}$", x)), None)
        clients.append({"mac": rec[0].upper(), "iface": iface, "connected": uptime, "signal": signal})
    return clients


def parse_openvpn(html: str) -> dict:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    status = re.search(r"Client:\s*([A-Z][A-Z ]+?)(?:\s+Local Address|\s+VPN Client|$)", text)
    local = re.search(r"Local Address:\s*([\d.]+)", text)
    return {
        "status": status.group(1).strip() if status else None,
        "connected": bool(status and "CONNECTED" in status.group(1) and "NOT" not in status.group(1)),
        "tunnel_ip": local.group(1) if local else None,
    }


def parse_networks(html: str) -> dict[str, dict]:
    """Wireless_Basic.asp form fields -> {iface: {ssid, subnet}} for each radio / virtual AP."""
    nets: dict[str, dict] = {}
    for iface, ssid in re.findall(r'name="(wlan\d+(?:\.\d+)?)_ssid"[^>]*?value="([^"]*)"', html):
        octets = [re.search(rf'name="{re.escape(iface)}_ipaddr_{i}"[^>]*?value="(\d+)"', html) for i in range(4)]
        mask = re.search(rf'name="{re.escape(iface)}_netmask"[^>]*?value="(\d+)"', html)
        ip = ".".join(o.group(1) for o in octets) if all(octets) else None
        nets[iface] = {"ssid": ssid, "ip": ip if ip and ip != "0.0.0.0" else None, "prefix": mask.group(1) if mask else None}
    return nets


def parse_monitor(text: str) -> dict:
    """/user/monitor.txt (JSON) written by the router's cron job:
    {"wan": {...ip-api...}, "vpn": {...}, "ifaces": {"wlan0": [rx, tx], ...}, "updated": epoch}."""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    out = {"updated": data.get("updated"), "ifaces": {}}
    for key in ("wan", "vpn"):
        v = data.get(key) or {}
        ok = v.get("status") == "success"
        out[key] = {"ip": v.get("query") if ok else None, "country": v.get("country"), "country_code": v.get("countryCode"), "isp": v.get("isp")}
    for iface, (rx, tx) in (data.get("ifaces") or {}).items():
        out["ifaces"][iface] = {"down": tx, "up": rx}  # router tx = what clients download
    return out


@dataclass
class DdwrtData:
    router: dict = field(default_factory=dict)
    networks: dict = field(default_factory=dict)
    clients: list = field(default_factory=list)
    vpn: dict = field(default_factory=dict)
    public: dict = field(default_factory=dict)
    traffic: dict = field(default_factory=dict)  # per WiFi interface: down/up bytes and down_rate/up_rate bytes/s


class RateTracker:
    """Bytes/s from successive counter readings; None on the first reading or after a counter reset."""

    def __init__(self) -> None:
        self._prev: dict = {}

    def rate(self, key, value, when):
        if value is None:
            return None  # keep the last valid reading: a client can drop out of one poll while roaming/reconnecting
        prev = self._prev.get(key)
        self._prev[key] = (value, when)
        if prev is None or when <= prev[1] or value < prev[0]:
            return None
        return (value - prev[0]) / (when - prev[1])


class DdwrtClient:
    def __init__(self, host: str, username: str, password: str, port: int = 80) -> None:
        self.host, self.port = host, port
        self._auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._networks: dict = {}
        self._networks_age = 0
        self._rates = RateTracker()
        self._iface_rates: dict = {}

    async def _get(self, path: str) -> str:
        # Plain HTTP/1.0: DD-WRT's httpd sends headers some strict parsers reject (e.g. Status_OpenVPN.asp).
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 10)
            writer.write(f"GET /{path} HTTP/1.0\r\nHost: {self.host}\r\nAuthorization: Basic {self._auth}\r\nConnection: close\r\n\r\n".encode())
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(), 20)
            writer.close()
        except (OSError, asyncio.TimeoutError) as err:
            raise ConnectError(str(err)) from err
        head, _, body = raw.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0]
        if b" 401" in status:
            raise AuthError
        if b" 200" not in status:
            raise ConnectError(status.decode(errors="replace"))
        return body.decode(errors="replace")

    async def fetch(self) -> DdwrtData:
        router = parse_kv(await self._get("Status_Router.live.asp"))
        lan = parse_kv(await self._get("Status_Lan.live.asp"))
        wl = parse_kv(await self._get("Status_Wireless.live.asp"))
        vpn = parse_openvpn(await self._get("Status_OpenVPN.asp"))
        # SSIDs/subnets rarely change: the settings page is large, so read it every 10th poll only.
        if not self._networks or self._networks_age >= 10:
            self._networks, self._networks_age = parse_networks(await self._get("Wireless_Basic.asp")), 0
        self._networks_age += 1
        # Optional: only present when the router runs the pubip.sh cron job.
        try:
            monitor = parse_monitor(await self._get("user/monitor.txt"))
        except ConnectError:
            monitor = {}
        now = time.monotonic()

        leases, arp = parse_leases(lan.get("dhcp_leases", "")), parse_arp(lan.get("arp_table", ""))
        clients = []
        for c in parse_wireless(wl.get("active_wireless", "")):
            info = leases.get(c["mac"]) or {}
            seen = arp.get(c["mac"]) or {}
            down, up = seen.get("down"), seen.get("up")
            clients.append({**c, "name": info.get("name") or seen.get("name"), "ip": info.get("ip") or seen.get("ip"),
                            "down": down, "up": up,
                            "down_rate": self._rates.rate(("dev_down", c["mac"]), down, now),
                            "up_rate": self._rates.rate(("dev_up", c["mac"]), up, now)})

        # Interface counters come from the cron file (once a minute): only recompute rates when it was rewritten.
        traffic = {}
        updated = monitor.get("updated")
        for iface, t in (monitor.get("ifaces") or {}).items():
            if updated and self._iface_rates.get(iface, (None,))[0] != updated:
                self._iface_rates[iface] = (updated, self._rates.rate(("if_down", iface), t["down"], updated),
                                            self._rates.rate(("if_up", iface), t["up"], updated))
            _, down_rate, up_rate = self._iface_rates.get(iface, (None, None, None))
            traffic[iface] = {**t, "down_rate": down_rate, "up_rate": up_rate}

        return DdwrtData(
            router={
                "uptime": parse_uptime(router.get("uptime", "")),
                "router_time": router.get("router_time"),
                "lan_ip": lan.get("lan_ip", "").split("/")[0] or None,
                "lan_mac": lan.get("lan_mac"),
                "gateway": lan.get("lan_gateway"),
                "dns": lan.get("lan_dns"),
                "connections": int(router["ip_conntrack"]) if router.get("ip_conntrack", "").isdigit() else None,
            },
            networks=self._networks,
            clients=clients,
            vpn=vpn,
            public=monitor,
            traffic=traffic,
        )
