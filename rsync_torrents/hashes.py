from __future__ import annotations
from pathlib import Path
from filelock import FileLock


def _lock_path(path: Path) -> str:
    return str(path) + ".lock"


def load_hashes(path: Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def save_hashes(path: Path, hashes: set[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with FileLock(_lock_path(path)):
        tmp.write_text("\n".join(sorted(hashes)) + ("\n" if hashes else ""))
        tmp.replace(path)


def append_hash(path: Path, hash_string: str) -> None:
    """Atomically append one hash. Used by sync after a successful rsync."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(_lock_path(path)):
        with open(path, "a") as f:
            f.write(hash_string + "\n")


def reconcile_hashes(path: Path, current: set[str]) -> set[str]:
    """Remove hashes not in *current* from disk. Guard: no-op if current is empty."""
    if not current:
        return load_hashes(path)
    kept = load_hashes(path) & current
    save_hashes(path, kept)
    return kept
