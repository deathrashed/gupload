import json

import pytest

import gupload
import gupload_state


def test_default_cli_is_offline_json_plan(tmp_path, monkeypatch, capsys):
    source = tmp_path / "file.txt"
    source.write_text("data")
    monkeypatch.setattr(gupload, "load_config", lambda: {"owner": "owner", "repo": "repo", "dedup_strategy": "none"})
    monkeypatch.setattr(gupload, "get_token", lambda cfg: pytest.fail("offline plan requested a token"))
    monkeypatch.setattr(gupload, "api_request", lambda *args, **kwargs: pytest.fail("offline plan requested network"))

    assert gupload.main([str(source), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["destination"] == {"owner": "owner", "repo": "repo", "branch": "main"}
    assert result["items"][0]["status"] == "planned"
    assert result["items"][0]["sha256"]


def test_malformed_names_fail_before_config_or_network(monkeypatch):
    monkeypatch.setattr(gupload, "load_config", lambda: pytest.fail("config loaded before argument validation"))
    with pytest.raises(SystemExit):
        gupload.main(["one", "two", "--names", "single"])


def test_custom_image_name_keeps_artist_subfolder(tmp_path):
    source = tmp_path / "artist.jpg"
    source.write_bytes(b"image")
    path, category = gupload.build_repo_path({"dedup_strategy": "none"}, str(source), custom_name="portrait")
    assert (path, category) == ("uploads/images/artists/portrait.jpg", "Images")


def test_custom_name_respects_script_and_explicit_folder_routing(tmp_path):
    source = tmp_path / "tool.py"
    source.write_text("print('ok')")
    assert gupload.build_repo_path({"dedup_strategy": "none"}, str(source), custom_name="renamed") == (
        "uploads/scripts/python/renamed.py", "Scripts")
    assert gupload.build_repo_path({"dedup_strategy": "none"}, str(source), custom_name="renamed",
                                   override_path="icons/docker") == ("uploads/icons/docker/renamed.py", "Scripts")


def test_url_plan_keeps_source_basename_and_is_unresolved():
    plan = gupload.build_plan(["https://example.test/assets/cover%20art.png?token=ignored"],
                              {"owner": "owner", "repo": "repo", "dedup_strategy": "none"})
    item = plan["items"][0]
    assert item["source_name"] == "cover art.png"
    assert item["filename"] == "cover-art.png"
    assert item["transport"] == "unresolved"
    assert item["sha256"] is None and item["size_bytes"] is None


def test_missing_remote_only_404_is_treated_as_absent(monkeypatch):
    monkeypatch.setattr(gupload, "api_request", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("GET -> 404")))
    assert gupload._github_contents({"owner": "o", "repo": "r"}, "token", "uploads/a") is None
    monkeypatch.setattr(gupload, "api_request", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("GET -> 403")))
    with pytest.raises(RuntimeError, match="403"):
        gupload._github_contents({"owner": "o", "repo": "r"}, "token", "uploads/a")


