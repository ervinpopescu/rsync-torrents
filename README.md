# rsync-torrents

Full workflow:

1. **Download** — Transmission downloads the torrent to `~/internet/torrents`
2. **Sync** — on completion, `sync-torrent.sh` rsyncs it to the server (routed by label: movie/series) and records the hash
3. **Seed** — Transmission continues seeding until ratio 5.0 is reached, then marks the torrent Stopped
4. **Cleanup** — `transmission-watch.sh` (timer, every 5 min) detects Stopped+synced torrents, deletes local files, and removes them from the queue
5. **Shutdown** — once no torrents are active for 30 minutes, the daemon stops

## Files

| File | Purpose |
|---|---|
| `sync-torrent.sh` | Transmission done-script: rsync + record hash |
| `transmission-watch.sh` | Timer script: cleanup finished torrents + idle shutdown |
| `transmission-idle-shutdown.service` | Systemd oneshot service running the watch script |
| `transmission-idle-shutdown.timer` | Systemd timer (every 5 min, bound to `transmission-daemon.service`) |
| `transmission-settings.json` | Transmission settings to apply (reference/diff) |
| `config.example` | Template config — copy to `~/.config/rsync-torrents/config` |

## Remote server setup

Run once on the server as root:

```bash
groupadd -f media
usermod -aG media jellyfin
usermod -aG media transmission

mkdir -p /path/to/movies /path/to/series
chown root:media /path/to/movies /path/to/series
chmod 2775 /path/to/movies /path/to/series
```

`2775` = setgid so new files/dirs inside inherit the `media` group automatically.

## Local setup

### 1. Create download directories

```bash
mkdir -p ~/internet/torrents/movies ~/internet/torrents/series
```

### 2. Create config

```bash
mkdir -p ~/.config/rsync-torrents
cp config.example ~/.config/rsync-torrents/config
$EDITOR ~/.config/rsync-torrents/config
```

Fill in `REMOTE_USER`, `REMOTE_HOST`, and the three `REMOTE_PATH_*` variables.

### 3. Ensure passwordless SSH to the server

```bash
ssh-copy-id user@yourserver
```

### 4. Install scripts

```bash
install -m 755 sync-torrent.sh ~/.local/bin/sync-torrent.sh
install -m 755 transmission-watch.sh ~/.local/bin/transmission-watch.sh
```

### 5. Run transmission-daemon as your user

Create a drop-in to override the default `User=transmission`:

```bash
sudo mkdir -p /etc/systemd/system/transmission-daemon.service.d
sudo tee /etc/systemd/system/transmission-daemon.service.d/username.conf <<EOF
[Service]
User=$USER
EOF
sudo systemctl daemon-reload
```

### 6. Install and enable the idle-shutdown units

These must be system units so they can bind to and stop `transmission-daemon.service`:

```bash
sudo cp transmission-idle-shutdown.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now transmission-idle-shutdown.timer
```

### 7. Apply Transmission settings

Stop the daemon, merge the settings, then restart:

```bash
sudo systemctl stop transmission-daemon.service
# Manually merge transmission-settings.json into ~/.config/transmission/settings.json
sudo systemctl start transmission-daemon.service
```

Key settings applied:

| Setting | Value |
|---|---|
| `download-dir` | `~/internet/torrents` |
| `ratio-limit` | 5.0 |
| `ratio-limit-enabled` | true |
| `script-torrent-done-enabled` | true |
| `script-torrent-done-filename` | `~/.local/bin/sync-torrent.sh` |
| `remote-session-enabled` | false |

### 8. Enable transmission-daemon

```bash
sudo systemctl enable --now transmission-daemon.service
```

### 9. Label torrents in Transmission

Set the label before or after adding a torrent:

| Label | Remote destination |
|---|---|
| `movie`, `movies` | `REMOTE_PATH_MOVIES` |
| `serie`, `series`, `show`, `shows`, `tv` | `REMOTE_PATH_SERIES` |
| anything else / none | `REMOTE_PATH_DEFAULT` |

## Testing

**Test the sync script manually:**

```bash
TR_TORRENT_DIR=~/internet/torrents \
TR_TORRENT_NAME=test-file \
TR_TORRENT_HASH=abc123 \
TR_TORRENT_LABELS=movie \
~/.local/bin/sync-torrent.sh

tail -f ~/.local/share/rsync-torrents/sync.log
```

Verify the file arrived on the server with `media` group ownership.

**Test the watch script manually:**

```bash
sudo systemctl start transmission-idle-shutdown.service
journalctl -u transmission-idle-shutdown.service
```

## How the cleanup works

`sync-torrent.sh` appends the torrent's info hash to `~/.local/share/rsync-torrents/synced-hashes` after a successful rsync. The watch script checks every Stopped torrent against that list. If the hash is present, it calls `transmission-remote --remove-and-delete`, then removes the hash from the list.

If rsync fails, the hash is never recorded — the watch script leaves the torrent alone so you can investigate and re-run manually.

## Transmission environment variables (done-script)

| Variable | Description |
|---|---|
| `TR_TORRENT_DIR` | Directory containing the downloaded files |
| `TR_TORRENT_NAME` | Name of the torrent (file or top-level folder) |
| `TR_TORRENT_HASH` | Torrent info hash |
| `TR_TORRENT_LABELS` | Comma-separated labels (Transmission 3.00+) |
| `TR_TORRENT_ID` | Transmission's internal torrent ID |
