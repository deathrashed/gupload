"""Run real planning/execution against a stateful offline GitHub boundary."""
from __future__ import annotations

import base64
import copy
import hashlib
from pathlib import Path
import urllib.parse

import pytest

import gupload


def blob_sha(content):
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


class OfflineRepository:
    def __init__(self):
        self.files = {}
        self.fail_paths = set()
        self.written_paths = []
        self.asset = None
        self.deleted_assets = []

    def request(self, method, url, token, data=None, headers=None):
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
        if method == "GET" and path == "/user":
            return {"login": "fixture-account"}
        if method == "GET" and path == "/repos/owner/repo":
            return {"private": False}
        prefix = "/repos/owner/repo/contents/"
        if path.startswith(prefix):
            remote = path[len(prefix):]
            current = self.files.get(remote)
            if method == "GET":
                if current is not None:
                    return {"path": remote, "sha": blob_sha(current),
                            "download_url": "https://example.invalid/" + urllib.parse.quote(remote)}
                matching = [
                    {"name": p[len(remote) + 1:], "path": p, "type": "file", "sha": blob_sha(c),
                     "download_url": "https://example.invalid/" + urllib.parse.quote(p)}
                    for p, c in self.files.items() if p.startswith(f"{remote}/")
                ]
                if matching:
                    return matching
                raise RuntimeError("GET -> 404")
            if method == "PUT":
                if remote in self.fail_paths:
                    raise RuntimeError("PUT -> 503 temporary offline fixture failure")
                if current is not None and data.get("sha") != blob_sha(current):
                    raise RuntimeError("PUT -> 422 update requires existing SHA")
                if current is None and "sha" in data:
                    raise RuntimeError("PUT -> 409 stale existing identity")
                self.files[remote] = base64.b64decode(data["content"])
                self.written_paths.append(remote)
                return {"content": {"path": remote, "sha": blob_sha(self.files[remote]),
                                    "download_url": "https://example.invalid/" + urllib.parse.quote(remote)}}
        if path == "/repos/owner/repo/releases/assets/91" and self.asset is not None:
            if method == "PATCH":
                self.asset["name"] = data["name"]
                return copy.deepcopy(self.asset)
            if method == "DELETE":
                self.deleted_assets.append(self.asset["id"])
                self.asset = None
                return None
        raise AssertionError(f"Unexpected offline request {method} {path}")


@pytest.fixture
def repository(monkeypatch):
    remote = OfflineRepository()
    monkeypatch.setattr(gupload, "api_request", remote.request)
    monkeypatch.setattr(gupload, "get_token", lambda cfg: "offline-fixture-token")
    return remote


@pytest.fixture
def cfg():
    return {
        "owner": "owner", "repo": "repo", "branch": "main",
        "allowed_destinations": ["owner/repo"],
        "dedup_strategy": "none", "use_path_for_generic_names": False,
        "use_image_subfolders": True, "contents_max_mb": 95,
        "release_append_timestamp": False,
    }


def test_identical_final_destination_reuses_link_without_creating_commit(repository, cfg, tmp_path):
    source = tmp_path / "cover.jpg"
    source.write_bytes(b"same content")
    target = "uploads/images/covers/cover.jpg"
    repository.files[target] = source.read_bytes()
    result = gupload.execute_plan(gupload.build_plan([str(source)], cfg), cfg)
    item = result["items"][0]
    assert item["status"] == "skipped"
    assert item["url"] in item["output"]
    assert repository.written_paths == []
    assert gupload.read_history()[-1]["remote_path"] == target


def test_different_content_is_not_uploaded_under_skip_policy(repository, cfg, tmp_path):
    source = tmp_path / "cover.jpg"
    source.write_bytes(b"new content")
    target = "uploads/images/covers/cover.jpg"
    repository.files[target] = b"previous content"
    result = gupload.execute_plan(gupload.build_plan([str(source)], cfg), cfg)
    assert result["items"][0]["status"] == "failed"
    assert repository.files[target] == b"previous content"
    assert repository.written_paths == []


