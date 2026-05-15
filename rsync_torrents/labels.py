from __future__ import annotations

_MOVIE_LABELS = {"movie", "movies"}
_SERIES_LABELS = {"serie", "series", "show", "shows", "tv"}


def resolve_remote_path(labels: str, paths) -> str:
    """Return the remote destination path based on comma-separated torrent labels."""
    normalised = labels.lower().replace(" ", "")
    for label in normalised.split(","):
        if label in _MOVIE_LABELS:
            return paths.movies
        if label in _SERIES_LABELS:
            return paths.series
    return paths.default
