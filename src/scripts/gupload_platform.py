#!/usr/bin/env python3
"""Portable platform adapters and the explicit publish dialog for gupload."""
from __future__ import annotations

import contextlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Optional, Sequence


def normalize_inputs(values: Sequence[str]) -> list[str]:
    """Decode file URLs and make local inputs absolute; allow HTTP(S) URLs only."""
    normalized: list[str] = []
    for value in values:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme == "file":
            if parsed.netloc not in ("", "localhost"):
                raise ValueError(f"Unsupported file URL host: {parsed.netloc}")
            value = urllib.parse.unquote(parsed.path)
            normalized.append(os.path.abspath(os.path.expanduser(value)))
        elif parsed.scheme:
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Unsupported input URL: {value}")
            normalized.append(value)
        else:
            normalized.append(os.path.abspath(os.path.expanduser(value)))
    return normalized


def _linux_gui_session() -> bool:
    return platform.system() == "Linux" and bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )

def clipboard_available() -> bool:
    """Report whether this platform has a recognized clipboard utility."""
    names = {
        "Darwin": ("pbpaste", "pbcopy"),
        "Linux": ("wl-paste", "wl-copy", "xclip", "xsel",
                  "termux-clipboard-get", "termux-clipboard-set"),
    }.get(platform.system(), ())
    return any(shutil.which(name) for name in names)



def clipboard_get() -> Optional[str]:
    """Read the system clipboard through the native utility when available."""
    commands = {
        "Darwin": (("pbpaste", []),),
        "Linux": (("wl-paste", ["--no-newline"]), ("xclip", ["-selection", "clipboard", "-o"]),
                  ("xsel", ["--clipboard", "--output"]), ("termux-clipboard-get", [])),
    }
    for name, args in commands.get(platform.system(), ()):
        command = shutil.which(name)
        if command:
            result = _run([command, *args])
            if result.returncode == 0:
                return result.stdout
    return None


def launcher_main(argv: Optional[Sequence[str]] = None) -> int:
    """Portable launcher entry: preserve arguments/stdout and support stdin."""
    values = list(argv or [])
    if not values and not sys.stdin.isatty():
        values = [line.rstrip("\r\n") for line in sys.stdin if line.rstrip("\r\n")]
    # Core parses flags before normalizing only positional sources.
    core = _core_module()
    if not values:
        if platform.system() == "Linux" and not _linux_gui_session():
            return int(core.main(["--menu"]) or 0)
        return int(core.main(["--dialog"]) or 0)
    return int(core.main(values) or 0)


def _run(
    command: Sequence[str], *, input_text: Optional[str] = None,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, input=input_text, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=timeout,
    )


def _osascript(script: str, *args: str) -> Optional[str]:
    """Run fixed AppleScript with user values passed as argv, never interpolated."""
    executable = shutil.which("osascript") or (
        "/usr/bin/osascript" if Path("/usr/bin/osascript").exists() else None
    )
    if not executable:
        raise RuntimeError("macOS osascript is unavailable.")
    try:
        result = _run([executable, "-e", script, *args], timeout=3600)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("macOS dialog timed out after 3600 seconds.") from exc
    if result.returncode:
        detail = result.stderr.strip() or f"osascript exited with status {result.returncode}"
        raise RuntimeError(f"macOS dialog failed: {detail}")
    return result.stdout.rstrip("\n")


def _mac_choose_files() -> list[str]:
    result = _osascript('''on run argv
try
 set chosen to choose file with prompt "Choose files to plan with gupload" with multiple selections allowed
 set oldDelims to AppleScript's text item delimiters
 set AppleScript's text item delimiters to linefeed
 set resultText to ""
 repeat with f in chosen
  if resultText is not "" then set resultText to resultText & linefeed
  set resultText to resultText & POSIX path of f
 end repeat
 set AppleScript's text item delimiters to oldDelims
 return resultText
on error number -128
 return ""
end try
end run''')
    return result.splitlines() if result else []


