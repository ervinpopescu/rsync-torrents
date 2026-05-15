import textwrap
from pathlib import Path
import pytest


@pytest.fixture
def tmp_config(tmp_path):
    """Write a minimal valid TOML config and return its path."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(textwrap.dedent("""\
        [remote]
        user = "testuser"
        host = "testhost"
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
    """).format(
        log=str(tmp_path / "sync.log"),
        hashes=str(tmp_path / "synced-hashes"),
    ))
    return cfg


@pytest.fixture
def tmp_hashes(tmp_path):
    """Return path to a fresh synced-hashes file."""
    return tmp_path / "synced-hashes"


def make_torrent(mocker, *, hash_string, name, status, download_dir, id_=1):
    t = mocker.MagicMock()
    t.hash_string = hash_string
    t.name = name
    t.status = status
    t.download_dir = download_dir
    t.id = id_
    return t


@pytest.fixture
def mock_client(mocker):
    """Return a MagicMock transmission_rpc.Client."""
    return mocker.patch("transmission_rpc.Client")
