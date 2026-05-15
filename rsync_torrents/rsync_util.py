from __future__ import annotations
import logging
import shlex
import subprocess
import time
from pathlib import Path


def build_ssh_command(ssh_key: str) -> str:
    opts = ["-o", "StrictHostKeyChecking=accept-new"]
    if ssh_key:
        opts += ["-i", ssh_key]
    return "ssh " + " ".join(shlex.quote(o) for o in opts)


def run_rsync(
    *,
    source: str | Path,
    remote_user: str,
    remote_host: str,
    remote_dest: str,
    remote_group: str,
    ssh_key: str,
    retry_attempts: int = 5,
    retry_backoff: int = 30,
    log_file: Path | None = None,
) -> None:
    ssh_cmd = build_ssh_command(ssh_key)
    cmd = [
        "rsync", "-avz", "--progress", "--partial",
        f"--chown=:{remote_group}",
        "--chmod=Dg+rwxs,Fg+rw",
        "-e", ssh_cmd,
        str(source),
        f"{remote_user}@{remote_host}:{remote_dest}/",
    ]
    stdout = None
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        stdout = open(log_file, "a")
    try:
        for attempt in range(1, retry_attempts + 1):
            result = subprocess.run(cmd, stdout=stdout, stderr=subprocess.STDOUT)
            if result.returncode == 0:
                return
            logging.warning("rsync attempt %d/%d failed (rc=%d)", attempt, retry_attempts, result.returncode)
            if attempt < retry_attempts:
                time.sleep(attempt * retry_backoff)
    finally:
        if stdout:
            stdout.close()
    raise RuntimeError(f"rsync failed after {retry_attempts} attempts")
