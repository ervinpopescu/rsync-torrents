from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import Config


def configure_logging(cfg: Config) -> None:
    log_path = cfg.log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=cfg.log.max_bytes,
        backupCount=cfg.log.backup_count,
    )
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