def test_saved_plan_checks_source_hash_destination_and_integrity(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("original")
    cfg = {"owner": "owner", "repo": "repo", "dedup_strategy": "none"}
    plan = gupload.build_plan([str(source)], cfg)
    plan["plan_sha256"] = gupload._plan_integrity(plan)
    saved = tmp_path / "plan.json"
    saved.write_text(json.dumps(plan))
    assert gupload._load_saved_plan(str(saved), cfg)["items"][0]["sha256"] == plan["items"][0]["sha256"]
    source.write_text("changed")
    with pytest.raises(ValueError, match="changed or is missing|changed since planning"):
        gupload._load_saved_plan(str(saved), cfg)
    with pytest.raises(ValueError, match="destination"):
        gupload._load_saved_plan(str(saved), {**cfg, "repo": "other"})


def test_atomic_state_update_preserves_existing_records(tmp_path):
    path = tmp_path / "history.json"
    path.write_text('[{"source":"old"}]')
    result = gupload_state.update_json(path, [], lambda rows: rows + [{"source": "new"}])
    assert result == [{"source": "old"}, {"source": "new"}]
    assert json.loads(path.read_text()) == result


def test_corrupt_state_is_not_silently_replaced(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("not-json")
    with pytest.raises(json.JSONDecodeError):
        gupload_state.update_json(path, [], lambda rows: rows + ["new"])
    assert path.read_text() == "not-json"


def test_final_path_collision_skip_rename_and_update(tmp_path, monkeypatch):
    source = tmp_path / "song.txt"
    source.write_text("first")
    cfg = {"owner": "owner", "repo": "repo", "dedup_strategy": "none"}
    plan = gupload.build_plan([str(source)], cfg, names=["custom"])
    item = plan["items"][0]
    blob_sha = gupload._git_blob_sha(str(source))
    existing = {"sha": blob_sha, "download_url": "https://cdn.test/uploads/custom.txt"}
    monkeypatch.setattr(gupload, "_github_contents", lambda _cfg, _token, path: existing if path == item["remote_path"] else None)

    gupload.resolve_remote_collision(cfg, "token", item)
    assert item["status"] == "skipped"
    assert item["url"] == existing["download_url"]
    assert item["output"]

    source.write_text("different")
    plan = gupload.build_plan([str(source)], cfg, names=["custom"], collision="rename")
    item = plan["items"][0]
    monkeypatch.setattr(gupload, "_github_contents", lambda _cfg, _token, path: existing if path == item["remote_path"] else None)
    gupload.resolve_remote_collision(cfg, "token", item)
    assert item["remote_path"].endswith("/custom (2).txt")
    assert item.get("remote_sha") is None

    plan = gupload.build_plan([str(source)], cfg, names=["custom"], collision="update")
    item = plan["items"][0]
    monkeypatch.setattr(gupload, "_github_contents", lambda *_args: existing)
    gupload.resolve_remote_collision(cfg, "token", item)
    assert item["remote_sha"] == blob_sha


def test_retry_plan_excludes_items_with_later_success(monkeypatch):
    failed = {"item_id": "one", "status": "failed", "source": "/tmp/a", "sha256": "x",
              "owner": "owner", "repo": "repo", "branch": "main"}
    success = dict(failed, status="succeeded")
    still_failed = {"item_id": "two", "status": "failed", "source": "/tmp/b", "sha256": "y",
                    "owner": "owner", "repo": "repo", "branch": "main"}
    monkeypatch.setattr(gupload, "read_history", lambda: [failed, success, still_failed])
    monkeypatch.setattr(gupload.os.path, "isfile", lambda _path: True)
    monkeypatch.setattr(gupload, "_sha256_file", lambda path: "x" if path.endswith("a") else "y")
    monkeypatch.setattr(gupload.os.path, "getsize", lambda _path: 1)
    plan = gupload.build_retry_plan({"owner": "owner", "repo": "repo"})
    assert [item["item_id"] for item in plan["items"]] == ["two"]


def test_formatted_custom_name_and_cdn_url_are_escaped():
    lines, warnings = gupload.render_formats(
        ["mdlink", "html"], 'A [great] name &".png', "https://cdn.test/a b(c).png?x=1&y=2",
        is_image=True, is_audio=False)
    assert lines[0] == '[A \\[great\\] name &".png](https://cdn.test/a%20b%28c%29.png?x=1&y=2)'
    assert lines[1] == '<img src="https://cdn.test/a b(c).png?x=1&amp;y=2">'
    assert warnings == []
    assert gupload.build_jsdelivr_url("owner", "repo", "feature/custom branch", "uploads/a b/file#.png") == (
        "https://cdn.jsdelivr.net/gh/owner/repo@feature%2Fcustom%20branch/uploads/a%20b/file%23.png")
