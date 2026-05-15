#!/usr/bin/env bash
# Called every 5 minutes by transmission-watch.timer.
# 1. Removes torrents that have finished seeding (Stopped) and are already synced.
# 2. Removes files in each torrent's Location dir that don't belong to any known torrent.
# 3. Shuts down transmission-daemon after IDLE_THRESHOLD seconds with no active torrents.
set -euo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/rsync-torrents/config"
[[ -f "$CONFIG" ]] || { echo "Missing config: $CONFIG" >&2; exit 1; }
# shellcheck source=/dev/null
source "$CONFIG"

TRANSMISSION_HOST="${TRANSMISSION_HOST:-localhost}"
TRANSMISSION_PORT="${TRANSMISSION_PORT:-9091}"
TRANSMISSION_USER="${TRANSMISSION_USER:-}"
TRANSMISSION_PASS="${TRANSMISSION_PASS:-}"
IDLE_THRESHOLD="${IDLE_THRESHOLD:-1800}"
STATE_FILE="${STATE_FILE:-${HOME}/.local/share/rsync-torrents/last-active}"
SYNCED_HASHES="${SYNCED_HASHES:-${HOME}/.local/share/rsync-torrents/synced-hashes}"

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$STATE_FILE")"
touch "$SYNCED_HASHES" 2>/dev/null || true

TR="${TRANSMISSION_HOST}:${TRANSMISSION_PORT}"
TR_AUTH=()
if [[ -n "$TRANSMISSION_USER" && -n "$TRANSMISSION_PASS" ]]; then
    TR_AUTH=(-n "${TRANSMISSION_USER}:${TRANSMISSION_PASS}")
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] watch: $*" >> "$LOG_FILE"; }

# Returns all torrent IDs (one per line), stripping the leading '*' on active ones.
all_ids() {
    transmission-remote "$TR" "${TR_AUTH[@]}" -l 2>/dev/null \
        | awk 'NR>1 && !/^Sum:/ { gsub(/[*]/, "", $1); print $1 }'
}

# Fetches the full info block for a torrent ID and prints key=value pairs for
# the fields we care about (State, Hash).
torrent_info() {
    local id="$1"
    transmission-remote "$TR" "${TR_AUTH[@]}" -t "$id" -i 2>/dev/null \
        | awk -F': ' '
            /^\s+State:/ { gsub(/^\s+/, "", $2); print "state=" $2 }
            /^\s+Hash:/  { gsub(/^\s+/, "", $2); print "hash="  $2 }
        '
}

# Prints "location<TAB>location/name" for every known torrent.
# Used to build both the set of known paths and the set of dirs to scan.
all_torrent_paths() {
    transmission-remote "$TR" "${TR_AUTH[@]}" -t all -i 2>/dev/null \
        | awk '
            /^\s+Name:/     { sub(/^\s+Name:\s*/, "");     name = $0 }
            /^\s+Location:/ { sub(/^\s+Location:\s*/, ""); sub(/\/+$/, "", $0); loc = $0 }
            loc != "" && name != "" { print loc "\t" loc "/" name; loc = ""; name = "" }
        '
}

# --- Step 1: remove stopped torrents whose files are already on the server ---
removed=0
while IFS= read -r id; do
    [[ -n "$id" ]] || continue

    state="" hash=""
    while IFS='=' read -r key value; do
        case "$key" in
            state) state="$value" ;;
            hash)  hash="$value"  ;;
        esac
    done < <(torrent_info "$id")

    [[ "$state" == "Stopped" || "$state" == "Finished" ]] || continue
    [[ -n "$hash" ]] || continue
    grep -qF "$hash" "$SYNCED_HASHES" 2>/dev/null || continue

    log "removing id=${id} hash=${hash} (seeding done, already synced)"
    if transmission-remote "$TR" "${TR_AUTH[@]}" -t "$id" --remove-and-delete 2>/dev/null; then
        (
            flock -e 200
            sed -i "/${hash}/d" "$SYNCED_HASHES"
        ) 200>"${SYNCED_HASHES}.lock"
        removed=$((removed + 1))
    fi
done < <(all_ids)

[[ "$removed" -gt 0 ]] && log "removed ${removed} finished torrent(s)"

# --- Step 2: remove orphaned files from torrent location dirs ---
if ! tr_list=$(transmission-remote "$TR" "${TR_AUTH[@]}" -l 2>/dev/null); then
    log "ERROR: transmission-remote -l failed. Skipping orphan cleanup."
else
    expected_count=$(echo "$tr_list" | awk 'NR>1 && !/^Sum:/ { count++ } END { print count+0 }')

    declare -A known=()
    declare -A scan_dirs=()
    actual_count=0
    while IFS=$'\t' read -r loc path; do
        if [[ -n "$path" ]]; then
            known["$path"]=1
            actual_count=$((actual_count + 1))
        fi
        [[ -n "$loc"  ]] && scan_dirs["$loc"]=1
    done < <(all_torrent_paths)

    if [[ "$actual_count" -lt "$expected_count" ]]; then
        log "ERROR: Incomplete torrent data (expected $expected_count, got $actual_count). Skipping orphan cleanup to prevent data loss."
    elif [[ "${#scan_dirs[@]}" -gt 0 ]]; then
        orphans=0
        for dir in "${!scan_dirs[@]}"; do
            [[ -d "$dir" ]] || continue
            while IFS= read -r -d '' item; do
                if [[ -z "${known[$item]+x}" ]]; then
                    log "removing orphan: $item"
                    if rm -rf -- "$item" 2>/dev/null; then
                        orphans=$((orphans + 1))
                    else
                        log "WARN failed to remove: $item"
                    fi
                fi
            done < <(find "$dir" -maxdepth 1 -mindepth 1 -print0)
        done
        [[ "$orphans" -gt 0 ]] && log "removed ${orphans} orphaned item(s)"
    fi
fi

# --- Step 3: idle-shutdown check ---
# Count torrents still downloading or seeding.
active=$(transmission-remote "$TR" "${TR_AUTH[@]}" -l 2>/dev/null \
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
    systemctl stop transmission-daemon.service 2>/dev/null || true
    rm -f "$STATE_FILE"
fi
