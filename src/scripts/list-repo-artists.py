#!/usr/bin/env python3
"""Read artist names and files from gupload's configured uploads tree."""
import json
import os
import sys
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from gupload import api_request, get_token, load_config


def _warn(message):
    print(f"list-repo-artists: {message}", file=sys.stderr)


def _contents_url(cfg, path):
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}?ref={urllib.parse.quote(branch, safe='')}"


def _upload_root(cfg):
    prefix = cfg.get("repo_path_prefix", "").strip("/")
    return f"{prefix}/uploads" if prefix else "uploads"


def _contents(cfg, path):
    result = api_request("GET", _contents_url(cfg, path), get_token(cfg))
    if result is None:
        raise RuntimeError(f"GitHub returned no contents for {path}")
    if not isinstance(result, list):
        raise RuntimeError(f"GitHub contents response for {path} was not a directory listing")
    for item in result:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise RuntimeError(f"GitHub contents response for {path} contained an invalid entry")
    return result


def list_artists():
    """List artist directories, or artists inferred from cover filenames."""
    cfg = load_config()
    organized = cfg.get("organize_by_artist", False)
    path = f"{_upload_root(cfg)}/audio" if organized else f"{_upload_root(cfg)}/images/covers"
    result = _contents(cfg, path)
    artists = set()
    for item in result:
        if item.get("type") == "dir":
            artists.add(item["name"])
        elif item.get("type") == "file" and not organized:
            name = item["name"]
            if " - " in name:
                artists.add(name.split(" - ", 1)[0])
    return sorted(artists)


def list_artist_files(artist_name):
    """List files for one artist from the configured destination tree."""
    cfg = load_config()
    root = _upload_root(cfg)
    if cfg.get("organize_by_artist", False):
        path = f"{root}/audio/{artist_name}"
        items = _contents(cfg, path)
        return [{"name": item["name"], "type": item.get("type", "file"),
                 "path": item.get("path", f"{path}/{item['name']}")}
                for item in items]

    path = f"{root}/images/covers"
    items = _contents(cfg, path)
    prefix = artist_name + " - "
    return [{"name": item["name"], "type": item.get("type", "file"),
             "path": item.get("path", f"{path}/{item['name']}")}
            for item in items
            if item.get("type") == "file" and item["name"].startswith(prefix)]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] == "--files":
            if len(argv) != 2:
                raise ValueError("usage: list-repo-artists.py --files ARTIST")
            print(json.dumps(list_artist_files(argv[1])))
        elif not argv:
            print("\n".join(list_artists()))
        else:
            raise ValueError("usage: list-repo-artists.py [--files ARTIST]")
        return 0
    except Exception as exc:
        _warn(f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
