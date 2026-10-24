"""Consumer-visible persistence invariants across separate writers and interrupted writes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import gupload_state


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_concurrent_process_updates_preserve_all_records(tmp_path):
    state = tmp_path / "history.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    writer = (
        "import sys\n"
        "from gupload_state import update_json\n"
        "for index in range(12):\n"
        "    update_json(sys.argv[1], [], "
        "lambda items: items + [sys.argv[2] + ':' + str(index)])\n"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", writer, str(state), str(worker)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for worker in range(4)
    ]
    for process in processes:
        out, err = process.communicate(timeout=20)
        assert process.returncode == 0, out + err
    assert sorted(json.loads(state.read_text())) == sorted(
        f"{worker}:{index}" for worker in range(4) for index in range(12)
    )


def test_corrupt_history_is_not_replaced_by_empty_state(tmp_path):
    history = tmp_path / "history.json"
    corrupt = b'{"incomplete": '
    history.write_bytes(corrupt)
    with pytest.raises((ValueError, json.JSONDecodeError)):
        gupload_state.update_json(history, [], lambda items: items + [{"status": "succeeded"}])
    assert history.read_bytes() == corrupt


def test_failed_atomic_commit_preserves_last_complete_state(tmp_path, monkeypatch):
    history = tmp_path / "history.json"
    original = [{"source": "first.png", "status": "succeeded"}]
    gupload_state.write_json(history, original)

    def interrupted_replace(*args):
        raise OSError("simulated interruption before commit")

    monkeypatch.setattr(gupload_state.os, "replace", interrupted_replace)
    with pytest.raises(OSError, match="interruption"):
        gupload_state.update_json(history, [], lambda records: records + [{"source": "second.png"}])
    assert json.loads(history.read_text()) == original
    assert not list(tmp_path.glob("*.tmp"))