def test_rename_keeps_final_image_folder_and_original_content(repository, cfg, tmp_path):
    source = tmp_path / "cover.jpg"
    source.write_bytes(b"new content")
    original = "uploads/images/covers/cover.jpg"
    renamed = "uploads/images/covers/cover (2).jpg"
    repository.files[original] = b"previous content"
    result = gupload.execute_plan(gupload.build_plan([str(source)], cfg, collision="rename"), cfg)
    assert result["items"][0]["remote_path"] == renamed
    assert repository.files == {original: b"previous content", renamed: b"new content"}
    assert gupload.read_history()[-1]["remote_sha"] == blob_sha(b"new content")


def test_explicit_update_uses_existing_identity_and_records_new_identity(repository, cfg, tmp_path):
    source = tmp_path / "notes.txt"
    source.write_bytes(b"new content")
    target = "uploads/documents/notes.txt"
    repository.files[target] = b"previous content"
    result = gupload.execute_plan(gupload.build_plan([str(source)], cfg, collision="update"), cfg)
    assert result["items"][0]["status"] == "succeeded"
    assert repository.files[target] == b"new content"
    assert gupload.read_history()[-1]["remote_sha"] == blob_sha(b"new content")


def test_partial_failure_retry_does_not_replay_success(repository, cfg, tmp_path):
    first, second = tmp_path / "one.txt", tmp_path / "two.txt"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    repository.fail_paths.add("uploads/documents/two.txt")
    result = gupload.execute_plan(gupload.build_plan([str(first), str(second)], cfg), cfg)
    assert [item["status"] for item in result["items"]] == ["succeeded", "failed"]
    retry = gupload.build_retry_plan(cfg)
    assert [item["source"] for item in retry["items"]] == [str(second)]
    repository.fail_paths.clear()
    assert gupload.execute_plan(retry, cfg)["items"][0]["status"] == "succeeded"
    assert repository.written_paths.count("uploads/documents/one.txt") == 1
    assert repository.written_paths.count("uploads/documents/two.txt") == 1
    assert gupload.build_retry_plan(cfg)["items"] == []


def test_failed_collision_rename_can_be_retried(repository, cfg, tmp_path):
    source = tmp_path / "notes.txt"
    source.write_bytes(b"new content")
    repository.files["uploads/documents/notes.txt"] = b"existing"
    renamed = "uploads/documents/notes (2).txt"
    repository.fail_paths.add(renamed)
    failed = gupload.execute_plan(gupload.build_plan([str(source)], cfg, collision="rename"), cfg)
    assert failed["items"][0]["status"] == "failed"
    repository.fail_paths.clear()
    result = gupload.execute_plan(gupload.build_retry_plan(cfg), cfg)
    assert result["items"][0]["status"] == "succeeded"
    assert repository.files[renamed] == b"new content"
    assert gupload.build_retry_plan(cfg)["items"] == []


def test_failed_downloaded_url_retries_with_clean_unresolved_metadata(repository, cfg, tmp_path, monkeypatch):
    downloads = []

    def download(url, **kwargs):
        path = tmp_path / f"temporary-{len(downloads)}.png"
        path.write_bytes(b"downloaded content")
        downloads.append(path)
        return str(path), "Album Cover.png"

    monkeypatch.setattr(gupload, "download_url", download)
    target = "uploads/images/Album-Cover.png"
    repository.fail_paths.add(target)
    failed = gupload.execute_plan(gupload.build_plan(["https://example.invalid/download"], cfg), cfg)
    assert failed["items"][0]["status"] == "failed"
    assert all(not path.exists() for path in downloads)
    repository.fail_paths.clear()
    retried = gupload.execute_plan(gupload.build_retry_plan(cfg), cfg)
    assert retried["items"][0]["status"] == "succeeded"
    assert repository.files[target] == b"downloaded content"
    assert all(not path.exists() for path in downloads)


