import os
import io
import sys

import subprocess
from pathlib import Path


import pytest
import gupload
import gupload_state
import gupload_platform as platform_adapter


def test_normalize_inputs_decodes_file_uri_and_keeps_urls():
    assert platform_adapter.normalize_inputs([
        "file:///tmp/Artist%20Cover.jpg", "https://example.test/cover.jpg"
    ]) == ["/tmp/Artist Cover.jpg", "https://example.test/cover.jpg"]


def test_normalize_inputs_rejects_remote_file_host():
    with pytest.raises(ValueError, match="Unsupported file URL host"):
        platform_adapter.normalize_inputs(["file://attacker.example/tmp/file.jpg"])

def test_normalize_inputs_rejects_non_http_network_urls():
    with pytest.raises(ValueError, match="Unsupported input URL"):
        platform_adapter.normalize_inputs(["ftp://example.test/file.jpg"])


def test_clipboard_set_passes_text_to_linux_clipboard_process(monkeypatch, tmp_path):
    received = tmp_path / "clipboard-input"
    fixture = tmp_path / "wl-copy"
    fixture.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "with open(os.environ['GUPLOAD_CLIPBOARD_CAPTURE'], 'w', encoding='utf-8') as stream:\n"
        "    stream.write(sys.stdin.read())\n",
        encoding="utf-8",
    )
    fixture.chmod(0o755)
    monkeypatch.setenv("GUPLOAD_CLIPBOARD_CAPTURE", str(received))
    monkeypatch.setattr(platform_adapter.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        platform_adapter.shutil, "which",
        lambda name: str(fixture) if name == "wl-copy" else None,
    )
    text = "https://example.test/a 'quoted' path/é"
    assert platform_adapter.clipboard_set(text)
    assert received.read_text(encoding="utf-8") == text


def test_clipboard_get_uses_linux_paste_utility(monkeypatch):
    monkeypatch.setattr(platform_adapter.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        platform_adapter.shutil, "which",
        lambda name: "/usr/bin/wl-paste" if name == "wl-paste" else None,
    )
    monkeypatch.setattr(
        platform_adapter, "_run",
        lambda command: subprocess.CompletedProcess(command, 0, stdout="https://example.test/a b"),
    )
    assert platform_adapter.clipboard_get() == "https://example.test/a b"




def test_linux_keychain_lookup_is_not_attempted(monkeypatch):
    monkeypatch.setattr(platform_adapter.platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform_adapter.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not access Keychain"))
    assert platform_adapter.get_keychain_token() is None


def test_osascript_returns_argument_as_ordinary_process_data(monkeypatch, tmp_path):
    fixture = tmp_path / "osascript-fixture"
    fixture.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "sys.stdout.write(sys.argv[-1] + '\\n')\n",
        encoding="utf-8",
    )
    fixture.chmod(0o755)
    monkeypatch.setattr(
        platform_adapter.shutil, "which",
        lambda name: str(fixture) if name == "osascript" else None,
    )
    value = "Artist's cover; do not run shell commands — 東京"
    result = platform_adapter._osascript(
        "on run argv\nreturn item 1 of argv\nend run", value
    )
    assert result == value
def test_osascript_failure_preserves_native_stderr(monkeypatch, tmp_path):
    fixture = tmp_path / "osascript-failure"
    fixture.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "sys.stderr.write('native script diagnostic')\n"
        "sys.exit(17)\n",
        encoding="utf-8",
    )
    fixture.chmod(0o755)
    monkeypatch.setattr(
        platform_adapter.shutil, "which",
        lambda name: str(fixture) if name == "osascript" else None,
    )
    with pytest.raises(RuntimeError, match="native script diagnostic"):
        platform_adapter._osascript("error \"failure\"")


