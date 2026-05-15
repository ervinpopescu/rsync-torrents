#!/usr/bin/env bash
set -euo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/rsync-torrents/config"
[[ -f "$CONFIG" ]] || { echo "Missing config: $CONFIG" >&2; exit 1; }
# shellcheck source=/dev/null
source "$CONFIG"

# Required config variables:
#   REMOTE_USER, REMOTE_HOST
#   REMOTE_PATH_MOVIES, REMOTE_PATH_SERIES, REMOTE_PATH_DEFAULT
#   LOG_FILE, SYNCED_HASHES
# Optional:
#   SSH_KEY  (path to identity file; leave empty to use ssh-agent/default key)

LOG_DIR="$(dirname "$LOG_FILE")"
mkdir -p "$LOG_DIR" "$(dirname "$SYNCED_HASHES")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

resolve_remote_path() {
    local labels="${TR_TORRENT_LABELS:-}"
    labels="${labels,,}"
    labels="${labels// /}"

    local IFS=','
    for label in $labels; do
        case "$label" in
            movie|movies) echo "$REMOTE_PATH_MOVIES"; return ;;
            serie|series|show|shows|tv) echo "$REMOTE_PATH_SERIES"; return ;;
        esac
    done

    log "WARN no recognised label in '${TR_TORRENT_LABELS:-}', using default path"
    echo "$REMOTE_PATH_DEFAULT"
}

SOURCE="${TR_TORRENT_DIR}/${TR_TORRENT_NAME}"
DEST="$(resolve_remote_path)"

echo "Syncing torrent: ${TR_TORRENT_NAME}"
echo "Logging to: ${LOG_FILE}"

log "START torrent='${TR_TORRENT_NAME}' labels='${TR_TORRENT_LABELS:-}' dest='${DEST}'"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
[[ -n "${SSH_KEY:-}" ]] && SSH_OPTS+=(-i "$SSH_KEY")

echo "Transferring files..."
rsync_rc=1
for attempt in 1 2 3 4 5; do
    rsync -avz --progress --partial \
        --chown=:"${REMOTE_GROUP:-media}" \
        --chmod=Dg+rwxs,Fg+rw \
        -e "ssh $(printf '%q ' "${SSH_OPTS[@]}")" \
        "$SOURCE" \
        "${REMOTE_USER}@${REMOTE_HOST}:$(printf '%q' "${DEST}/")" | tee -a "$LOG_FILE"
    rsync_rc=${PIPESTATUS[0]}
    [[ "$rsync_rc" -eq 0 ]] && break
    log "WARN rsync attempt ${attempt} failed (rc=${rsync_rc})"
    [[ "$attempt" -lt 5 ]] && sleep $((attempt * 30))
done

if [[ "$rsync_rc" -ne 0 ]]; then
    log "FAIL rsync failed after 5 attempts (rc=${rsync_rc}), not recording hash"
    exit "$rsync_rc"
fi

# Record this torrent as synced so transmission-watch.sh can safely delete it
# once seeding is complete.
echo "${TR_TORRENT_HASH}" >> "$SYNCED_HASHES"

log "DONE torrent='${TR_TORRENT_NAME}' hash='${TR_TORRENT_HASH}' synced and recorded"
echo "Sync complete."
