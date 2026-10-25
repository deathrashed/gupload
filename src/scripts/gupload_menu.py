#!/usr/bin/env python3
"""Portable terminal menu for gupload. Uploads always pass through an offline plan."""
from __future__ import annotations

import functools
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
import gupload_ui as ui


def _data(name: str) -> Path:
    return gupload_state.data_path(name)


def _read(name: str, default: Any) -> Any:
    return gupload_state.read_json(_data(name), default)
def _update(name: str, default: Any, mutate: Any) -> Any:
    return gupload_state.update_json(_data(name), default, mutate)


_INPUT_CLOSED = False

def ask(prompt: str, *, default: str = "") -> str:
    global _INPUT_CLOSED
    if ui.FULLSCREEN:
        return _form_ask(prompt, default)
    try:
        value = input(prompt)
    except (EOFError, KeyboardInterrupt):
        _INPUT_CLOSED = True
        return ""
    return value if value else default


_BACK_WORDS = {"q", "b", "back", "quit", "exit", "esc", ":q"}


_BLURBS = {
    "Dashboard": "pick something to upload, or look after what you already have",
    "Upload": "every upload becomes an offline plan you review before anything is sent",
    "Artist files": "collect an artist folder's artwork or audio in one go",
    "History": "everything gupload has uploaded, with links ready to copy",
    "Favorites": "paths you upload again and again",
    "Queue": "collect inputs now, upload them together later",
    "Templates": "saved destination, preset and naming you can reuse",
    "Logs, stats & help": "what happened, how much, and how the menu works",
}
_CURSOR: dict[str, int] = {}


def _tab() -> str:
    try:
        cfg = _config()
    except (OSError, ValueError):
        return "config.json unreadable"
    if cfg.get("owner") and cfg.get("repo"):
        return f"github.com/{cfg['owner']}/{cfg['repo']}"
    return "no destination set"


_FORM: dict[str, Any] | None = None


def page(section: str, glyph: str = "upload", blurb: str | None = None) -> None:
    """Start a fresh full-screen page for *section* (no-op in the scrolling menu). What the action
    prints and asks from here on is collected into the page's frame."""
    global _FORM
    if not ui.FULLSCREEN:
        return
    blurb = _BLURBS.get(section, "") if blurb is None else blurb
    _FORM = {"section": section, "glyph": glyph, "blurb": blurb, "lines": []}
    ui.set_inset(4, section, glyph)
    _draw_head(_FORM)
    ui.answered()


def _end_form() -> None:
    global _FORM
    _FORM = None
    ui.set_inset(0)


def _draw_head(form: dict[str, Any]) -> int:
    ui.clear()
    head = ui.header(form["section"], tab=_tab(), glyph=form["glyph"])
    for line in head:
        print(line)
    if form["blurb"]:
        print(ui.center(ui.hint(form["blurb"])))
    print()
    return len(head) + (2 if form["blurb"] else 1)


def _pending() -> list[str]:
    """Lines printed since the last answer, wrapped to the action frame, outer blank lines dropped."""
    if not isinstance(sys.stdout, ui._Page):
        return []
    lines = "".join(sys.stdout.since_answer).splitlines()
    ui.answered()
    while lines and not ui.strip(lines[0]).strip():
        lines.pop(0)
    while lines and not ui.strip(lines[-1]).strip():
        lines.pop()
    out: list[str] = []
    width = ui._layout()[0] - 4
    for line in lines:
        out.extend(ui.wrap_styled(line.expandtabs(4), width))
    return out


def _draw_form(form: dict[str, Any], *, question: list[str] | None = None, top: int | None = None,
               keys: list[tuple[str, str]] | None = None) -> tuple[int, int]:
    """Redraw an action page: header, then one frame holding the page's lines (from *top*, or the
    newest ones) and, when asking, the question and an input row; the key hints sit under the
    frame as on a menu. Returns (top, visible rows) so callers can scroll."""
    width, rows = ui._layout()
    used = _draw_head(form)
    lines = form["lines"]
    asking = question is not None
    room = max(3, rows - used - 2 - (len(question) + 2 if asking else 0) - 3)
    last = max(0, len(lines) - room)
    top = last if top is None else max(0, min(top, last))
    shown = lines[top:top + room]
    body = list(shown)
    if asking:
        body += ([""] if shown else []) + question + [""]
    above, below = top, len(lines) - top - len(shown)
    marks = ([f"↑ {above} more"] if above else []) + ([f"↓ {below} more"] if below else [])
    title = ui.heading(form["glyph"], form["section"])
    framed = ui.frame(title, body or [ui.hint("Working…")], subtitle=ui.hint("  ".join(marks)), width=width)
    print(framed)
    if keys:
        print()
        print(ui.footer(keys))
    if asking:  # back up onto the input row, the frame's last content line
        sys.stdout.flush()
        ui._raw("\x1b[%dA\r" % (4 if keys else 2))
    sys.stdout.flush()
    ui.answered()
    return top, room


