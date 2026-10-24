import os
import sys
import socket

import pytest

SRC_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, os.path.abspath(SRC_SCRIPTS))


@pytest.fixture(autouse=True)
def isolated_offline_environment(tmp_path, monkeypatch):
    """No regression test may read real user state or open a network connection."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GUPLOAD_BIN", raising=False)

    def reject_network(*args, **kwargs):
        raise AssertionError("Live network access is forbidden in gupload tests")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    monkeypatch.setattr(socket.socket, "connect_ex", reject_network)
