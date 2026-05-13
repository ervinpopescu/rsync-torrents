#!/usr/bin/env bash
# Called every 5 minutes by transmission-watch.timer.
# 1. Removes torrents that have finished seeding (Stopped) and are already synced.
# 2. Shuts down transmission-daemon after IDLE_THRESHOLD seconds with no active torrents.
set -euo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/rsync-torrents/config"
[[ -f "$CONFIG" ]] || { echo "Missing config: $CONFIG" >&2; exit 1; }
# shellcheck source=/dev/null
source "$CONFIG"

TRANSMISSION_HOST="${TRANSMISSION_HOST:-localhost}"
TRANSMISSION_PORT="${TRANSMISSION_PORT:-9091}"
IDLE_THRESHOLD="${IDLE_THRESHOLD:-1800}"
STATE_FILE="${STATE_FILE:-${HOME}/.local/share/rsync-torrents/last-active}"
SYNCED_HASHES="${SYNCED_HASHES:-${HOME}/.local/share/rsync-torrents/synced-hashes}"

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$STATE_FILE")"
touch "$SYNCED_HASHES" 2>/dev/null || true

TR="${TRANSMISSION_HOST}:${TRANSMISSION_PORT}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] watch: $*" >> "$LOG_FILE"; }

# Returns all torrent IDs (one per line), stripping the leading '*' on active ones.
all_ids() {
    transmission-remote "$TR" -l 2>/dev/null \
        | awk 'NR>1 && !/^Sum:/ { gsub(/[*]/, "", $1); print $1 }'
}

# Fetches the full info block for a torrent ID and prints key=value pairs for
# the fields we care about (State, Hash).
torrent_info() {
    local id="$1"
    transmission-remote "$TR" -t "$id" -i 2>/dev/null \
        | awk -F': ' '
            /^\s+State:/ { gsub(/^\s+/, "", $2); print "state=" $2 }
            /^\s+Hash:/  { gsub(/^\s+/, "", $2); print "hash="  $2 }
        '
}

# --- Step 1: remove stopped torrents whose files are already on the server ---
removed=0
while IFS= read -r id; do
    [[ -n "$id" ]] || continue

    state="" hash=""
    # shellcheck disable=SC1090
    while IFS= read -r line; do eval "$line"; done < <(torrent_info "$id")

    [[ "$state" == "Stopped" ]] || continue
    [[ -n "$hash" ]] || continue
    grep -qF "$hash" "$SYNCED_HASHES" 2>/dev/null || continue

    log "removing id=${id} hash=${hash} (seeding done, already synced)"
    if transmission-remote "$TR" -t "$id" --remove-and-delete 2>/dev/null; then
        sed -i "/${hash}/d" "$SYNCED_HASHES"
        removed=$((removed + 1))
    fi
done < <(all_ids)

[[ "$removed" -gt 0 ]] && log "removed ${removed} finished torrent(s)"

# --- Step 2: idle-shutdown check ---
# Count torrents still downloading or seeding.
active=$(transmission-remote "$TR" -l 2>/dev/null \
    | awk 'NR>1 && !/^Sum:/ {
        for (i=1; i<=NF; i++) {
            if ($i ~ /^(Seeding|Downloading|Up|Down|Up&Down)$/) { count++; break }
        }
    } END { print count+0 }')

now=$(date +%s)

if [[ "$active" -gt 0 ]]; then
    echo "$now" > "$STATE_FILE"
    log "active torrents: ${active}, idle clock reset"
    exit 0
fi

if [[ ! -f "$STATE_FILE" ]]; then
    echo "$now" > "$STATE_FILE"
    log "no active torrents, idle clock started"
    exit 0
fi

last_active=$(cat "$STATE_FILE")
idle_seconds=$(( now - last_active ))
log "idle for ${idle_seconds}s (threshold ${IDLE_THRESHOLD}s)"

if [[ "$idle_seconds" -ge "$IDLE_THRESHOLD" ]]; then
    log "stopping transmission-daemon"
    systemctl --user stop transmission-daemon.service 2>/dev/null \
        || systemctl stop transmission-daemon.service 2>/dev/null \
        || true
    rm -f "$STATE_FILE"
fi
