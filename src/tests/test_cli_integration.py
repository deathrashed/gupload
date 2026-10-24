"""Exercise the public launcher with isolated config and forbidden external effects."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "src" / "bin" / "gupload"


@pytest.fixture
def offline_cli(tmp_path):
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    config_dir = config_home / "gupload"
    config_dir.mkdir(parents=True)
    home.mkdir()
    config = {
        "owner": "offline-owner",
        "repo": "offline-repo",
        "branch": "main",
        "organize_by_artist": False,
        "use_path_for_generic_names": False,
        "use_image_subfolders": False,
        "collision_policy": "skip-identical",
        "allowed_destinations": ["offline-owner/offline-repo"],
        "token": "fixture-secret-must-not-enter-a-plan",
    }
    (config_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    probes = tmp_path / "probes"
    probes.mkdir()
    network_marker = tmp_path / "network-attempt"
    tool_marker = tmp_path / "external-tool-attempt"
    (probes / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        "import socket\n"
        "def blocked(*args, **kwargs):\n"
        f"    Path({str(network_marker)!r}).write_text('unexpected network')\n"
        "    raise RuntimeError('network disabled for offline integration test')\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("gh", "security", "pbcopy", "wl-copy", "xclip", "xsel",
                 "termux-clipboard-set", "curl"):
        probe = bin_dir / name
        probe.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' unexpected > '{tool_marker}'\n"
            "exit 88\n",
            encoding="utf-8",
        )
        probe.chmod(0o755)
    env = dict(os.environ)
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "GUPLOAD_BIN", "GUPLOAD_PYTHON"):
        env.pop(key, None)
    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config_home),
        "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
        "PYTHONPATH": str(probes),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TERM": "dumb",
        "COLUMNS": "200",
    })

    def run(*args):
        return subprocess.run(
            [str(LAUNCHER), *map(str, args)], cwd=tmp_path, env=env,
            input="", text=True, capture_output=True, timeout=15,
        )

    yield run, config_dir, network_marker, tool_marker
    assert not network_marker.exists(), "an offline command attempted network access"
    assert not tool_marker.exists(), "an offline command attempted auth/clipboard/transport"


def test_default_launcher_plans_without_credentials_or_state(offline_cli, tmp_path):
    run, config_dir, _, _ = offline_cli
    source = tmp_path / "photo.png"
    content = b"offline photo content"
    source.write_bytes(content)
    result = run(source, "--json")
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["destination"] == {
        "owner": "offline-owner", "repo": "offline-repo", "branch": "main",
    }
    item = plan["items"][0]
    assert item["remote_path"] == "uploads/images/photo.png"
    assert item["sha256"] == hashlib.sha256(content).hexdigest()
    assert item["transport"] == "contents"
    assert not (config_dir / "data").exists()
    assert "fixture-secret-must-not-enter-a-plan" not in result.stdout


def test_saved_plan_refuses_changed_source_before_auth(offline_cli, tmp_path):
    run, config_dir, _, _ = offline_cli
    source = tmp_path / "photo.png"
    source.write_bytes(b"reviewed content")
    saved = tmp_path / "review.json"
    planned = run(source, "--json", "--save-plan", saved)
    assert planned.returncode == 0, planned.stderr
    assert "fixture-secret-must-not-enter-a-plan" not in saved.read_text()
    source.write_bytes(b"different content after review")
    applied = run("--apply-plan", saved, "--execute",
                  "--expect-repo", "offline-owner/offline-repo", "--json")
    assert applied.returncode != 0
    assert "changed" in (applied.stdout + applied.stderr).lower()
    assert not (config_dir / "data").exists()


def test_file_uri_and_custom_name_keep_destination_preset(offline_cli, tmp_path):
    run, _, _, _ = offline_cli
    source = tmp_path / "O'Brien photo.png"
    source.write_bytes(b"offline content")
    result = run(source.as_uri(), "--preset", "wtfpl", "--name", "O'Brien logo.png", "--json")
    assert result.returncode == 0, result.stderr
    item = json.loads(result.stdout)["items"][0]
    assert item["filename"] == "O'Brien logo.png"
    assert item["remote_path"] == "uploads/files/licenses/wtfpl/O'Brien logo.png"
    assert source.read_bytes() == b"offline content"


def test_offline_url_plan_does_not_fetch_unknown_content(offline_cli, tmp_path):
    run, config_dir, _, _ = offline_cli
    result = run("https://example.invalid/Album%20Cover.png", "--json")
    assert result.returncode == 0, result.stderr
    item = json.loads(result.stdout)["items"][0]
    assert item["source_name"] == "Album Cover.png"
    assert item["sha256"] is None
    assert item["size_bytes"] is None
    assert item["transport"] == "unresolved"
    assert not (config_dir / "data").exists()


def test_batch_name_mismatch_fails_before_external_effects(offline_cli, tmp_path):
    run, config_dir, _, _ = offline_cli
    first, second = tmp_path / "one.png", tmp_path / "two.png"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    result = run(first, second, "--names", "only-one", "--json")
    assert result.returncode != 0
    assert not (config_dir / "data").exists()


def test_missing_input_is_a_failure_not_a_successful_empty_plan(offline_cli, tmp_path):
    run, config_dir, _, _ = offline_cli
    result = run(tmp_path / "missing.png", "--json")
    assert result.returncode != 0
    assert not (config_dir / "data").exists()


def test_execute_without_destination_approval_fails_before_auth(offline_cli, tmp_path):
    run, config_dir, _, _ = offline_cli
    config_file = config_dir / "config.json"
    config = json.loads(config_file.read_text())
    config["allowed_destinations"] = []
    config_file.write_text(json.dumps(config))
    source = tmp_path / "photo.png"
    source.write_bytes(b"local data")
    result = run(source, "--execute", "--json")
    assert result.returncode != 0
    assert "expect-repo" in (result.stdout + result.stderr)


def test_wrong_destination_guard_fails_before_auth(offline_cli, tmp_path):
    run, _, _, _ = offline_cli
    source = tmp_path / "photo.png"
    source.write_bytes(b"local data")
    result = run(source, "--execute", "--expect-repo", "other-owner/other-repo", "--json")
    assert result.returncode != 0
    assert "expect-repo" in (result.stdout + result.stderr)


def test_sensitive_input_cannot_publish_without_explicit_override(offline_cli, tmp_path):
    run, config_dir, _, _ = offline_cli
    source = tmp_path / ".env"
    source.write_text("PRIVATE_FIXTURE=value")
    result = run(source, "--execute", "--expect-repo", "offline-owner/offline-repo", "--json")
    assert result.returncode != 0
    assert "sensitive" in (result.stdout + result.stderr).lower()
    assert not (config_dir / "data").exists()


@pytest.mark.parametrize("filename", ["--execute", "--menu", "--dialog"])
def test_option_named_file_after_terminator_cannot_authorize_or_dispatch(
        offline_cli, tmp_path, filename):
    run, config_dir, _, _ = offline_cli
    source = tmp_path / filename
    source.write_bytes(b"an ordinary file with an option-looking name")
    result = run("--json", "--", filename)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["items"][0]["status"] == "planned"
    assert plan["items"][0]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert not (config_dir / "data").exists()
