from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RemoteConfig:
    user: str
    host: str
    group: str = "media"
    ssh_key: str = ""


@dataclass
class PathsConfig:
    movies: str
    series: str
    default: str


@dataclass
class LogConfig:
    file: str
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 3


@dataclass
class StateConfig:
    synced_hashes: str


@dataclass
class TransmissionConfig:
    host: str = "localhost"
    port: int = 9091
    username: str = ""
    password: str = ""
    idle_threshold: int = 1800
    state_file: str = "~/.local/share/rsync-torrents/last-active"


@dataclass
class SyncConfig:
    retry_attempts: int = 5
    retry_backoff: int = 30


@dataclass
class Config:
    remote: RemoteConfig
    paths: PathsConfig
    log: LogConfig
    state: StateConfig
    transmission: TransmissionConfig = field(default_factory=TransmissionConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)

    def log_path(self) -> Path:
        return Path(self.log.file).expanduser()

    def synced_hashes_path(self) -> Path:
        return Path(self.state.synced_hashes).expanduser()

    def state_file_path(self) -> Path:
        return Path(self.transmission.state_file).expanduser()


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(
        remote=RemoteConfig(**data["remote"]),
        paths=PathsConfig(**data["paths"]),
        log=LogConfig(**data["log"]),
        state=StateConfig(**data["state"]),
        transmission=TransmissionConfig(**data.get("transmission", {})),
        sync=SyncConfig(**data.get("sync", {})),
    )
