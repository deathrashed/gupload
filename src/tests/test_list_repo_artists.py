import pytest

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "list-repo-artists.py"
SPEC = importlib.util.spec_from_file_location("list_repo_artists", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def test_contents_url_encodes_each_path_segment():
    url = helper._contents_url(
        {"owner": "owner", "repo": "repo", "branch": "branch with space"},
        "prefix with space/uploads/audio/Artist Name",
    )
    assert url == (
        "https://api.github.com/repos/owner/repo/contents/"
        "prefix%20with%20space/uploads/audio/Artist%20Name?ref=branch%20with%20space"
    )


def test_unorganized_artist_files_filter_cover_routing(monkeypatch):
    monkeypatch.setattr(helper, "load_config", lambda: {
        "owner": "owner", "repo": "repo", "organize_by_artist": False,
        "repo_path_prefix": "media",
    })
    monkeypatch.setattr(helper, "get_token", lambda cfg: "token")
    calls = []

    def request(method, url, token):
        calls.append((method, url, token))
        return [
            {"type": "file", "name": "Artist Name - Album.jpg", "path": "uploads/images/covers/Artist Name - Album.jpg"},
            {"type": "file", "name": "Other - Album.jpg", "path": "uploads/images/covers/Other - Album.jpg"},
            {"type": "dir", "name": "nested"},
        ]

    monkeypatch.setattr(helper, "api_request", request)
    result = helper.list_artist_files("Artist Name")
    assert [item["name"] for item in result] == ["Artist Name - Album.jpg"]
    assert "/contents/media/uploads/images/covers?ref=main" in calls[0][1]


def test_missing_remote_result_is_not_silently_empty(monkeypatch):
    monkeypatch.setattr(helper, "get_token", lambda cfg: "offline-token")
    monkeypatch.setattr(helper, "api_request", lambda *args: None)
    with pytest.raises(RuntimeError, match="returned no contents"):
        helper._contents({"owner": "owner", "repo": "repo"}, "uploads/audio")
