import pytest

from rsync_torrents.rsync_util import build_ssh_command, run_rsync


def test_ssh_command_no_key():
    cmd = build_ssh_command("")
    assert cmd.startswith("ssh ")
    assert "StrictHostKeyChecking=accept-new" in cmd
    assert "-i" not in cmd


def test_ssh_command_with_key():
    cmd = build_ssh_command("/home/user/My Keys/id rsa")
    assert "-i" in cmd
    assert "'/home/user/My Keys/id rsa'" in cmd


def test_ssh_command_strict_host_key_checking_enabled():
    cmd = build_ssh_command("", strict_host_key_checking=True)
    assert "StrictHostKeyChecking=yes" in cmd


def test_ssh_command_strict_host_key_checking_disabled():
    cmd = build_ssh_command("", strict_host_key_checking=False)
    assert "StrictHostKeyChecking=accept-new" in cmd


def test_run_rsync_success(mocker):
    mock_run = mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))
    run_rsync(
        source="/src/file",
        remote_user="user",
        remote_host="host",
        remote_dest="/dst",
        remote_group="media",
        ssh_key="",
    )
    assert mock_run.call_count == 1


def test_run_rsync_retries_on_failure(mocker):
    mock_run = mocker.patch(
        "subprocess.run",
        side_effect=[
            mocker.Mock(returncode=1),
            mocker.Mock(returncode=1),
            mocker.Mock(returncode=0),
        ],
    )
    mock_sleep = mocker.patch("time.sleep")
    run_rsync(
        source="/src/file",
        remote_user="user",
        remote_host="host",
        remote_dest="/dst",
        remote_group="media",
        ssh_key="",
        retry_attempts=5,
        retry_backoff=1,
    )
    assert mock_run.call_count == 3
    assert mock_sleep.call_count == 2


def test_run_rsync_raises_after_exhausting_retries(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1))
    mocker.patch("time.sleep")
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        run_rsync(
            source="/src/file",
            remote_user="u",
            remote_host="h",
            remote_dest="/d",
            remote_group="media",
            ssh_key="",
            retry_attempts=3,
            retry_backoff=1,
        )


def test_run_rsync_uses_partial_flag(mocker):
    mock_run = mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))
    run_rsync(
        source="/src",
        remote_user="u",
        remote_host="h",
        remote_dest="/d",
        remote_group="media",
        ssh_key="",
    )
    cmd = mock_run.call_args[0][0]
    assert "--partial" in cmd


def test_run_rsync_dry_run_appends_flag(mocker):
    mock_run = mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))
    run_rsync(
        source="/src",
        remote_user="u",
        remote_host="h",
        remote_dest="/d",
        remote_group="media",
        ssh_key="",
        dry_run=True,
    )
    cmd = mock_run.call_args[0][0]
    assert "--dry-run" in cmd


def test_run_rsync_writes_to_log_file(mocker, tmp_path):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))
    log_file = tmp_path / "subdir" / "rsync.log"
    run_rsync(
        source="/src",
        remote_user="u",
        remote_host="h",
        remote_dest="/d",
        remote_group="media",
        ssh_key="",
        log_file=log_file,
    )
    assert log_file.parent.exists()