def _form_ask(prompt: str, default: str) -> str:
    """A question on the action page: everything printed so far stays in the frame above it, the
    answer is typed on a framed input row, and Esc goes back to the menu."""
    global _INPUT_CLOSED
    if _FORM is None:
        page("Gupload", "upload", "")
    form = _FORM
    form["lines"].extend(_pending())
    width = ui._layout()[0]
    head = getattr(prompt, "head", "") or ui.strip(prompt).strip()
    extra = getattr(prompt, "extra", "")
    one_line = head + (" " + extra if extra else "")
    question = [one_line] if ui.visible_width(one_line) <= width - 4 else [head] + ([extra] if extra else [])
    placeholder = getattr(prompt, "default", "") or ""
    placeholder = f"Enter for {placeholder}" if placeholder else "type here"
    keys = [("enter", "confirm"), ("esc", "back"), ("←→", "edit"), ("ctrl-u", "clear")]
    view = {"top": None, "room": 0}
    view["top"], view["room"] = _draw_form(form, question=question, keys=keys)
    if len(form["lines"]) > view["room"]:
        keys.insert(2, ("↑↓", "scroll"))
        view["top"], view["room"] = _draw_form(form, question=question, keys=keys)

    def render(text: str, cursor: int) -> None:
        row, column = ui.input_row(text, cursor, placeholder=placeholder, width=width)
        ui._raw("\r" + ui.margin() + row + "\r\x1b[%dC" % (len(ui.margin()) + column))

    def scroll(pressed: str) -> None:
        step = {"up": -1, "down": 1, "pgup": -view["room"], "pgdn": view["room"]}[pressed]
        view["top"], view["room"] = _draw_form(form, question=question, top=view["top"] + step, keys=keys)

    try:
        value = ui.edit_line(render, scroll)
    except (EOFError, KeyboardInterrupt):
        _INPUT_CLOSED = True
        raise ui.Cancelled from None
    finally:
        ui._raw("\r\n")
    label = getattr(prompt, "label", "") or ui.strip(head)
    shown = ui.value(value) if value else ui.hint(getattr(prompt, "default", "") or "—")
    form["lines"].append(ui.paint(ui.icon("arrow") or ">", ui.VIOLET) + " " + ui.hint(label) + "  " + shown)
    _draw_form(form)
    return value if value else default


def _form_view(lines: list[str]) -> None:
    """Show output that is too long for a notice in the action frame and wait for a key;
    ↑↓/PgUp/PgDn scroll when it does not fit."""
    form = _FORM or {"section": "Gupload", "glyph": "upload", "blurb": "", "lines": []}
    start = len(form["lines"])
    form["lines"].extend(lines)
    keys = [("any key", "to continue")]
    top, room = _draw_form(form, top=start, keys=keys)
    top = min(top, start)
    if len(form["lines"]) > room:
        keys = [("↑↓", "scroll"), ("pgup pgdn", "page"), ("enter", "continue")]
        top, room = _draw_form(form, top=top, keys=keys)
    ui._raw("\x1b[?25l")
    try:
        while True:
            pressed = ui.read_key()
            step = {"up": -1, "k": -1, "down": 1, "j": 1, "pgup": -room, "pgdn": room, "home": -len(form["lines"]),
                    "end": len(form["lines"])}.get(pressed)
            if step is None or len(form["lines"]) <= room:
                return
            top, room = _draw_form(form, top=top + step, keys=keys)
    finally:
        ui._raw("\x1b[?25h")


def _screen_choose(title: str, options: dict[str, str], glyph: str, hints: dict[str, str] | None,
                   icons: dict[str, str] | None, subtitle: str) -> str:
    """Arrow-key menu on its own page. Short notices from the last action carry over; longer
    output is shown in the action's frame first so the redraw never wipes something unread."""
    global _INPUT_CLOSED
    pending = _pending()
    notices = [line for line in pending if ui.strip(line).strip()]
    try:
        if len(notices) > 2:
            _form_view(pending)
            notices = []
    except (EOFError, KeyboardInterrupt):
        _INPUT_CLOSED = True
        return "q"
    finally:
        _end_form()
    keys = [k for k in options if k != "q"]
    cursor = min(_CURSOR.get(title, 0), len(keys) - 1)
    numbered = [k for k in keys if k.isdigit()]
    jump = f"{numbered[0]}-{numbered[-1]}" if len(numbered) > 1 else "/".join(keys)
    back = options.get("q", "back").lower()
    while True:
        _draw_head({"section": title, "glyph": glyph, "blurb": _BLURBS.get(title, "")})
        print(ui.frame("", ui.menu_rows(options, cursor, icons=icons, hints=hints), subtitle=subtitle))
        for line in notices:
            print("  " + line.strip())
        print()
        print(ui.footer([("↑↓", "navigate"), ("enter", "select"), (jump, "jump"), ("q", back)]))
        sys.stdout.flush()
        ui.answered()
        ui._raw("\x1b[?25l")
        try:
            pressed = ui.read_key()
        except (EOFError, KeyboardInterrupt):
            _INPUT_CLOSED = True
            return "q"
        finally:
            ui._raw("\x1b[?25h")
        if pressed in ("up", "k", "shift-tab"):
            cursor = (cursor - 1) % len(keys)
        elif pressed in ("down", "j", "\t"):
            cursor = (cursor + 1) % len(keys)
        elif pressed in ("home", "pgup"):
            cursor = 0
        elif pressed in ("end", "pgdn"):
            cursor = len(keys) - 1
        elif pressed in ("enter", "right") or pressed.lower() in keys:
            choice = keys[cursor] if pressed in ("enter", "right") else pressed.lower()
            _CURSOR[title] = keys.index(choice)
            page(options[choice], (icons or {}).get(choice, glyph))
            return choice
        elif pressed in ("esc", "backspace", "left") or pressed.lower() in _BACK_WORDS:
            return "q"
        notices = []


def _cancellable(menu: Any) -> Any:
    """Esc at any question inside *menu* abandons that action and redraws the menu."""
    @functools.wraps(menu)
    def run(*args: Any, **kwargs: Any) -> Any:
        while True:
            try:
                return menu(*args, **kwargs)
            except ui.Cancelled:
                if _INPUT_CLOSED:
                    return None
                print(ui.info("Cancelled; back to the menu."))
    return run


