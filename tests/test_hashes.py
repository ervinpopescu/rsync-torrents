import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from rsync_torrents.hashes import load_hashes, reconcile_hashes, save_hashes


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


_hash_text = st.text(
    alphabet="0123456789abcdef",
    min_size=1,
    max_size=64,
)


@given(st.frozensets(_hash_text, max_size=50))
def test_save_load_roundtrip_hypothesis(hashes):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "hashes"
        save_hashes(path, set(hashes))
        assert load_hashes(path) == set(hashes)


@given(st.frozensets(_hash_text, max_size=20), st.frozensets(_hash_text, max_size=20))
def test_reconcile_is_subset_hypothesis(stored, current):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "hashes"
        save_hashes(path, set(stored))
        if current:
            result = reconcile_hashes(path, current=set(current))
            assert result == set(stored) & set(current)
