# ddwrt_monitor: writes /tmp/pubip.sh at boot; cron runs it every minute.
cat > /tmp/pubip.sh <<'EOF'
#!/bin/sh
# Publishes the WAN (normal) and VPN public IPs and WiFi byte counters for Home Assistant
# at http://<router>/user/monitor.txt (JSON; DD-WRT httpd only serves known extensions)
q() { wget -q -T 8 -O - "http://ip-api.com/json/?fields=status,country,countryCode,isp,query" 2>/dev/null; }
ip rule del pref 100 2>/dev/null
wan=$(q)
vpn=""
a=$(nslookup ip-api.com 2>/dev/null | sed -n '/^Name/,$p' | grep -oE '([0-9]+\.){3}[0-9]+' | head -1)
# The router's own traffic leaves via the main router; route just this lookup through the VPN table to see the VPN exit IP.
if [ -n "$a" ] && ip -4 addr show tun1 2>/dev/null | grep -q inet; then
  ip rule add to "$a" lookup 10 pref 100 && vpn=$(q)
  ip rule del pref 100 2>/dev/null
fi
# Byte counters per WiFi interface (rx = uploaded by clients, tx = downloaded by clients). Needs nvram sfe=0 to be accurate.
ifaces=$(awk '/wlan[0-9]/ {sub(/^ */, ""); split($0, a, /[: ]+/); printf "%s\"%s\":[%s,%s]", s, a[1], a[2], a[10]; s=","}' /proc/net/dev)
echo "{\"wan\":${wan:-null},\"vpn\":${vpn:-null},\"ifaces\":{${ifaces}},\"updated\":$(date +%s)}" > /tmp/www/monitor.tmp && mv /tmp/www/monitor.tmp /tmp/www/monitor.txt
EOF
chmod +x /tmp/pubip.sh