def choose_files() -> list[str]:
    """Open a native file chooser where available; fall back to terminal input."""
    system = platform.system()
    if system == "Darwin":
        return _mac_choose_files()
    if system == "Linux":
        if _linux_gui_session() and shutil.which("zenity"):
            r = _run(["zenity", "--file-selection", "--multiple", "--separator=\n", "--title=Choose files for gupload"])
            return r.stdout.rstrip("\n").splitlines() if r.returncode == 0 and r.stdout else []
        if _linux_gui_session() and shutil.which("kdialog"):
            r = _run(["kdialog", "--getopenfilename", ".", "*", "--multiple", "--separate-output"])
            return r.stdout.rstrip("\n").splitlines() if r.returncode == 0 and r.stdout else []
    if sys.stdin.isatty():
        print("Enter file paths (one per line); blank line finishes:")
        result = []
        while True:
            try:
                value = input("Files> ").strip()
            except EOFError:
                break
            if not value:
                break
            result.append(value)
        return result
    return []


def finder_selection() -> list[str]:
    """Return selected Finder paths on macOS; other platforms have no Finder."""
    if platform.system() != "Darwin":
        return []
    result = _osascript('''tell application "Finder"
 set chosen to selection
 if chosen is {} then return ""
 set oldDelims to AppleScript's text item delimiters
 set AppleScript's text item delimiters to linefeed
 set resultText to ""
 repeat with f in chosen
  if resultText is not "" then set resultText to resultText & linefeed
  set resultText to resultText & POSIX path of (f as alias)
 end repeat
 set AppleScript's text item delimiters to oldDelims
 return resultText
end tell''')
    return result.splitlines() if result else []


def clipboard_set(text: str) -> bool:
    """Copy text using the platform clipboard command, returning success."""
    system = platform.system()
    if system == "Darwin":
        command = shutil.which("pbcopy") or ("/usr/bin/pbcopy" if Path("/usr/bin/pbcopy").exists() else None)
        if not command:
            return False
        return subprocess.run([command], input=text, text=True, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, check=False).returncode == 0
    if system == "Linux":
        for name, args in (("wl-copy", []), ("xclip", ["-selection", "clipboard"]),
                           ("xsel", ["--clipboard", "--input"]), ("termux-clipboard-set", [])):
            command = shutil.which(name)
            if command and subprocess.run([command, *args], input=text, text=True,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          check=False).returncode == 0:
                return True
    return False


def get_keychain_token() -> Optional[str]:
    """Read the optional macOS GuploadGitHubToken item without prompting."""
    if platform.system() != "Darwin":
        return None
    command = shutil.which("security") or ("/usr/bin/security" if Path("/usr/bin/security").exists() else None)
    if not command:
        return None
    result = _run([command, "find-generic-password", "-s", "GuploadGitHubToken", "-w"])
    token = result.stdout.strip()
    return token or None if result.returncode == 0 else None


def _dialog_text(title: str, prompt: str, default: str = "") -> Optional[str]:
    if platform.system() == "Darwin":
        return _osascript('''on run argv
try
 set answer to text returned of (display dialog (item 2 of argv) with title (item 1 of argv) default answer (item 3 of argv) buttons {"Cancel", "Continue"} default button "Continue")
 return answer
on error number -128
 return "__GUPLOAD_CANCEL__"
end try
end run''', title, prompt, default)
    if platform.system() == "Linux":
        if _linux_gui_session() and shutil.which("zenity"):
            r = _run(["zenity", "--entry", f"--title={title}", f"--text={prompt}", f"--entry-text={default}"])
            return r.stdout.rstrip("\n") if r.returncode == 0 else None
        if _linux_gui_session() and shutil.which("kdialog"):
            r = _run(["kdialog", "--title", title, "--inputbox", prompt, default])
            return r.stdout.rstrip("\n") if r.returncode == 0 else None
    if not sys.stdin.isatty():
        return None
    try:
        answer = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return None
    return answer or default


