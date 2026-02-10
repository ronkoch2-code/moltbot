#!/bin/bash
# Diagnose dnsmasq/Docker networking issue on Zorin box
# Run: sudo bash /mnt/moltbot/testscript/check_dnsmasq.sh

OUTPUT="/mnt/moltbot/testscript/dnsmasq_diag.log"

echo "=== dnsmasq diagnostics — $(date -Iseconds) ===" > "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== dnsmasq processes ===" >> "$OUTPUT"
ps aux | grep dnsmasq >> "$OUTPUT" 2>&1

echo "" >> "$OUTPUT"
echo "=== dnsmasq config files ===" >> "$OUTPUT"
cat /etc/dnsmasq.conf 2>/dev/null >> "$OUTPUT" || echo "(no /etc/dnsmasq.conf)" >> "$OUTPUT"
echo "---" >> "$OUTPUT"
ls /etc/dnsmasq.d/ 2>/dev/null >> "$OUTPUT" || echo "(no /etc/dnsmasq.d/)" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== NetworkManager DNS config ===" >> "$OUTPUT"
grep -i dns /etc/NetworkManager/NetworkManager.conf 2>/dev/null >> "$OUTPUT" || echo "(not found)" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== /etc/resolv.conf ===" >> "$OUTPUT"
cat /etc/resolv.conf >> "$OUTPUT" 2>&1

echo "" >> "$OUTPUT"
echo "=== Docker info (proxy/dns) ===" >> "$OUTPUT"
docker info 2>&1 | grep -iE 'proxy|dns|driver|runtime' >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== Docker daemon config ===" >> "$OUTPUT"
cat /etc/docker/daemon.json 2>/dev/null >> "$OUTPUT" || echo "(no daemon.json)" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== Docker network inspect moltbot ===" >> "$OUTPUT"
docker network inspect moltbot_moltbook-net >> "$OUTPUT" 2>&1

echo "" >> "$OUTPUT"
echo "=== iptables NAT rules (docker) ===" >> "$OUTPUT"
iptables -t nat -L -n 2>&1 | grep -A2 -i docker >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== Docker container DNS config ===" >> "$OUTPUT"
docker exec moltbook-mcp-server cat /etc/resolv.conf >> "$OUTPUT" 2>&1

echo "" >> "$OUTPUT"
echo "=== dnsmasq listening ports ===" >> "$OUTPUT"
ss -tlnp | grep dnsmasq >> "$OUTPUT" 2>&1

echo "" >> "$OUTPUT"
echo "=== systemd-resolved status ===" >> "$OUTPUT"
systemctl status systemd-resolved 2>&1 | head -20 >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== dnsmasq CPU usage (5 second sample) ===" >> "$OUTPUT"
top -b -n 2 -d 5 -p "$(pgrep -d, dnsmasq)" 2>/dev/null | tail -5 >> "$OUTPUT" || echo "(could not sample)" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "=== Done — $(date -Iseconds) ===" >> "$OUTPUT"

echo "Diagnostics saved to $OUTPUT"
