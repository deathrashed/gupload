#!/usr/bin/env python3
"""Portable terminal menu for gupload. Uploads always pass through an offline plan."""
from __future__ import annotations

import html
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gupload
import gupload_state
import gupload_platform


def _data(name: str) -> Path:
    return gupload_state.data_path(name)


def _read(name: str, default: Any) -> Any:
    return gupload_state.read_json(_data(name), default)
def _update(name: str, default: Any, mutate: Any) -> Any:
    return gupload_state.update_json(_data(name), default, mutate)


_INPUT_CLOSED = False

def ask(prompt: str, *, default: str = "") -> str:
    global _INPUT_CLOSED
    try:
        value = input(prompt)
    except (EOFError, KeyboardInterrupt):
        _INPUT_CLOSED = True
        return ""
    return value if value else default


def choose(prompt: str, options: dict[str, str]) -> str:
    if _INPUT_CLOSED:
        return "q"
    for key, label in options.items():
        print(f"  {key}) {label}")
    return ask(prompt).strip().lower()


def confirm_exact(prompt: str) -> bool:
    """Require the literal phrase, not a y/yes, to authorize execution."""
    print(prompt)
    return ask('Type EXECUTE to authorize the upload: ') == "EXECUTE"


def expand_input(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    normalized = gupload_platform.normalize_inputs([value])
    if not normalized:
        return ""
    value = os.path.expanduser(normalized[0])
    return value if gupload.is_url(value) else os.path.abspath(value)


def expand_sources(values: list[str]) -> list[str]:
    expanded: list[str] = []
    for raw_value in values:
        value = expand_input(raw_value)
        if not value:
            continue
        if os.path.isdir(value):
            expanded.extend(sorted(
                str(path) for path in Path(value).rglob("*") if path.is_file()
            ))
        else:
            expanded.append(value)
    return expanded


def _run_core(argv: list[str]) -> tuple[int, str, str]:
    """Run the shared engine and keep machine-readable stdout separate from diagnostics."""
    from contextlib import redirect_stdout, redirect_stderr
    from io import StringIO

    out, err = StringIO(), StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            result = gupload.main(argv)
        code = int(result or 0)
    except SystemExit as exc:
        code = int(exc.code or 0)
    return code, out.getvalue(), err.getvalue()


_LAST_RESULT: dict[str, Any] = {}
_LAST_PLAN: dict[str, Any] = {}


def _parse_result(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Gupload returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("Gupload returned JSON that was not an object.")
    return value


def _print_engine_output(stdout: str, stderr: str) -> None:
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)


def _plan_and_execute(inputs: list[str], *, names: list[str] | None = None,
                      path: str | None = None, preset: str | None = None,
                      collision: str | None = None, formats: list[str] | None = None,
                      retry_failed: bool = False) -> int:
    global _LAST_PLAN
    inputs = expand_sources(inputs)
    _LAST_RESULT.clear()
    _LAST_PLAN = {}
    if not inputs and not retry_failed:
        print("No inputs selected; cancelled.")
        return 0
    if names is not None and len(names) != len(inputs):
        print(f"Expected {len(inputs)} custom names; got {len(names)}.")
        return 2
    fd, plan_path = tempfile.mkstemp(prefix="gupload-menu-plan-", suffix=".json")
    os.close(fd)
    try:
        if retry_failed:
            code, output, diagnostics = _run_core([
                "--retry-failed", "--json", "--save-plan", plan_path,
            ])
        else:
            cfg = _config()
            preset_cfg = gupload.get_presets(cfg).get(preset, {}) if preset else {}
            if preset and not preset_cfg:
                print(f"Unknown preset: {preset}", file=sys.stderr)
                return 2
            if preset:
                cfg = dict(cfg)
                cfg["_active_preset"] = {"name": preset, **preset_cfg}
            effective_collision = collision or preset_cfg.get("collision")
            effective_formats = formats or preset_cfg.get("formats")
            try:
                plan = gupload.build_plan(
                    inputs, cfg, names=names, path=path,
                    collision=effective_collision, formats=effective_formats,
                )
                plan["plan_sha256"] = gupload._plan_integrity(plan)
                gupload_state.write_json(plan_path, plan)
            except (OSError, ValueError) as exc:
                print(f"Unable to create offline plan: {exc}", file=sys.stderr)
                return 2
            code, output, diagnostics = 0, json.dumps(plan, ensure_ascii=False), ""
        _print_engine_output(stdout="", stderr=diagnostics)
        if output:
            try:
                plan = _parse_result(output)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return code or 1
            destination = plan.get("destination")
            if not isinstance(destination, dict) or not destination.get("owner") or not destination.get("repo") \
                    or not isinstance(plan.get("items"), list):
                print("Gupload returned an invalid offline plan.", file=sys.stderr)
                return code or 1
            _LAST_PLAN = plan
            _LAST_RESULT.update(plan)
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        if code:
            return code
        if not output:
            print("Gupload returned no offline plan.", file=sys.stderr)
            return 1
        print(f"Offline plan saved: {plan_path}")
        if not confirm_exact("Review the plan above. No upload has occurred."):
            print("Cancelled; plan was not executed.")
            return 0
        destination = _LAST_PLAN["destination"]
        expected_repo = f"{destination['owner']}/{destination['repo']}"
        apply_code, apply_output, apply_diagnostics = _run_core([
            "--apply-plan", plan_path, "--execute", "--json", f"--expect-repo={expected_repo}",
        ])
        _print_engine_output(stdout="", stderr=apply_diagnostics)
        try:
            _LAST_RESULT.update(_parse_result(apply_output))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return apply_code or 1
        _print_engine_output(apply_output, "")
        return apply_code
    finally:
        try:
            os.unlink(plan_path)
        except FileNotFoundError:
            pass


def _config() -> dict[str, Any]:
    path = gupload_state.config_path() / "config.json"
    value = gupload_state.read_json(path, {})
    if not isinstance(value, dict):
        raise ValueError("Gupload config must be a JSON object.")
    return value


_SECRET_KEY = re.compile(r"(token|password|secret|credential|authorization|private[_-]?key|api[_-]?key)", re.I)
_LOG_SECRET = re.compile(
    r"(?i)\b(token|password|secret|credential|authorization|api[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else _redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _redact_log(text: str) -> str:
    text = re.sub(
        r"(?i)\b(authorization\s*[:=]\s*)(?:bearer|basic)\s+\S+",
        r"\1[REDACTED]", text)
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", text)
    return _LOG_SECRET.sub(r"\1\2[REDACTED]", text)


def _template_map(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, list):
        return {str(item.get("name")): item for item in value
                if isinstance(item, dict) and item.get("name")}
    if isinstance(value, dict):
        return value
    raise ValueError("Template state must be a JSON object or list.")


def _templates() -> dict[str, dict[str, Any]]:
    return _template_map(_read("templates.json", {}))


def _update_templates(change: Any) -> dict[str, dict[str, Any]]:
    def mutate(value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, (dict, list)):
            raise ValueError("Template state must be a JSON object or list.")
        templates = _template_map(value)
        change(templates)
        return templates
    return _update("templates.json", {}, mutate)

def _template_menu() -> None:
    while True:
        templates = _templates()
        print("\nSaved upload templates")
        key = choose("Select: ", {"a": "Apply template", "c": "Create", "v": "View", "d": "Delete", "q": "Back"})
        if key == "q":
            return
        if key == "v":
            if not templates:
                print("No saved templates.")
            for name, value in templates.items():
                print(f"{name}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
            continue
        if key == "c":
            name = ask("Template name: ").strip()
            if not name:
                continue
            print("Settings are optional. Preset settings are inherited, explicit values override them.")
            path = ask("Destination folder (blank = automatic): ").strip()
            preset = ask("Preset (blank = none): ").strip()
            collision = ask("Collision policy (blank/skip-identical/rename/update): ").strip()
            formats = ask("Formats comma-separated (blank = configured default): ").strip()
            pattern = ask("Filename pattern (blank = unchanged): ").strip()
            setting: dict[str, Any] = {}
            if path: setting["path"] = path
            if preset: setting["preset"] = preset
            if collision: setting["collision"] = collision
            if formats: setting["formats"] = [v.strip() for v in formats.split(",") if v.strip()]
            if pattern:
                try:
                    gupload._apply_name_pattern(pattern, "example.png", "Images")
                except ValueError as exc:
                    print(f"Invalid filename pattern: {exc}")
                    continue
                setting["name_pattern"] = pattern
            _update_templates(lambda current: current.__setitem__(name, setting))
            print(f"Saved template {name!r}.")
            continue
        if key == "d":
            name = ask("Template name to delete: ").strip()
            if ask(f"Type DELETE {name} to confirm: ") == f"DELETE {name}":
                _update_templates(lambda current: current.pop(name, None))
            continue
        if key == "a":
            name = ask("Template name: ").strip()
            template = templates.get(name)
            if not template:
                print("Template not found.")
                continue
            values = collect_upload_inputs()
            if not values:
                continue
            try:
                apply_template(template, values)
            except ValueError as exc:
                print(f"Cannot apply template: {exc}")


def apply_name_pattern(pattern: str, source: str) -> str:
    source_name = gupload._source_name(source)
    return gupload._apply_name_pattern(pattern, source_name, gupload.category_for_path(source_name))


def apply_template(template: dict[str, Any], values: list[str]) -> int:
    sources = expand_sources(values)
    preset = gupload.get_presets(_config()).get(template.get("preset"), {})
    pattern = template.get("name_pattern") or preset.get("name_pattern")
    names = ([apply_name_pattern(str(pattern), value) for value in sources] if pattern else None)
    return _plan_and_execute(
        sources,
        names=names,
        path=template.get("path"),
        preset=template.get("preset"),
        collision=template.get("collision"),
        formats=template.get("formats"),
    )


def collect_upload_inputs() -> list[str]:
    print("Enter files, folders, or URLs separated by newlines; blank line ends input.")
    values: list[str] = []
    while True:
        value = ask(f"Input {len(values)+1} (blank to finish): ").strip()
        if not value:
            break
        values.append(expand_input(value))
    return values


def upload_workflow() -> None:
    while True:
        print("\nUpload files")
        key = choose("Select: ", {"1": "Single file/path", "2": "Multiple files", "3": "URL",
                                  "4": "Folder/archive", "5": "Choose files", "6": "Finder selection",
                                  "7": "Artist assets/audio", "q": "Back"})
        if key == "q": return
        if key == "1":
            value = expand_input(ask("File path or folder: "))
            if value and not (Path(value).is_file() or Path(value).is_dir()):
                print("Path is not a readable file or directory."); continue
            values = [value] if value else []
        elif key == "2": values = collect_upload_inputs()
        elif key == "3":
            value = ask("HTTP(S) URL: ").strip()
            values = [value] if urllib.parse.urlsplit(value).scheme in ("http", "https") else []
        elif key == "4":
            folder = expand_input(ask("Folder path: "))
            if not folder or not Path(folder).is_dir(): print("Folder not found."); continue
            values = sorted(str(p) for p in Path(folder).rglob("*") if p.is_file())
            print(f"Selected {len(values)} files.")
        elif key == "5":
            values = gupload_platform.choose_files()
        elif key == "6":
            values = gupload_platform.finder_selection()
            if not values: print("No Finder selection was returned.")
        elif key == "7":
            artist_asset_workflow()
            continue
        else: continue
        values = expand_sources(values)
        if not values: print("No files selected; cancelled."); continue
        names_text = ask("Custom filenames, comma-separated (blank = automatic): ")
        names = [n.strip() for n in names_text.split(",")] if names_text else None
        path = ask("Destination folder under uploads/ (blank = automatic): ").strip() or None
        presets = gupload.get_presets(_config())
        if presets:
            print("Presets: " + ", ".join(sorted(presets)))
        preset = ask("Preset (blank = none): ").strip() or None
        _plan_and_execute(values, names=names, path=path, preset=preset)


def artist_asset_workflow() -> None:
    kind = choose("Artist files: ", {"1": "Collect cover.jpg, logo.png and artist.jpg",
                                      "2": "All audio files in artist folder", "q": "Back"})
    if kind == "q": return
    artist_dir = Path(expand_input(ask("Artist folder: ")))
    if not artist_dir.is_dir():
        print("Artist folder not found.")
        return
    if kind == "1":
        wanted = {"cover.jpg", "logo.png", "artist.jpg"}
        files = sorted(str(path) for path in artist_dir.rglob("*")
                       if path.is_file() and path.name.lower() in wanted)
        label = "artist assets"
    elif kind == "2":
        files = sorted(str(path) for path in artist_dir.rglob("*")
                       if path.is_file() and path.suffix.lower() in gupload.AUDIO_EXT)
        label = "artist audio"
    else:
        return
    if not files:
        print(f"No {label} found under {artist_dir}.")
        return
    print(f"Found {len(files)} {label} files:")
    for path in files:
        print(f"  {path}")
    _plan_and_execute(files)




def remote_browse() -> None:
    """Browse the configured remote tree only after this explicit user action."""
    folder: str | None = None
    while True:
        args = [f"--list-remote={folder}"] if folder else ["--list-remote"]
        args.append("--json")
        code, output, diagnostics = _run_core(args)
        _print_engine_output("", diagnostics)
        try:
            listing = _parse_result(output)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            if output:
                print(output, file=sys.stderr)
            return
        if code or listing.get("errors"):
            _print_engine_output(output, "")
            return
        items = listing.get("items")
        if not isinstance(items, list):
            print("Remote listing did not contain an item list.", file=sys.stderr)
            return
        query = ask("Artist/category filter (blank = all): ").casefold().strip()
        visible = [item for item in items
                   if not query or query in str(item.get("path", "")).casefold()
                   or query in str(item.get("name", "")).casefold()]
        folders = [item for item in visible if item.get("type") == "dir"]
        print(f"\nRemote folder: {folder or 'uploads'}")
        for index, item in enumerate(visible, 1):
            kind = "dir" if item.get("type") == "dir" else "file"
            print(f"{index}. [{kind}] {item.get('name')}  {item.get('path')}")
        action = ask("Open folder number/path, '..' to go up, 's' to change filter, q to return: ").strip()
        if action.lower() == "q":
            return
        if action == "..":
            if folder and folder != "uploads":
                parent = folder.rsplit("/", 1)[0]
                folder = parent or None
            elif folder == "uploads":
                folder = None
            continue
        if action.lower() == "s":
            continue
        selected = None
        if action.isdigit():
            index = int(action) - 1
            if 0 <= index < len(visible):
                selected = visible[index]
        else:
            selected = next((item for item in visible
                             if item.get("type") == "dir"
                             and action in {item.get("path"), item.get("name")}), None)
        if selected and selected.get("type") == "dir":
            folder = str(selected.get("path") or "")
        elif action:
            print("Select a listed folder, '..', 's', or q.")


def _history() -> list[dict[str, Any]]:
    records = gupload.read_history()
    if not isinstance(records, list):
        raise ValueError("History state must be a JSON list.")
    return records


def history_menu() -> None:
    while True:
        records = _history()
        print("\nUpload history")
        key = choose("Select: ", {"v": "View/search", "c": "Copy URL", "e": "Export JSON/CSV", "m": "Markdown gallery", "h": "HTML gallery", "r": "Retry failed only", "p": "Repeat last", "q": "Back"})
        if key == "q": return
        query = ""
        rows = records
        if key == "v":
            query = ask("Search filename/path/status (blank = all): ").casefold()
            rows = [r for r in records if query in json.dumps(r, ensure_ascii=False).casefold()]
            for i, record in enumerate(rows, 1): print(f"{i}. {json.dumps(record, ensure_ascii=False, sort_keys=True)}")
        elif key == "c":
            for i, record in enumerate(records, 1):
                print(f"{i}. {record.get('filename', record.get('source_name', 'file'))} — {record.get('url', '')}")
            try: index = int(ask("History number: ")) - 1
            except ValueError: continue
            if 0 <= index < len(records):
                url = str(records[index].get("url", ""))
                if url and gupload_platform.clipboard_set(url): print(f"Copied {url}")
                elif url: print("Clipboard is unavailable; URL: " + url)
        elif key == "e":
            fmt = ask("Format json/csv: ").strip().lower()
            destination = Path(expand_input(ask("Output file: ")))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "json": destination.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            elif fmt == "csv":
                import csv
                keys = sorted({k for row in records for k in row})
                with destination.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=keys); writer.writeheader(); writer.writerows(records)
            else: print("Choose json or csv."); continue
            print(f"Exported {len(records)} records to {destination}")
        elif key in ("m", "h"):
            destination = Path(expand_input(ask("Gallery output file: ")))
            if key == "m":
                content = "\n".join(f"- [{r.get('filename', r.get('source_name','file'))}]({r.get('url','')})" for r in records) + "\n"
            else:
                content = "<!doctype html><meta charset='utf-8'><title>Gupload gallery</title><main>" + "".join(
                    f"<figure><a href='{html.escape(str(r.get('url','')), quote=True)}'><img loading='lazy' src='{html.escape(str(r.get('url','')), quote=True)}' alt='{html.escape(str(r.get('filename','file')), quote=True)}'></a><figcaption>{html.escape(str(r.get('filename','file')))}</figcaption></figure>"
                    for r in records) + "</main>"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            print(f"Gallery written to {destination}")
        elif key == "r":
            failed = [r for r in records if str(r.get("status", "")).lower() in {"failed", "error"} or r.get("error")]
            if not failed:
                print("No failed history items.")
                continue
            _plan_and_execute([], retry_failed=True)
        elif key == "p":
            last = records[-1] if records else None
            src = last and (last.get("source") or last.get("source_path") or last.get("filepath")
                            or last.get("file_path") or last.get("path"))
            if src: _plan_and_execute([str(src)])
            else: print("No previous upload source is available.")


def _favorite_path(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("path") or value.get("source") or value.get("filepath")
                   or value.get("file_path") or value.get("source_path") or "")
    return str(value)


def _favorites() -> list[Any]:
    value = _read("favorites.json", [])
    if isinstance(value, dict) and any(key in value for key in ("path", "source", "filepath", "file_path")):
        return [value]
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    raise ValueError("Favorites state must be a JSON list or object.")


def _update_favorites(change: Any) -> list[Any]:
    def mutate(value: Any) -> list[Any]:
        if not isinstance(value, (list, dict)):
            raise ValueError("Favorites state must be a JSON list or object.")
        if isinstance(value, dict) and any(key in value for key in ("path", "source", "filepath", "file_path")):
            favorites = [value]
        elif isinstance(value, list):
            favorites = value
        else:
            favorites = list(value.values())
        change(favorites)
        return favorites
    return _update("favorites.json", [], mutate)


def favorites_menu() -> None:
    while True:
        favorites = _favorites()
        print("\nFavorites")
        key = choose("Select: ", {"v": "View", "a": "Add file/URL", "u": "Upload favorite", "d": "Remove", "q": "Back"})
        if key == "q": return
        if key == "v":
            for i, item in enumerate(favorites, 1): print(f"{i}. {_favorite_path(item)}")
        elif key == "a":
            value = expand_input(ask("File path or URL: "))
            if value:
                _update_favorites(lambda current: current.append(value) if value not in
                                  [_favorite_path(item) for item in current] else None)
        elif key in ("u", "d"):
            try: index = int(ask("Favorite number: ")) - 1
            except ValueError: continue
            if not 0 <= index < len(favorites): continue
            if key == "u": _plan_and_execute([_favorite_path(favorites[index])])
            else:
                item = favorites[index]
                _update_favorites(lambda current: current.remove(item) if item in current else None)

def queue_results(queue: list[dict[str, Any]], inputs: list[str], result: dict[str, Any],
                  eligible: tuple[str, ...] = ("pending",), queue_ids: set[str] | None = None) -> None:
    """Account only completed outcomes; planned and unresolved entries remain retryable."""
    successful = {"succeeded", "skipped", "uploaded", "completed"}
    failed = {"failed", "error"}
    result_items = result.get("items", [])
    requested = set(inputs)
    for item in queue:
        source = item.get("source")
        if item.get("status", "pending") not in eligible:
            continue
        if source not in requested and (queue_ids is None or item.get("id") not in queue_ids):
            continue
        normalized = expand_input(str(source))
        is_directory = bool(normalized and os.path.isdir(normalized))
        states: list[str] = []
        for result_item in result_items:
            result_source = str(result_item.get("source", ""))
            matches = result_source == normalized
            if is_directory and not matches:
                try:
                    matches = os.path.commonpath([normalized, result_source]) == normalized
                except ValueError:
                    matches = False
            if not matches:
                continue
            status = str(result_item.get("status", "")).lower()
            if result_item.get("error") or status in failed:
                states.append("failed")
            elif status in successful:
                states.append("completed")
            else:
                states.append("pending")
        if "failed" in states:
            item["status"] = "failed"
        elif states and all(state == "completed" for state in states):
            item["status"] = "completed"
        elif not states and result.get("errors"):
            item["status"] = "failed"


def _queue_item(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"id": uuid.uuid4().hex, "source": value, "status": "pending"}
    if not isinstance(value, dict):
        raise ValueError("Queue entries must be strings or JSON objects.")
    item = dict(value)
    item.setdefault("id", uuid.uuid4().hex)
    item["source"] = str(item.get("source") or item.get("filepath") or item.get("file_path") or item.get("path") or "")
    status = str(item.get("status", "pending")).lower()
    item["status"] = {"completed": "completed", "uploaded": "completed", "succeeded": "completed",
                      "done": "completed", "error": "failed"}.get(status, status)
    return item


def _queue() -> list[dict[str, Any]]:
    return _update_queue(lambda queue: None)


def _update_queue(change: Any) -> list[dict[str, Any]]:
    def mutate(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("Queue state must be a JSON list.")
        queue = [_queue_item(item) for item in value]
        change(queue)
        return queue
    return _update("upload_queue.json", [], mutate)


def queue_menu() -> None:
    while True:
        queue = _queue()
        print("\nUpload queue")
        key = choose("Select: ", {"a": "Add inputs", "v": "View", "r": "Remove", "p": "Process pending",
                                  "f": "Retry failed only", "c": "Clear queue", "q": "Back"})
        if key == "q": return
        if key == "a":
            additions = [{"id": uuid.uuid4().hex, "source": value, "status": "pending"}
                         for value in collect_upload_inputs() if value]
            if additions:
                _update_queue(lambda current: current.extend(additions))
        elif key == "v":
            for i, item in enumerate(queue, 1): print(f"{i}. {json.dumps(item, ensure_ascii=False)}")
        elif key == "r":
            try: index = int(ask("Queue number: ")) - 1
            except ValueError: continue
            if 0 <= index < len(queue):
                ident = queue[index]["id"]
                _update_queue(lambda current: current.__setitem__(
                    slice(None), [item for item in current if item.get("id") != ident]))
        elif key == "c":
            if ask("Type CLEAR QUEUE to confirm: ") == "CLEAR QUEUE":
                _update_queue(lambda current: current.clear())
        elif key in ("p", "f"):
            eligible = ("pending",) if key == "p" else ("failed",)
            selected = [item for item in queue if item.get("status", "pending") in eligible]
            sources = [str(item["source"]) for item in selected if item.get("source")]
            if not sources: print("No eligible queue items."); continue
            ids = {item["id"] for item in selected}
            _plan_and_execute(sources)

            def account(current: list[dict[str, Any]]) -> None:
                queue_results(current, sources, _LAST_RESULT, eligible, ids)
            _update_queue(account)


def clipboard_monitor() -> None:
    """Opt-in clipboard watcher. Candidates are queued, never auto-uploaded."""
    print("Clipboard monitoring is opt-in and only queues candidates; publish only through plan review and EXECUTE.")
    if not gupload_platform.clipboard_available():
        print("Clipboard monitoring is unavailable: no compatible clipboard utility was found.", file=sys.stderr)
        return
    if ask("Type MONITOR to start (Ctrl-C stops): ") != "MONITOR": return
    last = None
    try:
        while True:
            value = gupload_platform.clipboard_get()
            if value and value != last:
                last = value
                candidate = expand_input(value)
                if candidate and (Path(candidate).is_file() or urllib.parse.urlsplit(candidate).scheme in ("http", "https")):
                    entry = {"id": uuid.uuid4().hex, "source": candidate, "status": "pending"}
                    _update_queue(lambda queue: queue.append(entry))
                    print(f"Queued clipboard candidate: {candidate}")
            time.sleep(1)
    except (KeyboardInterrupt, EOFError):
        print("Clipboard monitor stopped.")


def configure() -> None:
    path = gupload_state.config_path() / "config.json"
    cfg = gupload_state.read_json(path, {})
    print(json.dumps(_redact(cfg), ensure_ascii=False, indent=2, sort_keys=True))
    key = ask("Config key to change (blank = back): ").strip()
    if not key: return
    raw = ask("New JSON value: ")
    try: value = json.loads(raw)
    except json.JSONDecodeError: print("Value must be valid JSON."); return

    def mutate(current: Any) -> dict[str, Any]:
        if not isinstance(current, dict):
            raise ValueError("Gupload config must be a JSON object.")
        current[key] = value
        return current
    gupload_state.update_json(path, {}, mutate)


def logs_stats_help() -> None:
    while True:
        key = choose("Select: ", {"l": "View log", "s": "Stats", "c": "Config summary", "h": "Help", "q": "Back"})
        if key == "q": return
        if key == "l":
            log_path = Path(os.environ.get("GUPLOAD_LOG", "/tmp/gupload.log"))
            if log_path.exists():
                print(_redact_log(log_path.read_text(encoding="utf-8", errors="replace")[-20000:]))
            else: print(f"No log file at {log_path}")
        elif key == "s":
            records = _history(); failed = sum(1 for x in records if x.get("error") or x.get("status") in ("failed", "error"))
            print(f"History: {len(records)} records; failed: {failed}; succeeded: {len(records)-failed}")
        elif key == "c":
            print(json.dumps(_redact(_config()), ensure_ascii=False, indent=2, sort_keys=True))
        elif key == "h":
            print("Gupload menu: offline plan first; inspect destination, names, warnings and collisions. Only exact EXECUTE applies the saved plan.")
            print("Remote browsing is read-only and runs only when explicitly selected. q backs out; blank input cancels.")


def main(argv: list[str] | None = None) -> int:
    if argv not in (None, [], ["--menu"]):
        return 2
    while True:
        print("\nGupload — offline-first uploader")
        key = choose("Select: ", {"1": "Upload files/URL/folder/artist assets", "2": "Browse remote repository (read-only)", "3": "History/search/export/galleries/retry", "4": "Favorites", "5": "Queue", "6": "Templates", "7": "Clipboard monitor (opt-in)", "8": "Configure", "9": "Logs/stats/help", "q": "Quit"})
        if key == "q": return 0
        if key == "1": upload_workflow()
        elif key == "2": remote_browse()
        elif key == "3": history_menu()
        elif key == "4": favorites_menu()
        elif key == "5": queue_menu()
        elif key == "6": _template_menu()
        elif key == "7": clipboard_monitor()
        elif key == "8": configure()
        elif key == "9": logs_stats_help()


if __name__ == "__main__":
    raise SystemExit(main())
