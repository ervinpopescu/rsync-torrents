from __future__ import annotations
import logging
import shutil
import subprocess
import time
from pathlib import Path

import transmission_rpc

from .config import Config
from .hashes import load_hashes, reconcile_hashes

_ACTIVE_STATUSES = {
    "downloading", "seeding", "seed_wait", "download_wait", "check", "check_wait",
    "download", "seed", "check wait", "download wait", "seed wait",
}


def run_watch(cfg: Config) -> None:
    try:
        client = transmission_rpc.Client(
            host=cfg.transmission.host,
            port=cfg.transmission.port,
            username=cfg.transmission.username or None,
            password=cfg.transmission.password or None,
        )
    except Exception as exc:
        logging.error("Cannot connect to Transmission: %s", exc)
        return

    torrents = client.get_torrents()
    hashes_path = cfg.synced_hashes_path()
    synced = load_hashes(hashes_path)
    current_hashes = {t.hash_string for t in torrents}

    # ── Step 1: remove stopped torrents whose files are on the server ─────────
    removed = 0
    for torrent in torrents:
        if str(torrent.status) != "stopped":
            continue
        if torrent.hash_string not in synced:
            continue
        logging.info("Removing %s (hash=%s)", torrent.name, torrent.hash_string)
        try:
            client.remove_torrent(torrent.id, delete_data=True)
            synced.discard(torrent.hash_string)
            current_hashes.discard(torrent.hash_string)
            removed += 1
        except Exception as exc:
            logging.error("Failed to remove torrent %s: %s", torrent.id, exc)

    if removed:
        logging.info("Removed %d finished torrent(s)", removed)

    reconcile_hashes(hashes_path, current=current_hashes)

    # ── Step 2: remove orphaned files from torrent location dirs ──────────────
    known_paths = {Path(t.download_dir) / t.name for t in torrents}
    scan_dirs = {Path(t.download_dir) for t in torrents}
    orphans = 0
    for dir_ in scan_dirs:
        if not dir_.is_dir():
            continue
        for item in dir_.iterdir():
            if item in known_paths:
                continue
            logging.info("Removing orphan: %s", item)
            try:
                shutil.rmtree(item) if item.is_dir() else item.unlink()
                orphans += 1
            except OSError as exc:
                logging.warning("Failed to remove %s: %s", item, exc)

    if orphans:
        logging.info("Removed %d orphaned item(s)", orphans)

    # ── Step 3: idle-shutdown check ───────────────────────────────────────────
    active = sum(1 for t in torrents if str(t.status) in _ACTIVE_STATUSES)
    state_file = cfg.state_file_path()
    now = int(time.time())

    if active > 0:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(str(now))
        logging.info("Active torrents: %d, idle clock reset", active)
        return

    if not state_file.exists():
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(str(now))
        logging.info("No active torrents, idle clock started")
        return

    last_active = int(state_file.read_text().strip())
    idle_seconds = now - last_active
    logging.info("Idle for %ds (threshold %ds)", idle_seconds, cfg.transmission.idle_threshold)

    if idle_seconds >= cfg.transmission.idle_threshold:
        logging.info("Stopping transmission-daemon")
        result = subprocess.run(["systemctl", "stop", "transmission-daemon.service"])
        if result.returncode == 0:
            state_file.unlink(missing_ok=True)
        else:
            logging.error("Failed to stop transmission-daemon (rc=%d)", result.returncode)