def _dialog_choice(title: str, prompt: str, choices: Sequence[str]) -> Optional[str]:
    if platform.system() == "Darwin":
        # The choice labels are provided in argv; AppleScript only handles structure.
        return _osascript('''on run argv
try
 set labels to items 3 thru -1 of argv
 set answer to choose from list labels with title (item 1 of argv) with prompt (item 2 of argv) OK button name "Continue" cancel button name "Cancel"
 if answer is false then return "__GUPLOAD_CANCEL__"
 return item 1 of answer
on error number -128
 return "__GUPLOAD_CANCEL__"
end try
end run''', title, prompt, *choices)
    if _linux_gui_session() and shutil.which("zenity"):
        r = _run(["zenity", "--list", f"--title={title}", f"--text={prompt}", "--column=Choice", *choices])
        return r.stdout.rstrip("\n") if r.returncode == 0 else None
    if _linux_gui_session() and shutil.which("kdialog"):
        r = _run(["kdialog", "--menu", prompt, *sum(([str(i), label] for i, label in enumerate(choices, 1)), [])])
        if r.returncode == 0 and r.stdout.strip().isdigit():
            return choices[int(r.stdout.strip()) - 1]
        return None
    if not sys.stdin.isatty():
        return None
    print(prompt)
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")
    try:
        answer = input(f"{title}> ").strip()
        return choices[int(answer) - 1] if answer.isdigit() and 1 <= int(answer) <= len(choices) else None
    except (EOFError, ValueError):
        return None


def _core_module():
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import gupload
    return gupload


