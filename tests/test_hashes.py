from rsync_torrents.hashes import load_hashes, save_hashes, reconcile_hashes


def test_load_empty(tmp_hashes):
    assert load_hashes(tmp_hashes) == set()


def test_load_nonexistent(tmp_path):
    assert load_hashes(tmp_path / "missing") == set()


def test_roundtrip(tmp_hashes):
    hashes = {"aabbcc", "ddeeff"}
    save_hashes(tmp_hashes, hashes)
    assert load_hashes(tmp_hashes) == hashes


def test_save_creates_parent(tmp_path):
    p = tmp_path / "deep" / "hashes"
    save_hashes(p, {"abc"})
    assert p.exists()


def test_reconcile_removes_stale(tmp_hashes):
    save_hashes(tmp_hashes, {"aabbcc", "ddeeff", "112233"})
    result = reconcile_hashes(tmp_hashes, current={"aabbcc", "112233"})
    assert result == {"aabbcc", "112233"}
    assert load_hashes(tmp_hashes) == {"aabbcc", "112233"}


def test_reconcile_skips_on_empty_current(tmp_hashes):
    save_hashes(tmp_hashes, {"aabbcc"})
    result = reconcile_hashes(tmp_hashes, current=set())
    assert result == {"aabbcc"}
    assert load_hashes(tmp_hashes) == {"aabbcc"}


def test_reconcile_readd_safety(tmp_hashes):
    save_hashes(tmp_hashes, {"aabbcc"})
    result = reconcile_hashes(tmp_hashes, current={"aabbcc"})
    assert "aabbcc" in result