def choose(prompt: str, options: dict[str, str], *, title: str | None = None, glyph: str = "arrow",
           hints: dict[str, str] | None = None, icons: dict[str, str] | None = None,
           subtitle: str = "") -> str:
    """Draw a framed menu and keep asking until a listed key (or a back word) is typed."""
    if _INPUT_CLOSED:
        return "q"
    if ui.FULLSCREEN:
        return _screen_choose(title or prompt.rstrip(": "), options, glyph, hints, icons, subtitle)
    print(ui.menu(title or prompt.rstrip(": "), options, glyph=glyph, hints=hints,
                  icons=icons, subtitle=subtitle))
    keys = [k for k in options if k != "q"]
    numbered = [k for k in keys if k.isdigit()]
    span = f"{numbered[0]}-{numbered[-1]}" if len(numbered) == len(keys) > 1 else "/".join(keys)
    print(ui.keybar([(span, "choose"), ("q", options.get("q", "back").lower()),
                     ("Ctrl-C", "leave")]))
    while True:
        answer = ask(ui.prompt("Choose")).strip().lower()
        if answer in options:
            return answer
        if _INPUT_CLOSED or answer in _BACK_WORDS:
            return "q"
        if answer:
            print(ui.warn(f"{answer!r} is not on this menu. ") + ui.hint(
                "Type one of " + ", ".join(k for k in options if k != "q") + ", or q to go back."))


def confirm_exact(prompt: str, plan: dict[str, Any] | None = None) -> bool:
    """Require the literal phrase, not a y/yes, to authorize execution."""
    print(ui.info(prompt))
    while True:
        answer = ask(ui.prompt("Type EXECUTE to upload", options=["json"] if plan else [],
                               note="Enter cancels")).strip()
        if answer == "EXECUTE":
            return True
        if plan is not None and answer.lower() in ("j", "json"):
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            continue
        if answer.upper() == "EXECUTE":
            print(ui.warn("EXECUTE must be typed in capitals; nothing was uploaded."))
        return False


def _human_size(size: Any) -> str:
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "?"


_STATUS_LOOK = {
    "succeeded": ("ok", ui.GREEN), "uploaded": ("ok", ui.GREEN), "completed": ("ok", ui.GREEN),
    "skipped": ("skip", ui.GRAY), "failed": ("fail", ui.RED), "error": ("fail", ui.RED),
}


def _item_line(item: dict[str, Any]) -> list[str]:
    status = str(item.get("status") or "planned").lower()
    glyph, rgb = _STATUS_LOOK.get(status, ("plan", ui.VIOLET))
    mark = ui.icon(glyph)
    head = (ui.paint(mark, rgb, bold=True) + " " if mark else "") + ui.paint(
        str(item.get("filename") or item.get("source_name") or "file"), ui.WHITE, bold=True)
    meta = [ui.hint(_human_size(item.get("size_bytes"))), ui.hint(str(item.get("transport") or "")),
            ui.hint(f"collision: {item.get('collision')}") if item.get("collision") else ""]
    lines = [head + "  " + ui.paint(" · ", ui.DIM_GRAY).join(m for m in meta if m)]
    target = item.get("url") or item.get("remote_path")
    if target:
        lines.append("   " + ui.hint("→ ") + ui.value(str(target)))
    if item.get("error"):
        lines.extend(ui.wrap(str(item["error"]), 3, ui.error))
    for warning in item.get("warnings") or []:
        wrapped = ui.wrap(str(warning), 5)
        lines.append("   " + ui.warn(wrapped[0].strip()))
        lines.extend(ui.paint(row, ui.AMBER) for row in wrapped[1:])
    return lines


def show_plan(plan: dict[str, Any], plan_path: str) -> None:
    destination = plan.get("destination") or {}
    items = plan.get("items") or []
    failed = sum(1 for item in items if item.get("status") == "failed")
    lines = [ui.hint("Destination ") + ui.value(f"{destination.get('owner')}/{destination.get('repo')}")
             + ui.hint(" on ") + ui.value(str(destination.get("branch", "main"))), ""]
    for item in items:
        lines.extend(_item_line(item))
    subtitle = ui.chip(f"{len(items) - failed} ready", ui.VIOLET) + (
        ui.chip(f"{failed} blocked", ui.RED) if failed else "")
    print(ui.frame(ui.heading("plan", "Offline plan · nothing uploaded yet"), lines, subtitle=subtitle))
    print(ui.hint(f"  Offline plan saved: {os.path.basename(plan_path)} · deleted after this prompt"))


