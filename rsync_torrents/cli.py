from __future__ import annotations

import argparse
import fcntl
import logging
import os
import sys
from pathlib import Path

from .config import load_config
from .hashes import append_hash
from .labels import resolve_remote_path
from .log_setup import configure_logging
from .rsync_util import run_rsync
from .watch import run_watch


def _default_config() -> Path:
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return xdg / "rsync-torrents" / "config.toml"


def cmd_sync(args) -> None:
    cfg = load_config(args.config)
    configure_logging(cfg)

    for var in ("TR_TORRENT_NAME", "TR_TORRENT_DIR", "TR_TORRENT_HASH"):
        if not os.environ.get(var):
            logging.error("Missing environment variable: %s", var)
            sys.exit(1)

    name = os.environ["TR_TORRENT_NAME"]
    dir_ = os.environ["TR_TORRENT_DIR"]
    hash_ = os.environ["TR_TORRENT_HASH"]
    labels = os.environ.get("TR_TORRENT_LABELS", "")

    dest = resolve_remote_path(labels, cfg.paths)
    logging.info("START torrent=%r labels=%r dest=%r", name, labels, dest)

    if args.dry_run:
        logging.info("DRY-RUN: would rsync %r to %s and record hash %r", name, dest, hash_)
        return

    run_rsync(
        source=Path(dir_) / name,
        remote_user=cfg.remote.user,
        remote_host=cfg.remote.host,
        remote_dest=dest,
        remote_group=cfg.remote.group,
        ssh_key=cfg.remote.ssh_key,
        retry_attempts=cfg.sync.retry_attempts,
        retry_backoff=cfg.sync.retry_backoff,
        log_file=cfg.log_path(),
        strict_host_key_checking=cfg.remote.strict_host_key_checking,
    )

    append_hash(cfg.synced_hashes_path(), hash_)
    logging.info("DONE torrent=%r hash=%r", name, hash_)


def cmd_watch(args) -> None:
    cfg = load_config(args.config)
    configure_logging(cfg)

    lock_path = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "rsync-torrents-watch.lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logging.info("Another instance is running, skipping")
        return

    try:
        run_watch(cfg, dry_run=args.dry_run)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="rsync-torrents")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to config.toml (default: XDG_CONFIG_HOME/rsync-torrents/config.toml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sync_parser = sub.add_parser("sync", help="Sync a completed torrent (Transmission hook)")
    sync_parser.add_argument("--dry-run", action="store_true", help="Log what would happen without making changes")
    watch_parser = sub.add_parser("watch", help="Watch loop: remove finished, clean orphans, idle-shutdown")
    watch_parser.add_argument("--dry-run", action="store_true", help="Log what would happen without making changes")

    args = parser.parse_args(argv)
    if args.config is None:
        args.config = _default_config()

    if args.command == "sync":
        cmd_sync(args)
    elif args.command == "watch":
        cmd_watch(args)
