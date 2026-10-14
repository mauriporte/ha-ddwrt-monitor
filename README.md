# DD-WRT Monitor for Home Assistant

A Home Assistant custom integration for routers running [DD-WRT](https://dd-wrt.com/). It shows the router's status, the OpenVPN client state, every WiFi network with the devices connected to it, and how much each network and each device is downloading and uploading.

It is built for DD-WRT used as an **access point with OpenVPN-routed WiFi networks** (separate, unbridged WiFi networks sent through the VPN with policy-based routing), but works on any DD-WRT router. Parts that don't apply to your setup simply show no value.

## Features

| Area | What you get |
|---|---|
| Router | LAN IP, MAC, gateway, last boot, active connections |
| OpenVPN client | Connected/disconnected (binary sensor), tunnel IP, status text |
| Public IPs *(optional, router script)* | Public IP of the normal connection and of the VPN, with country and ISP |
| Each WiFi network | Number of connected devices; the device list (name, IP, MAC, signal, connected time) as attributes |
| Traffic per network *(optional, router script)* | Downloaded / uploaded totals (kB) and download / upload speed (kB/s) |
| Traffic per device | Downloaded / uploaded totals and current speeds, in each device's entry of the network's device list |

## How it works

The integration polls the router's own web status pages over HTTP, once a minute, using the web interface login. This is the same method as Home Assistant's built-in DD-WRT device tracker:

- `Status_Router.live.asp`, `Status_Lan.live.asp`, `Status_Wireless.live.asp` and `Status_OpenVPN.asp` on every poll
- `Wireless_Basic.asp` (network names and subnets) every 10 polls

Nothing is installed on the router for the core features. The optional router script publishes the extra data as a small file served by the router's own web server.

## Installation

There are two ways to install it. **HACS is the easiest** and also gives you updates. Use the manual method if you don't have HACS.

### Option A: HACS (recommended)

1. In Home Assistant, open **HACS**, then the **⋮** menu (top right) → **Custom repositories**.
2. Paste this repository's URL, choose the category **Integration**, and click **Add**.
3. Search HACS for **DD-WRT Monitor**, open it and click **Download**.
4. Restart Home Assistant (**Settings → System**, power button at the top right → **Restart Home Assistant**).

### Option B: Manual

You copy one folder, `ddwrt_monitor`, into a folder called `custom_components` inside Home Assistant's **configuration folder**. That's the folder containing `configuration.yaml`.

**1. Find your configuration folder.** It depends on how Home Assistant is installed. Not sure which one you have? Go to **Settings → System → Repairs**, open the **⋮** menu → **System information**, and look at *Installation type*.

| Installation type | Where the configuration folder is | Easiest way to copy files there |
|---|---|---|
| **Home Assistant OS** (Raspberry Pi, Home Assistant Green/Yellow, virtual machine) | `/config` | The **Samba share** add-on (it appears as the `config` network share on your computer), or the **File editor** / **Studio Code Server** add-ons |
| **Home Assistant Supervised** | `/usr/share/hassio/homeassistant` on the host (`/config` inside add-ons) | Same add-ons as above, or SSH to the host |
| **Home Assistant Container** (Docker, including NAS systems like ZimaOS, CasaOS, Unraid, Synology, TrueNAS) | The host folder mapped to `/config` in the container. Find it in your `docker-compose.yml` (`volumes: - /some/host/path:/config`), in the app's settings on your NAS, or with `docker inspect homeassistant` | Your NAS file manager, a network share, or `scp` to the host |
| **Home Assistant Core** (Python virtual environment) | Usually `~/.homeassistant` for the user that runs Home Assistant | Copy directly on that machine |

**2. Copy the folder.** Download this repository (green **Code** button → **Download ZIP**) and unzip it. Copy the folder `custom_components/ddwrt_monitor` from the ZIP into your configuration folder. If `custom_components` doesn't exist there yet, create it. The result must look like this:

```
<configuration folder>/           ← the folder that contains configuration.yaml
├── configuration.yaml
├── custom_components/            ← create it if it doesn't exist
│   └── ddwrt_monitor/            ← copied from this repository
│       ├── __init__.py
│       ├── api.py
│       ├── manifest.json
│       ├── ...
│       └── translations/
└── ...
```

Common mistakes:
- Nesting one folder too deep (`custom_components/ddwrt_monitor/ddwrt_monitor/…`). `manifest.json` must sit directly inside `custom_components/ddwrt_monitor/`.
- Copying the whole repository instead of just the `ddwrt_monitor` folder.
- On Docker, copying into a folder on the host that isn't the one mapped to `/config`.

**3. Restart Home Assistant** (**Settings → System**, power button at the top right → **Restart Home Assistant**). Custom integrations are only loaded at startup.

## Configuration

**Settings → Devices & services → Add integration → DD-WRT Monitor**, then enter:

| Field | Value |
|---|---|
| Host | The router's LAN address |
| Username / Password | The router's web interface login |
| HTTP port | 80 unless you changed it |

## Router settings

### Device names

Turn on dnsmasq's lease file so device names are available. Under **Services → Services → Additional Dnsmasq Options**, add:

```
dhcp-leasefile=/tmp/dnsmasq.leases
```

### Accurate traffic numbers

DD-WRT's **Shortcut Forwarding Engine (SFE)** lets established connections bypass the kernel's counters, so traffic numbers come out far too low while it's on. Turn it off under **Setup → Basic Setup → Shortcut Forwarding Engine**.

On a router whose WiFi traffic goes through OpenVPN this costs nothing: tunnel traffic cannot use the fast path anyway. On a router doing plain high-speed routing it can lower throughput, so decide based on your setup.

### Optional router script: public IPs and per-network traffic

`scripts/ddwrt_startup.sh` installs a small script on the router that runs every minute. It writes `/tmp/www/monitor.txt`, which the router serves at `http://<router>/user/monitor.txt`. The file contains:

- the public IP, country and ISP of the normal connection and of the VPN, looked up through [ip-api.com](https://ip-api.com/) (free tier, about 2 requests per minute)
- the byte counters of every WiFi interface

To see the VPN's public IP, the script sends that one lookup through routing table `10`, the table DD-WRT's OpenVPN client uses for policy-based routing. The rule is removed again straight after the lookup.

**To install it:**
1. Paste the contents of `scripts/ddwrt_startup.sh` into **Administration → Commands** and click **Save Startup**.
2. Under **Administration → Management → Cron**, enable cron and add this job:
   ```
   * * * * * root /tmp/pubip.sh
   ```
3. Reboot the router, or click **Run Commands** once with the same script.

Without the script, the public IP and per-network traffic sensors stay empty. Everything else still works.

## Entities

Entity IDs depend on your device and network names. With the default device name **DD-WRT** and a network called `Guest`:

| Entity | Notes |
|---|---|
| `binary_sensor.dd_wrt_vpn` | OpenVPN client connected |
| `sensor.dd_wrt_vpn_tunnel_ip` | Tunnel address; attribute `status` |
| `sensor.dd_wrt_public_ip`, `sensor.dd_wrt_vpn_public_ip` | Router script; attributes `country`, `country_code`, `isp`, `checked` |
| `sensor.dd_wrt_lan_ip`, `sensor.dd_wrt_mac`, `sensor.dd_wrt_gateway` | |
| `sensor.dd_wrt_last_boot` | Timestamp; attribute `uptime_seconds` |
| `sensor.dd_wrt_active_connections` | Tracked connections (conntrack) |
| `sensor.dd_wrt_guest_clients` | State = device count. Attribute `clients`: `name`, `ip`, `mac`, `signal`, `connected`, `downloaded_kb`, `uploaded_kb`, `download_kbs`, `upload_kbs` |
| `sensor.dd_wrt_guest_downloaded`, `sensor.dd_wrt_guest_uploaded` | Router script; kB since router boot, `total_increasing` |
| `sensor.dd_wrt_guest_download_speed`, `sensor.dd_wrt_guest_upload_speed` | Router script; kB/s, averaged over one minute |

Units can be changed per entity in Home Assistant (for example to MB or GB).

## Dashboard example

A Markdown card listing each network's devices with their traffic:

```yaml
type: markdown
title: Guest WiFi
content: >-
  {% set n = states.sensor.dd_wrt_guest_clients %}
  **{{ n.attributes.ssid }}** · {{ n.attributes.subnet }} · {{ n.state }} device(s)

  | Name | IP | MAC | Signal | ↓ Total | ↑ Total | ↓ kB/s | ↑ kB/s |
  |---|---|---|---|---|---|---|---|
  {% for c in n.attributes.clients -%}
  | {{ c.name or '—' }} | {{ c.ip or '—' }} | {{ c.mac }} | {{ c.signal }} dBm | {{ c.downloaded_kb }} kB | {{ c.uploaded_kb }} kB | {{ c.download_kbs }} | {{ c.upload_kbs }} |
  {% endfor %}
```

## Limitations

- **Polling:** data is read every 60 seconds; speeds are averages over that interval and show as unknown until two readings exist.
- **Counter resets:** traffic totals restart from zero when the router reboots. `total_increasing` sensors handle this in long-term statistics.
- **Per-device counters** come from DD-WRT's own per-client accounting, which only counts traffic routed through the router (not traffic between devices on the same network).
- **HTTP only:** HTTPS to the router's web interface is not supported, so keep Home Assistant and the router on a trusted LAN.
- **Tested hardware:** a D-Link DIR-835 (Atheros) on DD-WRT r60137. Pages differ slightly between DD-WRT builds and chipsets; please open an issue with a sample if something isn't parsed.

## Development

```bash
python -m pytest tests                                                            # parser tests, no Home Assistant needed
DDWRT_HOST=192.168.1.1 DDWRT_PASSWORD=... python scripts/live_check.py           # query a real router
```

## License

MIT, see [LICENSE](LICENSE).