def show_result(result: dict[str, Any]) -> None:
    items = result.get("items") or []
    counts: dict[str, int] = {}
    lines: list[str] = []
    for item in items:
        status = str(item.get("status") or "").lower()
        counts[status] = counts.get(status, 0) + 1
        lines.extend(_item_line(item))
        output = str(item.get("output") or "").strip()
        if output and status == "succeeded":
            lines.extend("   " + ui.hint(row) for row in output.splitlines()[:4])
    for problem in result.get("errors") or []:
        lines.append(ui.error(str(problem)))
    done, bad = counts.get("succeeded", 0), counts.get("failed", 0)
    subtitle = ui.chip(f"{done} uploaded", ui.GREEN) + (ui.chip(f"{bad} failed", ui.RED) if bad else "") \
        + (ui.chip(f"{counts['skipped']} skipped", ui.GRAY) if counts.get("skipped") else "")
    print(ui.frame(ui.heading("upload", "Upload result"), lines or [ui.hint("No items were processed.")],
                   subtitle=subtitle))
    if bad:
        print(ui.info("Failed items stay in history: History → r retries only those."))
    if os.environ.get("GUPLOAD_MENU_JSON"):
        print(json.dumps(result, ensure_ascii=False, indent=2))


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
        print(ui.info("No inputs selected; cancelled."))
        return 0
    if names is not None and len(names) != len(inputs):
        print(ui.error(f"Expected {len(inputs)} custom names; got {len(names)}.")
              + ui.hint(" Give one name per file, comma-separated, or leave blank."))
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
                print(ui.error(f"Unknown preset: {preset}"), file=sys.stderr)
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
                print(ui.error(f"Unable to create offline plan: {exc}"), file=sys.stderr)
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
            show_plan(plan, plan_path)
        if code:
            return code
        if not output:
            print("Gupload returned no offline plan.", file=sys.stderr)
            return 1
        if not confirm_exact("Review the plan above. No upload has occurred.", _LAST_PLAN):
            print(ui.info("Cancelled; plan was not executed."))
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
        show_result(_LAST_RESULT)
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

@_cancellable
def _template_menu() -> None:
    while True:
        templates = _templates()
        key = choose("Select: ", {"a": "Apply template", "c": "Create", "v": "View", "d": "Delete", "q": "Back"},
                     title="Templates", glyph="template",
                     icons={"a": "bolt", "c": "plus", "v": "eye", "d": "trash"},
                     hints={"a": "reuse saved folder, preset and naming",
                            "c": "save settings you upload with often",
                            "v": f"{len(templates)} saved", "d": "asks you to type DELETE <name>"})
        if key == "q":
            return
        if key == "v":
            if not templates:
                print(ui.empty_state("No saved templates.", "c  Create one", title="Templates"))
            for name, value in templates.items():
                print(f"  {ui.key(name)}  {ui.hint(json.dumps(value, ensure_ascii=False, sort_keys=True))}")
            continue
        if key == "c":
            name = ask(ui.prompt("Template name", example="artist-covers")).strip()
            if not name:
                continue
            print(ui.info("Every setting is optional: Enter skips it. Explicit values override the preset."))
            path = ask(ui.prompt("Destination folder under uploads/", default="automatic")).strip()
            presets = sorted(gupload.get_presets(_config()))
            if presets:
                for row in ui.wrap("Presets: " + ", ".join(presets), 2):
                    print(ui.hint(row))
            preset = ask(ui.prompt("Preset", default="none")).strip()
            collision = ask(ui.prompt("When the file exists", options=["skip-identical", "rename", "update"],
                                      default="config")).strip()
            formats = ask(ui.prompt("Link formats", default="config", example="mdimage,literal")).strip()
            pattern = ask(ui.prompt("Filename pattern", default="unchanged", example="{category}-{stem}.{ext}")).strip()
            setting: dict[str, Any] = {}
            if path: setting["path"] = path
            if preset: setting["preset"] = preset
            if collision: setting["collision"] = collision
            if formats: setting["formats"] = [v.strip() for v in formats.split(",") if v.strip()]
            if pattern:
                try:
                    gupload._apply_name_pattern(pattern, "example.png", "Images")
                except ValueError as exc:
                    print(ui.error(f"Invalid filename pattern: {exc}"))
                    continue
                setting["name_pattern"] = pattern
            _update_templates(lambda current: current.__setitem__(name, setting))
            print(ui.ok(f"Saved template {name!r}."))
            continue
        if key == "d":
            name = ask(ui.prompt("Template to delete", options=list(templates))).strip()
            if ask(ui.prompt(f"Type DELETE {name} to confirm")) == f"DELETE {name}":
                _update_templates(lambda current: current.pop(name, None))
                print(ui.ok(f"Deleted template {name!r}."))
            else:
                print(ui.info("Nothing deleted."))
            continue
        if key == "a":
            name = ask(ui.prompt("Template name", options=list(templates))).strip()
            template = templates.get(name)
            if not template:
                print(ui.warn("Template not found.") + ui.hint(" v lists the saved names."))
                continue
            values = collect_upload_inputs()
            if not values:
                continue
            try:
                apply_template(template, values)
            except ValueError as exc:
                print(ui.error(f"Cannot apply template: {exc}"))


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
    print(ui.info("One file, folder or URL per line; drag files in from Finder. Enter on an empty line finishes."))
    values: list[str] = []
    while True:
        value = ask(ui.prompt(f"Input {len(values)+1}", default="done" if values else "")).strip()
        if not value:
            break
        values.append(expand_input(value))
    return values


_UPLOAD_OPTIONS = {"1": "Single file or folder", "2": "Several files", "3": "From a URL",
                   "4": "Whole folder", "5": "Choose files…", "6": "Finder selection",
                   "7": "Artist assets / audio", "q": "Back"}


