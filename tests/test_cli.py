from __future__ import annotations

import textwrap
from unittest.mock import patch

import pytest

from rsync_torrents.cli import _default_config, main


@pytest.fixture
def full_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        textwrap.dedent(
            """\
        [remote]
        user = "u"
        host = "h"
        group = "media"
        ssh_key = ""

        [paths]
        movies = "/mnt/movies"
        series = "/mnt/series"
        default = "/mnt/default"

        [log]
        file = "{log}"

        [state]
        synced_hashes = "{hashes}"
    """
        ).format(
            log=str(tmp_path / "sync.log"),
            hashes=str(tmp_path / "synced-hashes"),
        )
    )
    return cfg


def test_default_config_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert _default_config() == tmp_path / "rsync-torrents" / "config.toml"


def test_default_config_fallback(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    result = _default_config()
    assert result.parts[-2:] == ("rsync-torrents", "config.toml")


def test_cmd_sync_missing_env_exits(full_config, monkeypatch):
    monkeypatch.delenv("TR_TORRENT_NAME", raising=False)
    monkeypatch.delenv("TR_TORRENT_DIR", raising=False)
    monkeypatch.delenv("TR_TORRENT_HASH", raising=False)
    with pytest.raises(SystemExit):
        main(["-c", str(full_config), "sync"])


def test_cmd_sync_runs(full_config, monkeypatch, tmp_path):
    monkeypatch.setenv("TR_TORRENT_NAME", "my.torrent")
    monkeypatch.setenv("TR_TORRENT_DIR", str(tmp_path))
    monkeypatch.setenv("TR_TORRENT_HASH", "abc123")
    monkeypatch.delenv("TR_TORRENT_LABELS", raising=False)

    (tmp_path / "my.torrent").write_text("data")

    with patch("rsync_torrents.cli.run_rsync") as mock_rsync:
        mock_rsync.return_value = None
        main(["-c", str(full_config), "sync"])

    mock_rsync.assert_called_once()
    hashes = (tmp_path / "synced-hashes").read_text()
    assert "abc123" in hashes


def test_cmd_watch_runs(full_config, mocker):
    mock_run_watch = mocker.patch("rsync_torrents.cli.run_watch")
    main(["-c", str(full_config), "watch"])
    mock_run_watch.assert_called_once()


def test_cmd_watch_skips_when_locked(full_config, mocker, tmp_path, monkeypatch):
    import fcntl

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    lock_path = tmp_path / "rsync-torrents-watch.lock"
    lock_fd = open(lock_path, "w")
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    mock_run_watch = mocker.patch("rsync_torrents.cli.run_watch")
    try:
        main(["-c", str(full_config), "watch"])
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

    mock_run_watch.assert_not_called()