def test_release_execution_uses_reviewed_filename_after_clock_changes(repository, cfg, tmp_path, monkeypatch):
    cfg = {**cfg, "contents_max_mb": 0, "release_append_timestamp": True}
    source = tmp_path / "archive.zip"
    source.write_bytes(b"local archive")
    monkeypatch.setattr(gupload.time, "time", lambda: 1000)
    plan = gupload.build_plan([str(source)], cfg, names=["Chosen.zip"])
    reviewed_name = plan["items"][0]["filename"]
    monkeypatch.setattr(gupload.time, "time", lambda: 2000)
    monkeypatch.setattr(gupload, "_find_release", lambda cfg, token: None)
    published = []

    def upload(cfg, token, path, category, **kwargs):
        published.append(kwargs["filename"])
        return "https://example.invalid/asset", 10, 20

    monkeypatch.setattr(gupload, "upload_release_asset", upload)
    result = gupload.execute_plan(plan, cfg)
    assert result["items"][0]["status"] == "succeeded"
    assert published == [reviewed_name]
    assert gupload.read_history()[-1]["asset_id"] == 20


def test_failed_release_replacement_restores_old_asset_without_deletion(repository, cfg, tmp_path, monkeypatch):
    cfg = {**cfg, "contents_max_mb": 0}
    source = tmp_path / "archive.zip"
    source.write_bytes(b"new archive")
    plan = gupload.build_plan([str(source)], cfg, collision="update")
    name = plan["items"][0]["filename"]
    repository.asset = {"id": 91, "name": name, "digest": "sha256:old"}
    monkeypatch.setattr(gupload, "_find_release", lambda cfg, token: {
        "id": 10, "upload_url": "https://example.invalid/upload", "assets": [copy.deepcopy(repository.asset)],
    })

    def upload(*args, **kwargs):
        raise RuntimeError("replacement transport failed")

    monkeypatch.setattr(gupload, "upload_release_asset", upload)
    result = gupload.execute_plan(plan, cfg)
    assert result["items"][0]["status"] == "failed"
    assert repository.asset["name"] == name
    assert repository.deleted_assets == []


def test_boundary_rehash_rejects_modified_local_file_content(repository, cfg, tmp_path, monkeypatch):
    source = tmp_path / "notes.txt"
    source.write_bytes(b"initial content")
    plan = gupload.build_plan([str(source)], cfg)
    reviewed_sha = plan["items"][0]["sha256"]
    # Bypass initial plan validation to simulate disk change after plan check but before upload
    monkeypatch.setattr(gupload, "_validate_plan_sources", lambda *args, **kwargs: None)
    source.write_bytes(b"tampered content")
    result = gupload.execute_plan(plan, cfg)
    item = result["items"][0]
    assert item["status"] == "failed"
    assert "content changed on disk" in item["error"]
    assert item["sha256"] == reviewed_sha
    assert repository.written_paths == []


def test_sensitive_guard_catches_symlink_pointing_to_git_or_config(tmp_path):
    fake_git = tmp_path / "somewhere" / ".git" / "config"
    fake_git.parent.mkdir(parents=True)
    fake_git.write_bytes(b"git content")
    link_to_git = tmp_path / "innocent.txt"
    link_to_git.symlink_to(fake_git)
    reasons = gupload._sensitive_reasons(str(link_to_git))
    assert any("sensitive" in r.lower() for r in reasons)


def test_sensitive_guard_flags_url_userinfo_and_query_credentials():
    url_with_auth = "https://user:password@example.invalid/image.png"
    reasons = gupload._sensitive_reasons(url_with_auth)
    assert any("userinfo" in r.lower() for r in reasons)

    url_with_token = "https://example.invalid/download?token=secret123"
    reasons = gupload._sensitive_reasons(url_with_token)
    assert any("query" in r.lower() for r in reasons)


def test_list_remote_uses_configured_prefix_by_default(repository, cfg):
    cfg_with_prefix = {**cfg, "repo_path_prefix": "custom/root"}
    target_folder = "custom/root/uploads"
    # Put a file in that folder so contents API returns it
    repository.files[f"{target_folder}/item.txt"] = b"data"
    # Test that listing requests the prefix
    listing = gupload.list_remote(cfg_with_prefix)
    assert listing["items"][0]["path"] == f"{target_folder}/item.txt"


def test_bare_path_under_json_fails_with_json_error(capsys):
    with pytest.raises(SystemExit) as exc:
        gupload.main(["--json", "--path", "--", "file.txt"])
    assert exc.value.code == 2
    out, _ = capsys.readouterr()
    import json
    parsed = json.loads(out)
    assert len(parsed["errors"]) > 0
    assert "--path requires an explicit value" in parsed["errors"][0]