@_cancellable
def upload_workflow() -> None:
    while True:
        key = choose("Select: ", _UPLOAD_OPTIONS, title="Upload", glyph="upload",
                     icons={"1": "file", "2": "queue", "3": "link", "4": "folder", "5": "search",
                            "6": "eye", "7": "artist"},
                     hints={"1": "type or drag a path", "2": "one per line, Enter to finish",
                            "3": "http(s) link, downloaded then uploaded", "4": "every file inside, recursively",
                            "5": "open the system file picker", "6": "whatever is selected in Finder",
                            "7": "cover.jpg / logo.png / artist.jpg, or audio"},
                     subtitle=ui.hint("you always review a plan first"))
        if key == "q": return
        if key == "1":
            value = expand_input(ask(ui.prompt("File or folder path", example="~/Pictures/cover.jpg")))
            if value and not (Path(value).is_file() or Path(value).is_dir()):
                print(ui.warn("Path is not a readable file or directory.")); continue
            values = [value] if value else []
        elif key == "2": values = collect_upload_inputs()
        elif key == "3":
            value = ask(ui.prompt("URL", example="https://example.com/image.png")).strip()
            values = [value] if urllib.parse.urlsplit(value).scheme in ("http", "https") else []
            if value and not values: print(ui.warn("Only http:// and https:// links can be fetched."))
        elif key == "4":
            folder = expand_input(ask(ui.prompt("Folder path")))
            if not folder or not Path(folder).is_dir(): print(ui.warn("Folder not found.")); continue
            values = sorted(str(p) for p in Path(folder).rglob("*") if p.is_file())
            print(ui.info(f"Selected {len(values)} files."))
        elif key == "5":
            values = gupload_platform.choose_files()
        elif key == "6":
            values = gupload_platform.finder_selection()
            if not values: print(ui.warn("No Finder selection was returned.") + ui.hint(" Select files in Finder first."))
        elif key == "7":
            artist_asset_workflow()
            continue
        else: continue
        values = expand_sources(values)
        if not values: print(ui.info("No files selected; cancelled.")); continue
        print(ui.ok(f"{len(values)} file{'s' if len(values) != 1 else ''} selected.")
              + ui.hint("  Press Enter at each question below to keep the automatic choice."))
        names_text = ask(ui.prompt("Custom filenames, comma-separated", default="automatic"))
        names = [n.strip() for n in names_text.split(",")] if names_text else None
        path = ask(ui.prompt("Folder under uploads/", default="automatic", example="artists/Name")).strip() or None
        presets = gupload.get_presets(_config())
        if presets:
            for row in ui.wrap("Presets: " + ", ".join(sorted(presets)), 2):
                print(ui.hint(row))
        preset = (ask(ui.prompt("Preset", default="none")).strip() or None) if presets else None
        _plan_and_execute(values, names=names, path=path, preset=preset)


def artist_asset_workflow() -> None:
    kind = choose("Artist files: ", {"1": "Artwork set", "2": "All audio", "q": "Back"},
                  title="Artist files", glyph="artist", icons={"1": "image", "2": "music"},
                  hints={"1": "cover.jpg, logo.png and artist.jpg", "2": "every audio file in the folder"})
    if kind == "q": return
    artist_dir = Path(expand_input(ask(ui.prompt("Artist folder", example="~/Music/Artist"))))
    if not artist_dir.is_dir():
        print(ui.warn("Artist folder not found."))
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
        print(ui.warn(f"No {label} found under {artist_dir}."))
        return
    print(ui.ok(f"Found {len(files)} {label} files:"))
    for path in files:
        print(f"    {ui.hint(path)}")
    _plan_and_execute(files)




def remote_browse() -> None:
    """Browse the configured remote tree only after this explicit user action."""
    folder: str | None = None
    while True:
        page("Remote", "cloud", "read-only view of the repository's uploads/ tree")
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
        query = ask(ui.prompt("Filter by artist or category", default="show all")).casefold().strip()
        visible = [item for item in items
                   if not query or query in str(item.get("path", "")).casefold()
                   or query in str(item.get("name", "")).casefold()]
        folders = [item for item in visible if item.get("type") == "dir"]
        width = len(str(len(visible)))
        rows = []
        for index, item in enumerate(visible, 1):
            is_dir = item.get("type") == "dir"
            mark = ui.icon("folder" if is_dir else "file")
            name = str(item.get("name"))
            rows.append(f"{ui.key(str(index).rjust(width))}  "
                        + (ui.paint(mark, ui.MAGENTA if is_dir else ui.GRAY) + " " if mark else "")
                        + (ui.paint(name + "/", ui.WHITE, bold=True) if is_dir else ui.paint(name, ui.WHITE))
                        + "  " + ui.hint(str(item.get("path"))))
        print(ui.frame(ui.heading("cloud", f"Remote · {folder or 'uploads'}"),
                       rows or [ui.hint("Nothing matches this filter.")],
                       subtitle=ui.hint(f"{len(folders)} folders · {len(visible) - len(folders)} files · read-only")))
        print(ui.keybar([("number", "open folder"), ("..", "up"), ("s", "new filter"), ("q", "back")]))
        action = ask(ui.prompt("Open")).strip()
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
            print(ui.warn("Pick a listed folder number, '..', 's', or q."))


def _history() -> list[dict[str, Any]]:
    records = gupload.read_history()
    if not isinstance(records, list):
        raise ValueError("History state must be a JSON list.")
    return records


def _record_name(record: dict[str, Any]) -> str:
    return str(record.get("filename", record.get("source_name", "file")))


