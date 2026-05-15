# rsync-torrents

Full workflow:

1. **Download** — Transmission downloads the torrent to `~/internet/torrents`
2. **Sync** — on completion, `rsync-torrents sync` rsyncs it to the server (routed by label: movie/series) and records the hash
3. **Seed** — Transmission continues seeding until ratio 5.0 is reached, then marks the torrent Stopped
4. **Cleanup** — `rsync-torrents watch` (timer, every 5 min) detects Stopped+synced torrents, deletes local files, and removes them from the queue
5. **Shutdown** — once no torrents are active for 30 minutes, the daemon stops

## Files

| File | Purpose |
|---|---|
| `rsync_torrents/` | Python package |
| `transmission-idle-shutdown.service` | Systemd oneshot service running `rsync-torrents watch` |
| `transmission-idle-shutdown.timer` | Systemd timer (every 5 min, bound to `transmission-daemon.service`) |
| `transmission-settings.json` | Transmission settings to apply (reference/diff) |
| `config.example.toml` | Annotated config template — copy to `~/.config/rsync-torrents/config.toml` |

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

### 1. Install the package

```bash
pip install --user .
# or with uv:
uv tool install .
```

### 2. Create download directories

```bash
mkdir -p ~/internet/torrents/movies ~/internet/torrents/series
```

### 3. Create config

```bash
mkdir -p ~/.config/rsync-torrents
cp config.example.toml ~/.config/rsync-torrents/config.toml
$EDITOR ~/.config/rsync-torrents/config.toml
```

Fill in at minimum:

| Key | Description |
|---|---|
| `remote.user` | SSH user on the server |
| `remote.host` | Server hostname or IP |
| `remote.group` | Group that owns files on the server (e.g. `media`) |
| `paths.movies` | Destination path for torrents labelled `movie` |
| `paths.series` | Destination path for torrents labelled `series` |
| `paths.default` | Fallback path when no recognised label is set |

### 4. Ensure passwordless SSH to the server

```bash
ssh-copy-id user@yourserver
# or set remote.ssh_key in config.toml to point at an identity file
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

```bash
sudo cp transmission-idle-shutdown.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now transmission-idle-shutdown.timer
```

If `rsync-torrents` is installed to `~/.local/bin` (pip `--user` or uv tool), ensure the service can find it — the unit already sets `Environment=PATH=/home/ervin/.local/bin:/usr/bin:/bin`. Adjust the username if needed.

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
| `script-torrent-done-filename` | path to a wrapper that calls `rsync-torrents sync` |

Because Transmission's done-script field doesn't support arguments, create a one-line wrapper:

```bash
cat > ~/.local/bin/torrent-sync-hook <<'EOF'
#!/bin/sh
exec rsync-torrents sync
EOF
chmod +x ~/.local/bin/torrent-sync-hook
```

Then set `script-torrent-done-filename` to `~/.local/bin/torrent-sync-hook`.

### 8. Enable transmission-daemon

```bash
sudo systemctl enable --now transmission-daemon.service
```

### 9. Label torrents in Transmission

Set the label before or after adding a torrent:

| Label | Remote destination |
|---|---|
| `movie`, `movies` | `paths.movies` |
| `serie`, `series`, `show`, `shows`, `tv` | `paths.series` |
| anything else / none | `paths.default` |

## Testing

**Test sync manually:**

```bash
TR_TORRENT_DIR=~/internet/torrents \
TR_TORRENT_NAME=test-file \
TR_TORRENT_HASH=abc123 \
TR_TORRENT_LABELS=movie \
rsync-torrents sync

tail -f ~/.local/share/rsync-torrents/sync.log
```

Verify the file arrived on the server with `media` group ownership.

**Test watch manually:**

```bash
rsync-torrents watch
tail -f ~/.local/share/rsync-torrents/sync.log
```

Or via systemd:

```bash
sudo systemctl start transmission-idle-shutdown.service
journalctl -u transmission-idle-shutdown.service
```

**Run the test suite:**

```bash
uv run pytest -v
```

## How the cleanup works

`rsync-torrents sync` appends the torrent's info hash to `~/.local/share/rsync-torrents/synced-hashes` after a successful rsync. The watch command checks every Stopped torrent against that list via Transmission's JSON-RPC API. If the hash is present, it removes the torrent and its data, then reconciles the hash file against the current torrent list to prune any stale entries.

If rsync fails (after all retries), the hash is never recorded — the watch command leaves the torrent alone so you can investigate and re-run manually.

## Transmission environment variables (done-script)

| Variable | Description |
|---|---|
| `TR_TORRENT_DIR` | Directory containing the downloaded files |
| `TR_TORRENT_NAME` | Name of the torrent (file or top-level folder) |
| `TR_TORRENT_HASH` | Torrent info hash |
| `TR_TORRENT_LABELS` | Comma-separated labels (Transmission 3.00+) |
| `TR_TORRENT_ID` | Transmission's internal torrent ID |
