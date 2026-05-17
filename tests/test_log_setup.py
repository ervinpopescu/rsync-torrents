from __future__ import annotations

import logging
import logging.handlers

import pytest

from rsync_torrents.log_setup import configure_logging


@pytest.fixture(autouse=True)
def reset_root_logger():
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    old_level = root.level
    yield
    root.handlers = old_handlers
    root.level = old_level


def test_configure_logging_creates_file(tmp_config):
    from rsync_torrents.config import load_config

    cfg = load_config(tmp_config)
    configure_logging(cfg)

    assert cfg.log_path().exists()
    assert any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in logging.getLogger().handlers
    )


def test_configure_logging_respects_max_bytes(tmp_config):
    from rsync_torrents.config import load_config

    cfg = load_config(tmp_config)
    configure_logging(cfg)

    handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert handlers
    assert handlers[-1].maxBytes == cfg.log.max_bytes