@_cancellable
def history_menu() -> None:
    while True:
        records = _history()
        failed_count = sum(1 for r in records if str(r.get("status", "")).lower() in {"failed", "error"} or r.get("error"))
        key = choose("Select: ", {"v": "View / search", "c": "Copy a URL", "e": "Export JSON or CSV",
                                  "m": "Markdown gallery", "h": "HTML gallery", "r": "Retry failed",
                                  "p": "Repeat last upload", "q": "Back"},
                     title="History", glyph="history",
                     icons={"v": "search", "c": "copy", "e": "export", "m": "file", "h": "image",
                            "r": "retry", "p": "bolt"},
                     hints={"v": "filter by name, path or status", "c": "puts a link on the clipboard",
                            "e": "every record to a file", "m": "list of links", "h": "image grid page",
                            "r": f"{failed_count} failed" if failed_count else "nothing failed",
                            "p": _record_name(records[-1]) if records else "no uploads yet"},
                     subtitle=ui.hint(f"{len(records)} records"))
        if key == "q": return
        if not records and key != "p":
            print(ui.empty_state("No uploads recorded yet.", "Main menu → 1 Upload", title="History"))
            continue
        query = ""
        rows = records
        if key == "v":
            query = ask(ui.prompt("Search", default="show all")).casefold()
            rows = [r for r in records if query in json.dumps(r, ensure_ascii=False).casefold()]
            for i, record in enumerate(rows, 1):
                status = str(record.get("status", "")).lower()
                look = ui.error if status in {"failed", "error"} or record.get("error") else ui.ok
                print(f"  {ui.key(str(i).rjust(3))}  " + look(ui.paint(_record_name(record), ui.WHITE))
                      + "  " + ui.hint(str(record.get("url") or record.get("error") or "")))
            if not rows:
                print(ui.info("No records match that search."))
        elif key == "c":
            for i, record in enumerate(records, 1):
                print(f"  {ui.key(str(i).rjust(3))}  {ui.paint(_record_name(record), ui.WHITE)}  {ui.hint(str(record.get('url', '')))}")
            try: index = int(ask(ui.prompt("Number to copy", default=str(len(records))) ) or len(records)) - 1
            except ValueError: continue
            if 0 <= index < len(records):
                url = str(records[index].get("url", ""))
                if url and gupload_platform.clipboard_set(url): print(ui.ok(f"Copied {url}"))
                elif url: print(ui.warn("Clipboard is unavailable; URL: ") + ui.value(url))
        elif key == "e":
            fmt = ask(ui.prompt("Format", options=["json", "csv"], default="json")).strip().lower() or "json"
            target = ask(ui.prompt("Output file", example=f"~/Desktop/gupload-history.{fmt}"))
            if not target.strip(): print(ui.info("No file given; nothing exported.")); continue
            destination = Path(expand_input(target))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "json": destination.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            elif fmt == "csv":
                import csv
                keys = sorted({k for row in records for k in row})
                with destination.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=keys); writer.writeheader(); writer.writerows(records)
            else: print(ui.warn("Choose json or csv.")); continue
            print(ui.ok(f"Exported {len(records)} records to {destination}"))
        elif key in ("m", "h"):
            suffix = "md" if key == "m" else "html"
            target = ask(ui.prompt("Gallery output file", example=f"~/Desktop/gupload-gallery.{suffix}"))
            if not target.strip(): print(ui.info("No file given; nothing written.")); continue
            destination = Path(expand_input(target))
            if key == "m":
                content = "\n".join(f"- [{r.get('filename', r.get('source_name','file'))}]({r.get('url','')})" for r in records) + "\n"
            else:
                content = "<!doctype html><meta charset='utf-8'><title>Gupload gallery</title><main>" + "".join(
                    f"<figure><a href='{html.escape(str(r.get('url','')), quote=True)}'><img loading='lazy' src='{html.escape(str(r.get('url','')), quote=True)}' alt='{html.escape(str(r.get('filename','file')), quote=True)}'></a><figcaption>{html.escape(str(r.get('filename','file')))}</figcaption></figure>"
                    for r in records) + "</main>"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            print(ui.ok(f"Gallery written to {destination}"))
        elif key == "r":
            if not failed_count:
                print(ui.ok("No failed history items."))
                continue
            _plan_and_execute([], retry_failed=True)
        elif key == "p":
            last = records[-1] if records else None
            src = last and (last.get("source") or last.get("source_path") or last.get("filepath")
                            or last.get("file_path") or last.get("path"))
            if src: _plan_and_execute([str(src)])
            else: print(ui.info("No previous upload source is available."))


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


@_cancellable
def favorites_menu() -> None:
    while True:
        favorites = _favorites()
        key = choose("Select: ", {"v": "View", "a": "Add file or URL", "u": "Upload a favorite", "d": "Remove", "q": "Back"},
                     title="Favorites", glyph="star", icons={"v": "eye", "a": "plus", "u": "upload", "d": "trash"},
                     hints={"v": f"{len(favorites)} saved", "a": "keep a path you upload again and again",
                            "u": "plan + review, like any upload", "d": "forget one (the file stays)"})
        if key == "q": return
        if not favorites and key != "a":
            print(ui.empty_state("No favorites saved.", "a  Add file or URL", title="Favorites"))
            continue
        if key in ("v", "u", "d"):
            for i, item in enumerate(favorites, 1):
                print(f"  {ui.key(str(i).rjust(3))}  {ui.paint(_favorite_path(item), ui.WHITE)}")
        if key == "a":
            value = expand_input(ask(ui.prompt("File path or URL")))
            if value:
                _update_favorites(lambda current: current.append(value) if value not in
                                  [_favorite_path(item) for item in current] else None)
                print(ui.ok(f"Added {value}"))
        elif key in ("u", "d"):
            try: index = int(ask(ui.prompt("Favorite number"))) - 1
            except ValueError: continue
            if not 0 <= index < len(favorites): continue
            if key == "u": _plan_and_execute([_favorite_path(favorites[index])])
            else:
                item = favorites[index]
                _update_favorites(lambda current: current.remove(item) if item in current else None)
                print(ui.ok(f"Removed {_favorite_path(item)}"))

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


