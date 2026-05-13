# rsync-torrents

Full workflow:

1. **Download** — Transmission downloads the torrent
2. **Sync** — on completion, `sync-torrent.sh` rsyncs it to the server (routed by label: movie/series) and records the hash
3. **Seed** — Transmission continues seeding until the ratio limit is reached, then marks the torrent Stopped
4. **Cleanup** — `transmission-watch.sh` (timer, every 5 min) detects Stopped+synced torrents, deletes local files, and removes them from the queue
5. **Shutdown** — once no torrents are active for 30 minutes, the daemon stops

## Files

| File | Purpose |
|---|---|
| `sync-torrent.sh` | Transmission done-script: rsync + record hash |
| `transmission-watch.sh` | Timer script: cleanup finished torrents + idle shutdown |
| `transmission-idle-shutdown.service` | Systemd oneshot service running the watch script |
| `transmission-idle-shutdown.timer` | Systemd timer (every 5 min, bound to the daemon) |
| `config.example` | Template config — copy to `~/.config/rsync-torrents/config` |

## Remote server setup

Run these once on the server (as root):

```bash
# Create the media group (if it doesn't exist)
groupadd -f media

# Add jellyfin and transmission to the group
usermod -aG media jellyfin
usermod -aG media transmission   # or whatever user runs transmission-daemon

# Create destination directories with correct ownership
mkdir -p /path/to/movies /path/to/series
chown root:media /path/to/movies /path/to/series
chmod 2775 /path/to/movies /path/to/series   # setgid so new files inherit the group
```

The `2775` mode (setgid + rwxrwxr-x) means any file or directory created inside inherits the `media` group automatically. The rsync flags `--chown=:media --chmod=Dg+rwxs,Fg+rw` reinforce this on every transfer.

## Setup

### 1. Install scripts

```bash
install -m 755 sync-torrent.sh ~/.local/bin/sync-torrent.sh
install -m 755 transmission-watch.sh ~/.local/bin/transmission-watch.sh
```

### 2. Create config

```bash
mkdir -p ~/.config/rsync-torrents
cp config.example ~/.config/rsync-torrents/config
$EDITOR ~/.config/rsync-torrents/config
```

### 3. Ensure passwordless SSH works

```bash
ssh-copy-id user@yourserver
```

### 4. Set the seed ratio limit in Transmission

Transmission stops seeding automatically when the ratio limit is reached. Set it once:

```bash
# e.g. stop seeding at ratio 1.0
transmission-remote --seedratio 1.0
```

Or in `settings.json` (stop daemon first):

```json
"seedRatioLimit": 1.0,
"seedRatioLimited": true
```

Per-torrent override: right-click → Edit → Seeding → Stop at ratio.

### 5. Install systemd units (user session)

```bash
mkdir -p ~/.config/systemd/user
cp transmission-idle-shutdown.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now transmission-idle-shutdown.timer
```

The timer only runs while `transmission-daemon.service` is active (`BindsTo=`).

### 6. Register the done-script with Transmission

```bash
transmission-remote --torrent-done-script ~/.local/bin/sync-torrent.sh
```

Or in `settings.json`:

```json
"script-torrent-done-enabled": true,
"script-torrent-done-filename": "/home/you/.local/bin/sync-torrent.sh"
```

### 7. Label torrents in Transmission

Set the label before or after adding the torrent:

| Label | Destination |
|---|---|
| `movie`, `movies` | `REMOTE_PATH_MOVIES` |
| `serie`, `series`, `show`, `shows`, `tv` | `REMOTE_PATH_SERIES` |
| anything else / none | `REMOTE_PATH_DEFAULT` |

### 8. Test the sync script manually

```bash
TR_TORRENT_DIR=/path/to/downloads \
TR_TORRENT_NAME=test-file \
TR_TORRENT_HASH=abc123 \
TR_TORRENT_LABELS=movie \
~/.local/bin/sync-torrent.sh

tail -f ~/.local/share/rsync-torrents/sync.log
```

### 9. Test the watch script manually

```bash
~/.local/bin/transmission-watch.sh
tail -f ~/.local/share/rsync-torrents/sync.log
```

## How the cleanup works

`sync-torrent.sh` appends the torrent's info hash to `~/.local/share/rsync-torrents/synced-hashes` after a successful rsync. The watch script checks every Stopped torrent against that list. If the hash is present, it calls `transmission-remote --remove-and-delete` (removes from queue and deletes local files), then removes the hash from the list.

This means: if the rsync fails, the hash is never recorded, the watch script leaves the torrent alone, and you can investigate / re-run the sync manually.

## Transmission environment variables (done-script)

| Variable | Description |
|---|---|
| `TR_TORRENT_DIR` | Directory containing the downloaded files |
| `TR_TORRENT_NAME` | Name of the torrent (file or top-level folder) |
| `TR_TORRENT_HASH` | Torrent info hash |
| `TR_TORRENT_LABELS` | Comma-separated labels (Transmission 3.00+) |
| `TR_TORRENT_ID` | Transmission's internal torrent ID |
