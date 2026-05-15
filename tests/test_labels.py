import pytest
from rsync_torrents.labels import resolve_remote_path


@pytest.mark.parametrize("labels,expected", [
    ("movies",         "/mnt/movies"),
    ("Movies",         "/mnt/movies"),
    ("movie",          "/mnt/movies"),
    ("MOVIE",          "/mnt/movies"),
    ("series",         "/mnt/series"),
    ("Serie",          "/mnt/series"),
    ("show",           "/mnt/series"),
    ("tv",             "/mnt/series"),
    ("shows",          "/mnt/series"),
    ("",               "/mnt/default"),
    ("unknown",        "/mnt/default"),
    ("movie,series",   "/mnt/movies"),
    ("hd, movies",     "/mnt/movies"),
])
def test_resolve(labels, expected):
    paths = type("P", (), {
        "movies": "/mnt/movies",
        "series": "/mnt/series",
        "default": "/mnt/default",
    })()
    assert resolve_remote_path(labels, paths) == expected