def test_linux_headless_no_args_enters_terminal_menu(monkeypatch):
    calls = []

    class FakeCore:
        @staticmethod
        def main(argv):
            calls.append(argv)
            return 0

    monkeypatch.setattr(platform_adapter, "_core_module", lambda: FakeCore)
    monkeypatch.setattr(platform_adapter.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(platform_adapter.sys, "stdin", io.StringIO(""))
    assert platform_adapter.launcher_main([]) == 0
    assert calls == [["--menu"]]
def _prepare_dialog_core(monkeypatch, tmp_path, source):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text("{}", encoding="utf-8")
    cfg = {"owner": "owner", "repo": "repo", "branch": "main"}
    monkeypatch.setattr(gupload_state, "config_path", lambda: config_dir)
    monkeypatch.setattr(gupload, "load_config", lambda: cfg)
    monkeypatch.setattr(platform_adapter, "_core_module", lambda: gupload)
    monkeypatch.setattr(platform_adapter, "_dialog_text", lambda *args: "")
    monkeypatch.setattr(platform_adapter, "choose_files", lambda: [str(source)])
    return cfg


def test_dialog_cancel_after_real_offline_plan_never_executes(monkeypatch, tmp_path):
    source = tmp_path / "--execute"
    source.write_bytes(b"offline plan input")
    _prepare_dialog_core(monkeypatch, tmp_path, source)
    choices = iter([
        "Automatic routing",
        "Automatic",
        "skip-identical",
        "Cancel — do not upload",
    ])
    reviewed = []
    monkeypatch.setattr(
        platform_adapter, "_dialog_choice",
        lambda title, prompt, choices: reviewed.append((title, prompt, choices)) or next(choices_iter),
    )
    choices_iter = choices
    monkeypatch.setattr(gupload, "get_token", lambda cfg: pytest.fail("offline plan must not look up credentials"))
    original_main = gupload.main
    calls = []

    def recording_main(argv):
        calls.append(argv)
        return original_main(argv)

    monkeypatch.setattr(gupload, "main", recording_main)
    assert platform_adapter.dialog_main([str(source)]) == 0
    assert len(calls) == 1
    assert "--execute" not in calls[0]
    separator = calls[0].index("--")
    assert separator > 0
    assert calls[0][separator + 1:] == [str(source)]
    review = next(entry for entry in reviewed if entry[0] == "Review gupload offline plan")
    assert review[0] == "Review gupload offline plan"
    assert "Destination: owner/repo@main" in review[1]
    assert "--execute →" in review[1]
    saved_plan = Path(calls[0][calls[0].index("--save-plan") + 1])
    assert not saved_plan.exists()


def test_dialog_saved_plan_source_guard_blocks_publish(monkeypatch, tmp_path):
    source = tmp_path / "cover.jpg"
    source.write_bytes(b"original")
    _prepare_dialog_core(monkeypatch, tmp_path, source)
    choices = iter([
        "Automatic routing", "Automatic", "skip-identical",
        "Continue to publish confirmation",
    ])
    shown = []
    original_main = gupload.main
    calls = []

    def recording_main(argv):
        calls.append(argv)
        return original_main(argv)

    monkeypatch.setattr(gupload, "main", recording_main)
    monkeypatch.setattr(platform_adapter, "_show_message", lambda title, text: shown.append((title, text)) or "Continue")
    def choose(*args):
        choice = next(choices, None)
        if choice is None:
            source.write_bytes(b"changed after preview")
            return "Publish now"
        return choice

    monkeypatch.setattr(platform_adapter, "_dialog_choice", choose)
    monkeypatch.setattr(gupload, "get_token", lambda cfg: pytest.fail("source mismatch must fail before credentials"))
    assert platform_adapter.dialog_main([str(source)]) == 2
    apply_call = next(argv for argv in calls if "--apply-plan" in argv)
    assert apply_call[apply_call.index("--expect-repo") + 1] == "owner/repo"
    saved_plan = Path(apply_call[apply_call.index("--apply-plan") + 1])
    assert not saved_plan.exists()
def test_plan_output_must_be_one_complete_json_object():
    assert platform_adapter._decode_output('{"items": [], "errors": []}') == {
        "items": [], "errors": [],
    }
    with pytest.raises(ValueError, match="complete JSON plan"):
        platform_adapter._decode_output('{"items": []}\nnoise')