@_cancellable
def queue_menu() -> None:
    while True:
        queue = _queue()
        counts = {state: sum(1 for item in queue if item.get("status", "pending") == state)
                  for state in ("pending", "failed", "completed")}
        key = choose("Select: ", {"a": "Add inputs", "v": "View", "r": "Remove one", "p": "Process pending",
                                  "f": "Retry failed", "c": "Clear queue", "q": "Back"},
                     title="Queue", glyph="queue",
                     icons={"a": "plus", "v": "eye", "r": "trash", "p": "upload", "f": "retry", "c": "trash"},
                     hints={"a": "collect now, upload later", "v": f"{len(queue)} items",
                            "p": f"{counts['pending']} pending", "f": f"{counts['failed']} failed",
                            "c": "asks you to type CLEAR QUEUE"},
                     subtitle=ui.hint(f"{counts['pending']} pending · {counts['failed']} failed · {counts['completed']} done"))
        if key == "q": return
        if not queue and key not in ("a",):
            print(ui.empty_state("The queue is empty.", "a  Add inputs, or start the clipboard monitor", title="Queue"))
            continue
        if key == "a":
            additions = [{"id": uuid.uuid4().hex, "source": value, "status": "pending"}
                         for value in collect_upload_inputs() if value]
            if additions:
                _update_queue(lambda current: current.extend(additions))
                print(ui.ok(f"Queued {len(additions)} input{'s' if len(additions) != 1 else ''}."))
        if key in ("v", "r"):
            for i, item in enumerate(queue, 1):
                status = item.get("status", "pending")
                look = {"failed": ui.error, "completed": ui.ok}.get(status, lambda t: ui._status("dot", ui.VIOLET, t))
                print(f"  {ui.key(str(i).rjust(3))}  " + look(ui.paint(str(item.get("source")), ui.WHITE)) + "  " + ui.hint(status))
        if key == "r":
            try: index = int(ask(ui.prompt("Queue number to remove"))) - 1
            except ValueError: continue
            if 0 <= index < len(queue):
                ident = queue[index]["id"]
                _update_queue(lambda current: current.__setitem__(
                    slice(None), [item for item in current if item.get("id") != ident]))
        elif key == "c":
            if ask(ui.prompt("Type CLEAR QUEUE to confirm")) == "CLEAR QUEUE":
                _update_queue(lambda current: current.clear())
                print(ui.ok("Queue cleared."))
            else:
                print(ui.info("Queue left as it was."))
        elif key in ("p", "f"):
            eligible = ("pending",) if key == "p" else ("failed",)
            selected = [item for item in queue if item.get("status", "pending") in eligible]
            sources = [str(item["source"]) for item in selected if item.get("source")]
            if not sources: print(ui.info("No eligible queue items.")); continue
            ids = {item["id"] for item in selected}
            _plan_and_execute(sources)

            def account(current: list[dict[str, Any]]) -> None:
                queue_results(current, sources, _LAST_RESULT, eligible, ids)
            _update_queue(account)


def clipboard_monitor() -> None:
    """Opt-in clipboard watcher. Candidates are queued, never auto-uploaded."""
    print(ui.frame(ui.heading("clipboard", "Clipboard monitor"), [
        ui.paint("Copied file paths and links are added to the queue as you copy them.", ui.WHITE),
        ui.hint("Nothing uploads by itself: process the queue later, review the plan, type EXECUTE."),
        ui.hint("Ctrl-C stops watching."),
    ]))
    if not gupload_platform.clipboard_available():
        print(ui.error("Clipboard monitoring is unavailable: no compatible clipboard utility was found."), file=sys.stderr)
        return
    if ask(ui.prompt("Type MONITOR to start", note="Enter goes back")) != "MONITOR": return
    print(ui.ok("Watching the clipboard…"))
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
                    print(ui.ok("Queued ") + ui.value(candidate))
            time.sleep(1)
    except (KeyboardInterrupt, EOFError):
        print("\n" + ui.info("Clipboard monitor stopped."))


def configure() -> None:
    path = gupload_state.config_path() / "config.json"
    cfg = gupload_state.read_json(path, {})
    shown = _redact(cfg) if isinstance(cfg, dict) else {}
    width = max((len(str(k)) for k in shown), default=0)
    print(ui.frame(ui.heading("cog", "Configure"),
                   [f"{ui.key(str(k).ljust(width))}  {ui.value(json.dumps(v, ensure_ascii=False))}" for k, v in sorted(shown.items())]
                   or [ui.hint("config.json is empty.")], subtitle=ui.hint(str(path))))
    print(ui.info('Values are JSON: strings in quotes ("main"), numbers bare (95), true/false.'))
    key = ask(ui.prompt("Key to change", note="Enter goes back")).strip()
    if not key: return
    current = shown.get(key)
    raw = ask(ui.prompt(f"New value for {key}", default=json.dumps(current, ensure_ascii=False) if key in shown and current != "[REDACTED]" else ""))
    if not raw.strip(): print(ui.info("Unchanged.")); return
    try: value = json.loads(raw)
    except json.JSONDecodeError: print(ui.warn("Value must be valid JSON.") + ui.hint(' Wrap text in quotes, e.g. "main".')); return

    def mutate(current: Any) -> dict[str, Any]:
        if not isinstance(current, dict):
            raise ValueError("Gupload config must be a JSON object.")
        current[key] = value
        return current
    gupload_state.update_json(path, {}, mutate)
    print(ui.ok(f"Saved {key}."))


