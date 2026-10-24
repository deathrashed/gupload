"""Atomic, serialized JSON state shared by Gupload frontends."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


def config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gupload"


def data_path(name: str) -> Path:
    if Path(name).name != name or name in {"", ".", ".."}:
        raise ValueError("data filename must be a single path component")
    return config_path() / "data" / name


def read_json(path: str | Path, default: T) -> T:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        return default


def _write_json_unlocked(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def write_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import fcntl
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        _write_json_unlocked(path, value)


def update_json(path: str | Path, default: T, mutate: Callable[[T], T | None]) -> T:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import fcntl
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current = read_json(path, default)
        updated = mutate(current)
        if updated is None:
            updated = current
        _write_json_unlocked(path, updated)
        return updated