def _invoke_core(core, argv: Sequence[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    status = 0
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = int(core.main(list(argv)) or 0)
    except SystemExit as exc:
        status = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 2)
    except Exception as exc:
        status = 2
        stderr.write(f"{type(exc).__name__}: {exc}\n")
    return status, stdout.getvalue(), stderr.getvalue()


def _decode_output(text: str) -> dict:
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("Gupload did not return a complete JSON plan.") from exc
    if not isinstance(value, dict):
        raise ValueError("Gupload returned a JSON value that is not a plan object.")
    return value


def _preset_names(core) -> list[str]:
    from gupload_state import config_path

    cfg_file = config_path() / "config.json"
    if not cfg_file.is_file():
        raise FileNotFoundError(f"Missing config: {cfg_file}")
    cfg = core.load_config()
    return list(core.get_presets(cfg))


def _show_failure(title: str, stdout: str, stderr: str, plan: Optional[dict] = None) -> None:
    parts = []
    if stderr.strip():
        parts.append(stderr.strip())
    if plan is not None:
        parts.append(json.dumps(plan, ensure_ascii=False, indent=2))
    elif stdout.strip():
        parts.append(stdout.strip())
    _show_message(title, "\n\n".join(parts) or "Gupload failed without diagnostic output.")


def _format_plan_summary(plan: dict, expected_account: Optional[str] = None, limit: int = 12) -> str:
    destination = plan.get("destination") or {}
    owner = destination.get("owner") or "(unknown owner)"
    repo = destination.get("repo") or "(unknown repo)"
    branch = destination.get("branch") or "main"
    lines = [
        "OFFLINE PLAN — no upload has occurred",
        f"Destination: {owner}/{repo}@{branch}",
    ]
    if expected_account:
        lines.append(f"Expected GitHub account: {expected_account}")

    items = plan.get("items") or []
    lines.append(f"Inputs: {len(items)}")
    for item in items[:limit]:
        source = item.get("source_name") or Path(item.get("source", "")).name or "(unknown source)"
        target = item.get("remote_path") or "(unresolved destination)"
        if item.get("transport") == "release":
            target = f"release asset {item.get('filename') or Path(target).name} (path: {target})"
        size = item.get("size_bytes")
        size_text = f", {size} bytes" if size is not None else ""
        lines.append(f"• {source} → {target}{size_text}")
        lines.append(f"  collision: {item.get('collision', 'skip-identical')}; status: {item.get('status', 'unknown')}")
        if item.get("transport") == "unresolved":
            lines.append("  URL item: download and final size/name remain unresolved until execution.")
        for warning in item.get("warnings", []):
            lines.append(f"  warning: {warning}")
    if len(items) > limit:
        lines.append(f"Showing first {limit} of {len(items)} inputs.")
        lines.append("Choose “Inspect full saved plan (JSON)” to review every remaining target before publishing.")
    for warning in plan.get("warnings", []):
        lines.append(f"Plan warning: {warning}")
    for error in plan.get("errors", []):
        lines.append(f"Plan error: {error}")
    lines.append("Choose Continue only after reviewing the destination and targets.")
    return "\n".join(lines)


def _open_plan_file(filename: Path) -> bool:
    if platform.system() == "Darwin":
        command = shutil.which("open") or "/usr/bin/open"
        return subprocess.run(
            [command, str(filename)], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False,
        ).returncode == 0
    if platform.system() == "Linux":
        command = shutil.which("xdg-open")
        if command:
            subprocess.Popen(
                [command, str(filename)], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        command = shutil.which("gio")
        if command:
            subprocess.Popen(
                [command, "open", str(filename)], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
    return False


def _review_saved_plan(plan: dict, plan_file: Path, expected_account: Optional[str]) -> bool:
    summary = _format_plan_summary(plan, expected_account)
    while True:
        choice = _dialog_choice(
            "Review gupload offline plan",
            summary,
            ["Cancel — do not upload", "Inspect full saved plan (JSON)", "Continue to publish confirmation"],
        )
        if choice != "Inspect full saved plan (JSON)":
            return choice == "Continue to publish confirmation"
        if not _open_plan_file(plan_file):
            if _show_message(
                "Full gupload plan (JSON)",
                plan_file.read_text(encoding="utf-8"),
            ) != "Continue":
                return False


def dialog_main(argv: Optional[Sequence[str]] = None) -> int:
    """Review and apply one saved offline plan; publication requires confirmation."""
    values = list(argv or [])
    separator = values.index("--") if "--" in values else -1
    source_values = values[separator + 1:] if separator >= 0 else values
    try:
        inputs = list(source_values)
        if not inputs:
            mode = _dialog_choice("Gupload", "Choose input type", ["Choose files", "Enter URL"])
            if mode is None or mode == "__GUPLOAD_CANCEL__":
                return 0
            if mode == "Choose files":
                inputs = choose_files()
            else:
                url = _dialog_text("Gupload", "Enter the file URL")
                if url is None or url == "__GUPLOAD_CANCEL__" or not url.strip():
                    return 0
                inputs = [url.strip()]
        if not inputs:
            return 0
        inputs = normalize_inputs(inputs)

        options = []
        if len(inputs) == 1:
            name = _dialog_text("Gupload", "Custom filename (leave blank for automatic name)")
            if name is None or name == "__GUPLOAD_CANCEL__":
                return 0
            if name.strip():
                options.append("--name=" + name.strip())

        core = _core_module()
        choices = ["Automatic routing", "Custom path"] + [
            "Preset: " + name for name in _preset_names(core)
        ]
        destination = _dialog_choice("Gupload destination", "Choose a destination", choices)
        if destination is None or destination == "__GUPLOAD_CANCEL__":
            return 0
        if destination == "Custom path":
            path = _dialog_text("Gupload destination", "Destination path under uploads/", "images/covers")
            if path is None or path == "__GUPLOAD_CANCEL__" or not path.strip():
                return 0
            options.append("--path=" + path.strip())
        elif destination.startswith("Preset: "):
            options.append("--preset=" + destination[len("Preset: "):])

        fmt = _dialog_choice("Gupload format", "Output format", ["Automatic", "mdlink", "mdimage", "literal", "html", "jsdelivr"])
        if fmt is None or fmt == "__GUPLOAD_CANCEL__":
            return 0
        if fmt != "Automatic":
            options.append("--format=" + fmt)

        collision = _dialog_choice("Gupload collision", "Existing-file policy", ["skip-identical", "rename", "update"])
        if collision is None or collision == "__GUPLOAD_CANCEL__":
            return 0
        options.append("--collision=" + collision)

        with tempfile.TemporaryDirectory(prefix="gupload-plan-") as directory:
            plan_file = Path(directory) / "reviewed-plan.json"
            plan_status, plan_stdout, plan_stderr = _invoke_core(
                core, [*options, "--save-plan", str(plan_file), "--json", "--", *inputs]
            )
            try:
                printed_plan = _decode_output(plan_stdout)
                with plan_file.open(encoding="utf-8") as stream:
                    plan = json.load(stream)
                if not isinstance(plan, dict) or printed_plan != plan:
                    raise ValueError("Saved plan differs from the plan shown by gupload.")
            except (OSError, ValueError, TypeError) as exc:
                _show_failure(
                    "Gupload plan failed", plan_stdout, plan_stderr,
                    {"errors": [str(exc)]},
                )
                return plan_status or 2

            failed_items = [
                item for item in plan.get("items", [])
                if item.get("status") == "failed" or item.get("error")
            ]
            if plan_status or plan.get("errors") or failed_items:
                _show_failure("Gupload plan failed", plan_stdout, plan_stderr, plan)
                return plan_status or 1

            destination = plan.get("destination", {})
            owner, repo = destination.get("owner"), destination.get("repo")
            if not isinstance(owner, str) or not owner or not isinstance(repo, str) or not repo:
                _show_failure(
                    "Gupload plan failed", plan_stdout, plan_stderr,
                    {"errors": ["Plan does not contain a valid repository destination."]},
                )
                return 2

            expected_account = core.load_config().get("expected_account")
            if not _review_saved_plan(plan, plan_file, expected_account):
                return 0
            publish = _dialog_choice(
                "Publish with gupload?",
                "This exact saved plan will be applied. Publishing requires this confirmation.",
                ["Cancel — do not upload", "Publish now"],
            )
            if publish != "Publish now":
                return 0

            execute_status, execute_stdout, execute_stderr = _invoke_core(
                core, [
                    "--apply-plan", str(plan_file), "--execute",
                    "--expect-repo", f"{owner}/{repo}", "--json",
                ]
            )
            if execute_stdout:
                sys.stdout.write(execute_stdout)
                sys.stdout.flush()
            if execute_stderr:
                sys.stderr.write(execute_stderr)
                sys.stderr.flush()
            if execute_status:
                try:
                    result = _decode_output(execute_stdout) if execute_stdout.strip() else None
                except ValueError:
                    result = None
                _show_failure("Gupload execution failed", execute_stdout, execute_stderr, result)
            return execute_status
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        print(f"gupload dialog: {exc}", file=sys.stderr)
        try:
            _show_message("Gupload dialog error", str(exc))
        except (OSError, RuntimeError, subprocess.SubprocessError) as display_exc:
            print(f"gupload dialog: native error display failed: {display_exc}", file=sys.stderr)
        return 2


def _show_message(title: str, message: str) -> Optional[str]:
    if platform.system() == "Darwin":
        return _osascript('''on run argv
try
 set response to display dialog (item 2 of argv) with title (item 1 of argv) buttons {"Cancel", "Continue"} default button "Continue" giving up after 3600
 if gave up of response then return "__GUPLOAD_CANCEL__"
 return button returned of response
on error number -128
 return "__GUPLOAD_CANCEL__"
end try
end run''', title, message)
    if _linux_gui_session() and shutil.which("zenity"):
        return "Continue" if _run(["zenity", "--info", f"--title={title}", f"--text={message}"]).returncode == 0 else None
    if _linux_gui_session() and shutil.which("kdialog"):
        return "Continue" if _run(["kdialog", "--msgbox", message, "--title", title]).returncode == 0 else None
    print(f"\n{title}\n{message}")
    return "Continue"
