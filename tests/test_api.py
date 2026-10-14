"""Parser tests for custom_components/ddwrt_monitor/api.py (no Home Assistant needed).

Run: python -m pytest tests   (or: python tests/test_api.py)
Sample data uses documentation IP ranges and locally administered MAC addresses.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "ddwrt_monitor"))
import api  # noqa: E402

MAC_A = "02:00:00:00:00:0A"
MAC_B = "02:00:00:00:00:0B"


def test_uptime():
    assert api.parse_uptime(" 17:16:33 up 2:48, load average: 0.00") == 2 * 3600 + 48 * 60
    assert api.parse_uptime(" 17:16:33 up 3 days,  2:48, load average: 0.1") == 3 * 86400 + 2 * 3600 + 48 * 60
    assert api.parse_uptime(" 17:16:33 up 5 min, load average: 0.1") == 300
    assert api.parse_uptime("garbage") is None


def test_leases():
    leases = api.parse_leases(f"'tablet','192.168.2.118','{MAC_A.lower()}','23:59:01','118','*','192.168.1.120','{MAC_B}','1 day 00:00:00','120'")
    assert leases[MAC_A] == {"name": "tablet", "ip": "192.168.2.118"}
    assert leases[MAC_B]["name"] is None


def test_arp_with_traffic():
    arp = api.parse_arp(f"'phone','192.168.1.118','{MAC_A}','40', 'wlan0','230158','405381','635539','*','192.168.0.1','{MAC_B}','0', 'br0','0','0','0'")
    assert arp[MAC_A] == {"ip": "192.168.1.118", "name": "phone", "iface": "wlan0", "down": 230158, "up": 405381}
    assert arp[MAC_B]["iface"] == "br0" and arp[MAC_B]["name"] is None


def test_wireless_clients():
    wl = api.parse_wireless(
        f"'{MAC_A}','','wlan1','0:12:34','866M','780M','VHT80SGI','-48','-95','47','1000',"
        f"'{MAC_B}','','wlan0','1 day, 2:03:04','72M','65M','HT20','-61','-95','34','800'"
    )
    assert [(c["mac"], c["iface"], c["signal"]) for c in wl] == [(MAC_A, "wlan1", -48), (MAC_B, "wlan0", -61)]
    assert wl[0]["connected"] == "0:12:34"


def test_openvpn():
    vpn = api.parse_openvpn("<b>Client:</b> CONNECTED SUCCESS <br>Local Address: 10.8.0.6<br>Remote Address: 10.8.0.6 VPN Client Stats")
    assert vpn == {"status": "CONNECTED SUCCESS", "connected": True, "tunnel_ip": "10.8.0.6"}
    assert api.parse_openvpn("Client: NOT CONNECTED VPN Client Stats")["connected"] is False


def test_networks():
    html = ('<input name="wlan0_ssid" value="Guest"><input name="wlan0_ipaddr_0" value="192"><input name="wlan0_ipaddr_1" value="168">'
            '<input name="wlan0_ipaddr_2" value="1"><input name="wlan0_ipaddr_3" value="1"><input name="wlan0_netmask" value="24">')
    assert api.parse_networks(html) == {"wlan0": {"ssid": "Guest", "ip": "192.168.1.1", "prefix": "24"}}


def test_monitor_file():
    pub = api.parse_monitor('{"wan":{"status":"success","country":"Spain","countryCode":"ES","isp":"Example ISP","query":"198.51.100.7"},'
                            '"vpn":null,"ifaces":{"wlan0":[100,900]},"updated":1791991500}')
    assert pub["wan"]["ip"] == "198.51.100.7" and pub["vpn"]["ip"] is None and pub["updated"] == 1791991500
    assert pub["ifaces"]["wlan0"] == {"down": 900, "up": 100}
    assert api.parse_monitor("<html>404</html>") == {}


def test_rate_tracker():
    rt = api.RateTracker()
    assert rt.rate("k", 1000, 10) is None  # first reading
    assert rt.rate("k", 7000, 70) == 100  # 6000 bytes / 60 s
    assert rt.rate("k", 50, 130) is None  # counter reset (reboot)
    assert rt.rate("k", None, 190) is None  # client missing from one poll...
    assert rt.rate("k", 6050, 250) == 50  # ...rate resumes from the last valid reading


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all tests passed")
