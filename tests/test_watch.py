import time

from rsync_torrents.hashes import load_hashes, save_hashes
from rsync_torrents.watch import run_watch


def _cfg(tmp_config_path, mocker):
    from rsync_torrents.config import load_config

    return load_config(tmp_config_path)


def _torrent(mocker, *, hash_string, name="Torrent", status="seed", download_dir="/dl", id_=1):
    t = mocker.MagicMock()
    t.hash_string = hash_string
    t.name = name
    t.status = status
    t.download_dir = str(download_dir)
    t.id = id_
    return t


# ── step 1: removal ───────────────────────────────────────────────────────────


def test_removes_stopped_synced_torrent(tmp_config, tmp_hashes, mocker):
    save_hashes(tmp_hashes, {"abc123"})
    torrent = _torrent(mocker, hash_string="abc123", status="stopped")
    client = mocker.MagicMock()
    client.get_torrents.return_value = [torrent]
    mocker.patch("transmission_rpc.Client", return_value=client)

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    run_watch(cfg)

    client.remove_torrent.assert_called_once_with(torrent.id, delete_data=True)


def test_does_not_remove_seeding_torrent(tmp_config, tmp_hashes, mocker):
    save_hashes(tmp_hashes, {"abc123"})
    torrent = _torrent(mocker, hash_string="abc123", status="seed")
    client = mocker.MagicMock()
    client.get_torrents.return_value = [torrent]
    mocker.patch("transmission_rpc.Client", return_value=client)

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    run_watch(cfg)

    client.remove_torrent.assert_not_called()


def test_does_not_remove_unsynced_stopped_torrent(tmp_config, tmp_hashes, mocker):
    save_hashes(tmp_hashes, set())
    torrent = _torrent(mocker, hash_string="abc123", status="stopped")
    client = mocker.MagicMock()
    client.get_torrents.return_value = [torrent]
    mocker.patch("transmission_rpc.Client", return_value=client)

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    run_watch(cfg)

    client.remove_torrent.assert_not_called()


def test_reconciles_stale_hash_after_removal(tmp_config, tmp_hashes, mocker):
    save_hashes(tmp_hashes, {"abc123", "old_hash"})
    torrent = _torrent(mocker, hash_string="abc123", status="seed")
    client = mocker.MagicMock()
    client.get_torrents.return_value = [torrent]
    mocker.patch("transmission_rpc.Client", return_value=client)

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    run_watch(cfg)

    remaining = load_hashes(tmp_hashes)
    assert "old_hash" not in remaining


# ── step 2: orphan cleanup ────────────────────────────────────────────────────


def test_removes_orphan_file(tmp_config, tmp_hashes, tmp_path, mocker):
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    known = dl_dir / "KnownTorrent"
    known.mkdir()
    orphan = dl_dir / "OrphanFile.mkv"
    orphan.touch()

    torrent = _torrent(
        mocker, hash_string="abc", name="KnownTorrent", status="seed", download_dir=dl_dir
    )
    client = mocker.MagicMock()
    client.get_torrents.return_value = [torrent]
    mocker.patch("transmission_rpc.Client", return_value=client)

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    run_watch(cfg)

    assert not orphan.exists()
    assert known.exists()


def test_keeps_known_torrent_dir(tmp_config, tmp_hashes, tmp_path, mocker):
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    known = dl_dir / "KnownTorrent"
    known.mkdir()

    torrent = _torrent(
        mocker, hash_string="abc", name="KnownTorrent", status="seed", download_dir=dl_dir
    )
    client = mocker.MagicMock()
    client.get_torrents.return_value = [torrent]
    mocker.patch("transmission_rpc.Client", return_value=client)

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    run_watch(cfg)

    assert known.exists()


# ── step 3: idle shutdown ─────────────────────────────────────────────────────


def test_resets_idle_clock_when_active(tmp_config, tmp_hashes, tmp_path, mocker):
    torrent = _torrent(mocker, hash_string="abc", status="seed")
    client = mocker.MagicMock()
    client.get_torrents.return_value = [torrent]
    mocker.patch("transmission_rpc.Client", return_value=client)
    mock_run = mocker.patch("subprocess.run")

    state_file = tmp_path / "last-active"
    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    cfg.transmission.state_file = str(state_file)
    run_watch(cfg)

    assert state_file.exists()
    mock_run.assert_not_called()


def test_stops_daemon_after_idle_threshold(tmp_config, tmp_hashes, tmp_path, mocker):
    client = mocker.MagicMock()
    client.get_torrents.return_value = []
    mocker.patch("transmission_rpc.Client", return_value=client)
    mock_run = mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))

    state_file = tmp_path / "last-active"
    past = int(time.time()) - 9999
    state_file.write_text(str(past))

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    cfg.transmission.state_file = str(state_file)
    cfg.transmission.idle_threshold = 1800
    run_watch(cfg)

    mock_run.assert_called_once()
    assert "transmission-daemon.service" in mock_run.call_args[0][0]


def test_no_shutdown_before_threshold(tmp_config, tmp_hashes, tmp_path, mocker):
    client = mocker.MagicMock()
    client.get_torrents.return_value = []
    mocker.patch("transmission_rpc.Client", return_value=client)
    mock_run = mocker.patch("subprocess.run")

    state_file = tmp_path / "last-active"
    recent = int(time.time()) - 60
    state_file.write_text(str(recent))

    cfg = _cfg(tmp_config, mocker)
    cfg.state.synced_hashes = str(tmp_hashes)
    cfg.transmission.state_file = str(state_file)
    cfg.transmission.idle_threshold = 1800
    run_watch(cfg)

    mock_run.assert_not_called()