@_cancellable
def logs_stats_help() -> None:
    while True:
        key = choose("Select: ", {"l": "View log", "s": "Stats", "c": "Config summary", "h": "How the menu works", "q": "Back"},
                     title="Logs, stats & help", glyph="help",
                     icons={"l": "log", "s": "chart", "c": "cog", "h": "help"},
                     hints={"l": "last 20 KB, secrets redacted", "s": "uploads so far",
                            "c": "current settings, secrets redacted", "h": "plan, review, EXECUTE"})
        if key == "q": return
        if key == "l":
            log_path = Path(os.environ.get("GUPLOAD_LOG", "/tmp/gupload.log"))
            if log_path.exists():
                print(_redact_log(log_path.read_text(encoding="utf-8", errors="replace")[-20000:]))
            else: print(ui.info(f"No log file at {log_path}"))
        elif key == "s":
            records = _history(); failed = sum(1 for x in records if x.get("error") or x.get("status") in ("failed", "error"))
            print(ui.frame(ui.heading("chart", "Stats"), [
                f"{ui.hint('History  ')}{ui.value(str(len(records)))} records",
                f"{ui.hint('Uploaded ')}{ui.paint(str(len(records) - failed), ui.GREEN, bold=True)}",
                f"{ui.hint('Failed   ')}{ui.paint(str(failed), ui.RED if failed else ui.GRAY, bold=True)}",
            ]))
        elif key == "c":
            print(json.dumps(_redact(_config()), ensure_ascii=False, indent=2, sort_keys=True))
        elif key == "h":
            print(ui.frame(ui.heading("help", "How the menu works"), [
                ui.paint("1  Pick what to upload. 2  gupload builds an offline plan: destination, names,", ui.WHITE),
                ui.paint("   collisions and warnings. 3  Nothing is sent until you type EXECUTE.", ui.WHITE),
                "",
                f"{ui.key('↑↓ j k')}   {ui.hint('move through a menu; Enter picks the highlighted row')}",
                f"{ui.key('1-9 a-z')}  {ui.hint('jump straight to that row')}",
                f"{ui.key('q')}        {ui.hint('back out of any menu (b, esc and backspace work too)')}",
                f"{ui.key('Enter')}    {ui.hint('at a question, an empty answer takes the [default] shown')}",
                f"{ui.key('Esc')}      {ui.hint('at a question, drops the action and returns to its menu')}",
                f"{ui.key('↑↓ PgUp')}  {ui.hint('at a question, scroll what the page printed above it')}",
                f"{ui.key('json')}     {ui.hint('at the EXECUTE prompt, prints the full plan')}",
                f"{ui.key('Ctrl-C')}   {ui.hint('leave gupload')}",
                "",
                ui.hint("Remote browsing is read-only and only runs when you choose it."),
                ui.hint("NO_COLOR or GUPLOAD_PLAIN=1: no colour.  GUPLOAD_ICONS=nerd|unicode|ascii: icon set."),
                ui.hint("GUPLOAD_FULLSCREEN=0: scroll in the terminal instead of taking over the page."),
            ]))


_MAIN_OPTIONS = {"1": "Upload", "2": "Browse remote", "3": "History", "4": "Favorites", "5": "Queue",
                 "6": "Templates", "7": "Clipboard monitor", "8": "Configure", "9": "Logs, stats & help",
                 "q": "Quit"}


def _destination_line() -> str:
    try:
        cfg = _config()
    except (OSError, ValueError):
        return ui.warn("config.json could not be read") + ui.hint("  8 Configure fixes it")
    if not cfg.get("owner") or not cfg.get("repo"):
        return ui.warn("No destination repository set") + ui.hint("  8 Configure → owner, repo")
    return (ui.hint("→ ") + ui.value(f"{cfg['owner']}/{cfg['repo']}") + ui.hint(" on ")
            + ui.value(str(cfg.get("branch", "main"))))


def _main_hints() -> dict[str, str]:
    hints = {"1": "files, folders, URLs, Finder, artist assets", "2": "look around the repository, read-only",
             "3": "search, copy links, export, galleries, retry", "4": "paths you upload often",
             "5": "collect now, upload later", "6": "saved folder + preset + naming",
             "7": "queue whatever you copy (opt-in)", "8": "owner, repo, branch, defaults",
             "9": "log, stats, how plans work"}
    try:
        pending = sum(1 for item in _queue() if item.get("status", "pending") == "pending")
        if pending: hints["5"] = f"{pending} pending, ready to process"
        count = len(_history())
        hints["3"] += f" · {count} record{'s' if count != 1 else ''}"
    except (OSError, ValueError):
        pass
    return hints


def main(argv: list[str] | None = None) -> int:
    if argv not in (None, [], ["--menu"]):
        return 2
    if ui.fullscreen_supported():
        ui.enter_fullscreen()
    try:
        return _main_loop()
    finally:
        ui.leave_fullscreen()


def _main_loop() -> int:
    if not ui.FULLSCREEN:
        print(ui.banner("offline-first uploader for GitHub"))
    while True:
        if not ui.FULLSCREEN:
            print()
        key = choose("Select: ", _MAIN_OPTIONS, title="Dashboard", glyph="upload",
                     icons={"1": "upload", "2": "cloud", "3": "history", "4": "star", "5": "queue",
                            "6": "template", "7": "clipboard", "8": "cog", "9": "help"},
                     hints=_main_hints(), subtitle=_destination_line())
        if key == "q": return 0
        try:
            if key == "1": upload_workflow()
            elif key == "2": remote_browse()
            elif key == "3": history_menu()
            elif key == "4": favorites_menu()
            elif key == "5": queue_menu()
            elif key == "6": _template_menu()
            elif key == "7": clipboard_monitor()
            elif key == "8": configure()
            elif key == "9": logs_stats_help()
        except ui.Cancelled:
            if not _INPUT_CLOSED:
                print(ui.info("Cancelled; back to the menu."))


if __name__ == "__main__":
    raise SystemExit(main())
