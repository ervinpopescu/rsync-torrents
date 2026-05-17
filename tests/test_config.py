import pytest

from rsync_torrents.config import Config, load_config


def test_load_valid_config(tmp_config):
    cfg = load_config(tmp_config)
    assert isinstance(cfg, Config)
    assert cfg.remote.user == "testuser"
    assert cfg.remote.host == "testhost"
    assert cfg.remote.group == "media"
    assert cfg.paths.movies == "/mnt/movies"
    assert cfg.transmission.host == "localhost"
    assert cfg.transmission.idle_threshold == 1800
    assert cfg.sync.retry_attempts == 5


def test_missing_config_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="config.toml"):
        load_config(tmp_path / "config.toml")


def test_missing_required_section(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[remote]\nuser='x'\nhost='y'\ngroup='g'\nssh_key=''\n")
    with pytest.raises(KeyError):
        load_config(cfg)


def test_path_expansion(tmp_config, tmp_path):
    cfg = load_config(tmp_config)
    assert cfg.log_path().is_absolute()
    assert cfg.synced_hashes_path().is_absolute()
