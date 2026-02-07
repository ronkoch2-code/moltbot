# CelticXfer Heartbeat

Automated heartbeat for the CelticXfer agent on Moltbook, using Claude Code CLI.

## Setup

### 1. Verify prerequisites

```bash
claude --version       # Claude Code CLI
jq --version           # JSON parser
docker compose version # Docker (for MCP server)
```

### 2. Make the script executable

```bash
chmod +x celticxfer_heartbeat.sh
```

### 3. Test manually

```bash
./celticxfer_heartbeat.sh
```

Check `heartbeat.log` for output.

### 4. Install the launchd agent (runs every 4 hours)

```bash
cp com.celticxfer.moltbook.heartbeat.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.celticxfer.moltbook.heartbeat.plist
```

### 5. Verify it's loaded

```bash
launchctl list | grep celticxfer
```

## Managing

```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.celticxfer.moltbook.heartbeat.plist

# Restart
launchctl unload ~/Library/LaunchAgents/com.celticxfer.moltbook.heartbeat.plist
launchctl load ~/Library/LaunchAgents/com.celticxfer.moltbook.heartbeat.plist

# Run manually
./celticxfer_heartbeat.sh

# Watch logs
tail -f heartbeat.log
```

## Files

| File | Purpose |
|------|---------|
| `celticxfer_heartbeat.sh` | Main heartbeat script |
| `config.json` | Agent credentials (gitignored) |
| `com.celticxfer.moltbook.heartbeat.plist` | macOS launchd schedule |
| `heartbeat.log` | Activity log |
| `heartbeat.error.log` | Error log |
| `heartbeat-state.json` | Last heartbeat timestamp + result |

## Notes

- The script checks that the Docker MCP server is running and starts it if not
- Interval is 4 hours (14400s) — adjust `StartInterval` in the plist
- The plist uses `WatchPaths` for `/Volumes/FS001` so it won't try to run if the volume isn't mounted
- `config.json` contains the API key and is gitignored — don't commit it
