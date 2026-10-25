"""Terminal styling for the gupload menu: one palette, one layout, stdlib only.

Roles (never mix them on a line): frame violet · icons magenta · headings bold white ·
keys bold magenta · labels white · hints gray · defaults violet · status green/amber/red only.

Colour switches off for NO_COLOR, GUPLOAD_PLAIN=1, TERM=dumb or a non-terminal stdout.
Icons follow GUPLOAD_ICONS=nerd|unicode|ascii (default nerd; unicode without colour; ascii off UTF-8).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata
from typing import Iterable

PURPLE = (176, 48, 240)     # #B030F0, the brand colour from the README
VIOLET = (157, 124, 255)    # #9D7CFF, frames and defaults
MAGENTA = (240, 80, 216)    # #F050D8, icons and hotkeys
LILAC = (214, 196, 255)     # #D6C4FF, values worth a second look
GRAY = (138, 136, 154)      # #8A889A, hints and secondary text
DIM_GRAY = (92, 90, 106)    # #5C5A6A, punctuation and separators
WHITE = (245, 243, 255)     # #F5F3FF, labels and headings
GREEN = (126, 224, 129)
AMBER = (255, 190, 92)
RED = (255, 99, 120)

MAX_WIDTH = 92

_NERD = {
    "upload": "\U000f0552", "cloud": "\U000f015f", "history": "\U000f02da", "star": "\U000f04ce",
    "queue": "\U000f0cb8", "template": "\U000f0219", "clipboard": "\U000f0147", "cog": "\U000f0493",
    "help": "\U000f02d7", "folder": "\U000f024b", "file": "\U000f0214", "link": "\U000f0337",
    "search": "\U000f0349", "image": "\U000f02e9", "music": "\U000f075a", "artist": "\U000f0004",
    "arrow": "\U000f0142", "back": "\U000f004d", "ok": "\U000f05e0", "fail": "\U000f0159",
    "warn": "\U000f0028", "info": "\U000f02fd", "skip": "\U000f073a", "plan": "\U000f014e",
    "lock": "\U000f033e", "trash": "\U000f0a79", "plus": "\U000f0415", "eye": "\U000f0208",
    "export": "\U000f0207", "copy": "\U000f018f", "retry": "\U000f0450", "bolt": "\U000f140b",
    "chart": "\U000f0128", "log": "\U000f0219", "quit": "\U000f0343", "dot": "\U000f0130",
}
_UNICODE = {
    "upload": "↑", "cloud": "☁", "history": "⟲", "star": "★", "queue": "≡", "template": "▤",
    "clipboard": "▣", "cog": "⚙", "help": "?", "folder": "▸", "file": "▤", "link": "↗",
    "search": "⌕", "image": "▣", "music": "♪", "artist": "☻", "arrow": "›", "back": "‹",
    "ok": "✓", "fail": "✗", "warn": "!", "info": "i", "skip": "⊘", "plan": "◇", "lock": "◆",
    "trash": "✕", "plus": "+", "eye": "◉", "export": "⇥", "copy": "⧉", "retry": "↻", "bolt": "ϟ",
    "chart": "▥", "log": "▤", "quit": "⏻", "dot": "•",
}
_ASCII = {**{name: "*" for name in _UNICODE}, "arrow": ">", "back": "<", "ok": "+", "fail": "x",
          "warn": "!", "info": "i", "skip": "-", "plus": "+", "help": "?", "dot": "."}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def color_enabled(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") or os.environ.get("GUPLOAD_PLAIN") in ("1", "true", "yes"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def icon(name: str) -> str:
    choice = os.environ.get("GUPLOAD_ICONS", "").lower()
    if choice not in ("nerd", "unicode", "ascii"):
        encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
        choice = ("nerd" if color_enabled() else "unicode") if "utf" in encoding else "ascii"
    return {"nerd": _NERD, "unicode": _UNICODE, "ascii": _ASCII}[choice].get(name, "")


def paint(text: str, rgb: tuple[int, int, int] | None = None, *, bold: bool = False,
          dim: bool = False, italic: bool = False) -> str:
    if not text or not color_enabled():
        return text
    codes = []
    if bold: codes.append("1")
    if dim: codes.append("2")
    if italic: codes.append("3")
    if rgb: codes.append("38;2;%d;%d;%d" % rgb)
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m" if codes else text


def strip(text: str) -> str:
    return _ANSI.sub("", text)


def visible_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else
               0 if unicodedata.combining(ch) else 1 for ch in strip(text))


def _width() -> int:
    if FULLSCREEN:
        return _layout()[0] - _inset
    return max(40, min(shutil.get_terminal_size((MAX_WIDTH, 24)).columns, MAX_WIDTH))


def _clip(text: str, limit: int) -> str:
    if visible_width(text) <= limit:
        return text
    plain = strip(text)
    while plain and visible_width(plain) > limit - 1:
        plain = plain[:-1]
    return plain + "…"


def key(text: str) -> str:
    return paint(text, MAGENTA, bold=True)


def hint(text: str) -> str:
    return paint(text, GRAY)


def value(text: str) -> str:
    return paint(text, LILAC)


def heading(glyph: str, text: str) -> str:
    mark = icon(glyph)
    return (paint(mark, MAGENTA) + " " if mark else "") + paint(text, WHITE, bold=True)


def frame(title: str, lines: Iterable[str], *, subtitle: str = "", border=VIOLET,
          width: int | None = None) -> str:
    """A rounded panel of the standard width: title on the top edge, subtitle on the bottom-right."""
    if FULLSCREEN and _inset and width is None:
        return section(title, lines, subtitle=subtitle, border=border)
    width = width or _width()
    inner = width - 4
    rounded = color_enabled() or "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()
    tl, tr, bl, br, h, v = ("╭", "╮", "╰", "╯", "─", "│") if rounded else ("+", "+", "+", "+", "-", "|")
    edge = lambda s: paint(s, border)
    title_text = f" {title} " if title else ""
    top = edge(tl + h) + title_text + edge(h * max(0, width - 3 - visible_width(title_text)) + tr)
    out = [top]
    for line in lines:
        line = _clip(line, inner)
        out.append(edge(v) + " " + line + " " * (inner - visible_width(line)) + " " + edge(v))
    sub = f" {subtitle} " if subtitle else ""
    out.append(edge(bl + h * max(0, width - 3 - visible_width(sub))) + sub + edge(h + br))
    return "\n".join(out)


def section(title: str, lines: Iterable[str], *, subtitle: str = "", border=VIOLET) -> str:
    """frame() as drawn inside an action page's own frame: a titled rule instead of a second box,
    and no title at all when it would only repeat the page's."""
    width = _width()
    out = []
    if title and strip(title).strip() != strip(heading(_page_glyph, _page_section)).strip():
        rest = width - 4 - visible_width(title)
        out += ["", paint("──", border) + " " + title + " " + paint("─" * max(0, rest), border)]
    out.extend(_clip(line, width) for line in lines)
    if subtitle:
        out.append(" " * max(0, width - visible_width(subtitle)) + subtitle)
    return "\n".join(out)


def wrap_styled(line: str, width: int) -> list[str]:
    """Word-wrap a line that may carry colour codes; continuation rows keep the colour in force
    and indent two past the line's own indent."""
    if visible_width(line) <= width:
        return [line]
    plain = strip(line)
    indent = " " * (len(plain) - len(plain.lstrip()) + 2)
    rows: list[str] = []
    current, used, active = "", 0, ""
    for word in line.split(" "):
        size = visible_width(word)
        if used and size and used + 1 + size > width:
            rows.append(current + ("\x1b[0m" if active else ""))
            current, used = indent + active, len(indent)
        elif current or used:
            current += " "
            used += 1
        current += word
        used += size
        for code in _ANSI.findall(word):
            active = "" if code == "\x1b[0m" else code
    rows.append(current)
    return rows


def menu(title: str, options: dict[str, str], *, glyph: str = "arrow",
         hints: dict[str, str] | None = None, icons: dict[str, str] | None = None,
         subtitle: str = "") -> str:
    """Key · icon · label · hint rows inside a frame. `q` is drawn last, apart from the rest."""
    hints, icons = hints or {}, icons or {}
    rows = [(k, v) for k, v in options.items() if k != "q"]
    labels = max((visible_width(v) for _, v in rows), default=0)
    keys = max((len(k) for k in options), default=1)
    lines = []
    for k, label in rows:
        mark = icon(icons.get(k, "dot"))
        cell = (paint(mark, VIOLET) + " ") if mark else ""
        note = hints.get(k, "")
        lines.append(f"{paint(k.rjust(keys), NUMBER, bold=True)}  {cell}{paint(label, WHITE)}"
                     + (" " * (labels - visible_width(label) + 2) + hint(note) if note else ""))
    if "q" in options:
        mark = icon("back") if options["q"].lower() == "back" else icon("quit")
        lines.append("")
        lines.append(f"{paint('q'.rjust(keys), NUMBER, bold=True)}  {paint(mark, GRAY) + ' ' if mark else ''}{hint(options['q'])}")
    return frame(heading(glyph, title), lines, subtitle=subtitle)


class Prompt(str):
    """The text handed to input(), plus its parts so a full-screen form can lay them out itself."""
    label = default = head = extra = ""


def prompt(label: str, *, options: Iterable[str] = (), default: str = "", example: str = "",
           note: str = "") -> Prompt:
    """`› Label (a/b) [default] e.g. … · note` — the text handed to input(). Long option lists collapse."""
    options = list(options)
    if len(options) > 5:
        options = options[:4] + [f"…+{len(options) - 4}"]
    head = [paint(label, WHITE, bold=True)]
    if options:
        head.append(paint("(", DIM_GRAY) + paint("/", DIM_GRAY).join(key(o) for o in options) + paint(")", DIM_GRAY))
    if default:
        head.append(paint("[", DIM_GRAY) + paint(default, VIOLET, bold=True) + paint("]", DIM_GRAY))
    extra = [hint(f"e.g. {example}")] if example else []
    if note:
        extra.append(hint(f"· {note}"))
    text = Prompt(paint(icon("arrow") or ">", MAGENTA, bold=True) + " " + " ".join(head + extra) + " ")
    text.label, text.default, text.head, text.extra = label, default, " ".join(head), " ".join(extra)
    return text


def wrap(text: str, indent: int = 0, style=None) -> list[str]:
    """Wrap plain *text* to the frame's inner width; *style* paints each wrapped row."""
    import textwrap
    rows = textwrap.wrap(text, max(20, _width() - 4 - indent)) or [""]
    return [" " * indent + (style(row) if style else row) for row in rows]


def keybar(entries: Iterable[tuple[str, str]]) -> str:
    """One quiet line of shortcuts: `1-9 choose · q back · Ctrl-C quit`."""
    sep = paint("  ·  ", DIM_GRAY)
    return "  " + sep.join(f"{key(k)} {hint(v)}" for k, v in entries)


def _status(glyph: str, rgb, text: str) -> str:
    mark = icon(glyph)
    return (paint(mark, rgb, bold=True) + " " if mark else "") + text


def ok(text: str) -> str:
    return _status("ok", GREEN, text)


def warn(text: str) -> str:
    return _status("warn", AMBER, text)


def error(text: str) -> str:
    return _status("fail", RED, text)


def info(text: str) -> str:
    return _status("info", VIOLET, hint(text))


def chip(label: str, rgb) -> str:
    return paint(f" {label} ", rgb, bold=True)


def empty_state(message: str, next_step: str, *, title: str = "Nothing here yet", glyph: str = "info") -> str:
    return frame(heading(glyph, title), [paint(message, WHITE),
                                         hint(f"{icon('arrow') or '>'} Next: ") + key(next_step)])


def banner(subtitle: str) -> str:
    word = "gupload"
    if color_enabled():
        ramp = [PURPLE, (190, 64, 236), (204, 72, 230), (218, 76, 226), (230, 78, 222), MAGENTA, MAGENTA]
        word = "".join(paint(ch, ramp[i % len(ramp)], bold=True) for i, ch in enumerate(word))
    mark = icon("upload")
    return f"\n  {paint(mark, MAGENTA) + ' ' if mark else ''}{word}  {hint(subtitle)}"


# ── Full-screen mode ────────────────────────────────────────────────────────────
# On a real terminal the menu owns the alternate screen (like a TUI): every menu
# redraws the page in place and the shell scrollback is left untouched on exit.
# GUPLOAD_FULLSCREEN=0 keeps the scrolling line-by-line menu.

WORDMARK = (
    " ██████╗ ██╗   ██╗██████╗ ██╗      ██████╗  █████╗ ██████╗ ",
    "██╔════╝ ██║   ██║██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗",
    "██║  ███╗██║   ██║██████╔╝██║     ██║   ██║███████║██║  ██║",
    "██║   ██║██║   ██║██╔═══╝ ██║     ██║   ██║██╔══██║██║  ██║",
    "╚██████╔╝╚██████╔╝██║     ███████╗╚██████╔╝██║  ██║██████╔╝",
    " ╚═════╝  ╚═════╝ ╚═╝     ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ",
)
NUMBER = (201, 182, 255)    # #C9B6FF, menu keys: light purple, so they never sit pink-on-pink beside an icon
SELECTED = (199, 125, 255)  # #C77DFF, the highlighted row's label
HERO_ROWS = 36              # terminals at least this tall get the big wordmark

FULLSCREEN = False
_margin = 0
_inset = 0                  # columns taken by the frame around an action page's content
_page_section, _page_glyph = "", ""


class Cancelled(Exception):
    """Esc at a full-screen question: abandon the action and return to its menu."""


class _Page:
    """stdout proxy for full-screen mode: centres every printed line and remembers what was
    printed since the last answer, so a short notice can carry onto the next screen and a
    long listing can wait for a key instead of being wiped by the redraw."""

    def __init__(self, real):
        self.real = real
        self.at_line_start = True
        self.since_answer: list[str] = []

    def write(self, text: str) -> int:
        out = []
        for piece in re.split(r"(\n)", text):
            if piece == "\n":
                out.append(piece)
                self.at_line_start = True
                continue
            if piece and self.at_line_start:
                out.append(" " * _margin)
                self.at_line_start = False
            out.append(piece)
        self.since_answer.append(text)
        return self.real.write("".join(out))

    def flush(self):
        self.real.flush()

    def fileno(self):
        return self.real.fileno()

    def isatty(self):
        return self.real.isatty()

    @property
    def encoding(self):
        return self.real.encoding


def fullscreen_supported() -> bool:
    if os.environ.get("GUPLOAD_FULLSCREEN", "").lower() in ("0", "false", "no", "off"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        import termios, tty  # noqa: F401  (POSIX terminals only)
    except ImportError:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def _raw(text: str) -> None:
    real = sys.stdout.real if isinstance(sys.stdout, _Page) else sys.stdout
    real.write(text)
    real.flush()


def enter_fullscreen() -> None:
    global FULLSCREEN
    if FULLSCREEN:
        return
    FULLSCREEN = True
    sys.stdout = _Page(sys.stdout)
    sys.stderr = sys.stdout  # engine diagnostics land on the page instead of scribbling over it
    _raw("\x1b[?1049h\x1b[H\x1b[2J")


def leave_fullscreen() -> None:
    global FULLSCREEN
    if not FULLSCREEN:
        return
    FULLSCREEN = False
    _raw("\x1b[?25h\x1b[?1049l")
    if isinstance(sys.stdout, _Page):
        sys.stdout = sys.stdout.real
        sys.stderr = sys.__stderr__


def answered() -> None:
    """Call after every input(): what was printed before it has been seen."""
    if isinstance(sys.stdout, _Page):
        sys.stdout.since_answer.clear()
        sys.stdout.at_line_start = True


def set_inset(columns: int, title: str = "", glyph: str = "") -> None:
    """Narrow frames and wrapping by *columns* while printing inside the frame of the action page
    *title*; frames printed meanwhile become sections of it."""
    global _inset, _page_section, _page_glyph
    _inset, _page_section, _page_glyph = columns, title, glyph


def margin() -> str:
    return " " * _margin


def _layout() -> tuple[int, int]:
    global _margin
    size = shutil.get_terminal_size((MAX_WIDTH, 30))
    width = max(40, min(size.columns - 2, MAX_WIDTH))
    _margin = max(0, (size.columns - width) // 2) if FULLSCREEN else 0
    return width, size.lines


def center(text: str, width: int | None = None) -> str:
    width = width or _width()
    gap = max(0, width - visible_width(text))
    return " " * (gap // 2) + text + " " * (gap - gap // 2)


def spaced(text: str) -> str:
    return " ".join(text.upper())


def _wordmark_row(row: str) -> str:
    if not color_enabled():
        return row
    out = []
    for i, ch in enumerate(row):
        if ch == "█":
            t = i / max(1, len(row) - 1)  # purple on the left easing towards magenta on the right
            rgb = tuple(int(a + (b - a) * t) for a, b in zip(PURPLE, MAGENTA))
            out.append(paint(ch, rgb))
        elif ch in "╔╗╚╝═║":
            out.append(paint(ch, DIM_GRAY))
        else:
            out.append(ch)
    return "".join(out)


def header(section: str, *, tab: str = "", glyph: str = "upload", tagline: str = "PLAN  •  REVIEW  •  UPLOAD") -> list[str]:
    """The page header: a frame with the destination tab on its top edge, the wordmark (or a
    one-line title on short terminals) and the section badge cut into its bottom edge."""
    width, rows = _layout()
    edge = lambda s: paint(s, VIOLET)
    inner = width - 2
    lines: list[str] = []
    if tab:
        tab_w = visible_width(tab) + 4
        left = (width - tab_w) // 2
        lines.append(" " * left + edge("╭" + "─" * (tab_w - 2) + "╮"))
        lines.append(edge("╭" + "─" * (left - 1) + "┤") + " " + paint(tab, LILAC) + " "
                     + edge("├" + "─" * (width - left - tab_w - 1) + "╮"))
        lines.append(edge("│") + " " * (left - 1) + edge("╰" + "─" * (tab_w - 2) + "╯")
                     + " " * (width - left - tab_w - 1) + edge("│"))
    else:
        lines.append(edge("╭" + "─" * inner + "╮"))
    if rows >= HERO_ROWS and width >= len(WORDMARK[0]) + 4:
        for row in WORDMARK:
            lines.append(edge("│") + center(_wordmark_row(row), inner) + edge("│"))
        lines.append(edge("│") + center(hint(tagline), inner) + edge("│"))
    else:
        title = (paint(icon("upload"), MAGENTA) + "  " if icon("upload") else "") \
            + paint("G U P L O A D", PURPLE, bold=True) + "   " + hint(tagline)
        lines.append(edge("│") + center(title, inner) + edge("│"))
    badge = spaced(section)
    mark = icon(glyph)
    badge_w = visible_width(badge) + 6
    left = (width - badge_w) // 2
    right = width - left - badge_w
    lines.append(edge("│") + " " * (left - 1) + edge("╭" + "─" * (badge_w - 2) + "╮") + " " * (right - 1) + edge("│"))
    lines.append(edge("╰" + "─" * (left - 1) + "┤") + "  " + paint(badge, MAGENTA, bold=True) + "  "
                 + edge("├" + "─" * (right - 1) + "╯"))
    under = "─" * (badge_w - 2)
    if mark:
        mid = (badge_w - 2) // 2
        under = edge(under[:mid - 1]) + " " + paint(mark, MAGENTA) + " " + edge(under[mid + 2:])
    else:
        under = edge(under)
    lines.append(" " * left + edge("╰") + under + edge("╯"))
    return lines


def footer(entries: Iterable[tuple[str, str]]) -> str:
    sep = paint("  •  ", DIM_GRAY)
    return center(sep.join(f"{key(k)} {hint(v)}" for k, v in entries))


def clear() -> None:
    _layout()
    _raw("\x1b[H\x1b[2J")
    if isinstance(sys.stdout, _Page):
        sys.stdout.at_line_start = True


_SEQUENCES = {"[A": "up", "OA": "up", "[B": "down", "OB": "down", "[C": "right", "OC": "right",
              "[D": "left", "OD": "left", "[H": "home", "OH": "home", "[1~": "home", "[F": "end",
              "OF": "end", "[4~": "end", "[3~": "delete", "[5~": "pgup", "[6~": "pgdn", "[Z": "shift-tab"}
_CONTROLS = {"\r": "enter", "\n": "enter", "\x7f": "backspace", "\b": "backspace", "\x01": "home",
             "\x05": "end", "\x15": "ctrl-u", "\x17": "ctrl-w", "\x04": "ctrl-d"}


def _read_token(fd: int) -> str:
    """One keypress from a terminal already in cbreak mode: a name from _SEQUENCES/_CONTROLS,
    'esc', or the typed character (UTF-8 decoded). Ctrl-C raises KeyboardInterrupt."""
    import select
    data = os.read(fd, 1)
    if not data:
        raise EOFError
    if data == b"\x1b":
        seq = b""
        while select.select([fd], [], [], 0.03)[0]:
            seq += os.read(fd, 1)
            if len(seq) >= 2 and (chr(seq[-1]).isalpha() or seq.endswith(b"~")):
                break
        return _SEQUENCES.get(seq.decode(errors="ignore"), "" if seq else "esc")
    if data[0] >= 0xC0:
        need = 1 if data[0] < 0xE0 else 2 if data[0] < 0xF0 else 3
        while need:
            more = os.read(fd, need)
            if not more:
                break
            data += more
            need -= len(more)
    ch = data.decode(errors="ignore")
    if ch == "\x03":
        raise KeyboardInterrupt
    return _CONTROLS.get(ch, ch)


def read_key() -> str:
    """One keypress in cbreak mode: 'up', 'down', 'enter', 'esc', 'backspace', … or the character.
    Ctrl-C raises KeyboardInterrupt and Ctrl-D EOFError."""
    import termios
    import tty
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        pressed = _read_token(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    if pressed == "ctrl-d":
        raise EOFError
    return pressed


def edit_line(render, scroll=None) -> str:
    """Read one line with a small editor: ←→ Home End, Backspace/Delete, Ctrl-U/Ctrl-W. Enter
    returns the text; Esc raises Cancelled; Ctrl-D on an empty line raises EOFError.
    render(text, cursor) redraws the input row; scroll(key) handles ↑↓ PgUp PgDn."""
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    buf: list[str] = []
    pos = 0
    try:
        tty.setcbreak(fd)
        _raw("\x1b[?25h")
        render("", 0)
        while True:
            pressed = _read_token(fd)
            if pressed == "enter":
                return "".join(buf)
            if pressed == "esc":
                raise Cancelled
            if pressed == "ctrl-d" and not buf:
                raise EOFError
            if pressed == "backspace" and pos:
                pos -= 1
                del buf[pos]
            elif pressed == "delete" and pos < len(buf):
                del buf[pos]
            elif pressed == "left":
                pos = max(0, pos - 1)
            elif pressed == "right":
                pos = min(len(buf), pos + 1)
            elif pressed == "home":
                pos = 0
            elif pressed == "end":
                pos = len(buf)
            elif pressed == "ctrl-u":
                del buf[:pos]
                pos = 0
            elif pressed == "ctrl-w":
                start = pos
                while start and buf[start - 1] == " ":
                    start -= 1
                while start and buf[start - 1] != " ":
                    start -= 1
                del buf[start:pos]
                pos = start
            elif pressed in ("up", "down", "pgup", "pgdn") and scroll:
                scroll(pressed)
            elif len(pressed) == 1 and pressed.isprintable():
                buf.insert(pos, pressed)
                pos += 1
            if not select.select([fd], [], [], 0)[0]:  # a paste arrives as many keys: draw once
                render("".join(buf), pos)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def input_row(text: str, cursor: int, *, placeholder: str = "", width: int) -> tuple[str, int]:
    """The framed input row of an action page and the column its cursor sits in. Text wider
    than the field scrolls sideways so the cursor stays visible."""
    edge = lambda s: paint(s, VIOLET)
    field = width - 6
    start = max(0, cursor - field + 1)
    shown = text[start:start + field]
    body = shown if text else hint(_clip(placeholder, field))
    row = (edge("│") + " " + paint("❯" if "utf" in (getattr(sys.stdout, "encoding", "") or "").lower() else ">",
                                    MAGENTA, bold=True)
           + " " + body + " " * max(0, field - visible_width(body)) + " " + edge("│"))
    return row, 4 + visible_width(text[start:cursor])


def menu_rows(options: dict[str, str], cursor: int, *, icons: dict[str, str] | None = None,
              hints: dict[str, str] | None = None) -> list[str]:
    """The list inside a full-screen menu: `❯` and a brighter label mark the highlighted row."""
    icons, hints = icons or {}, hints or {}
    keys = [k for k in options if k != "q"]  # q/esc live in the footer, not in the list
    labels = max((visible_width(options[k]) for k in keys), default=0)
    pointer = "❯" if color_enabled() or "utf" in (getattr(sys.stdout, "encoding", "") or "").lower() else ">"
    lines = []
    for index, k in enumerate(keys):
        on = index == cursor
        mark = icon(icons.get(k) or "dot")
        label = options[k]
        row = (paint(pointer, MAGENTA, bold=True) if on else " ") + " "
        row += paint(k, NUMBER, bold=True) + "  "
        row += (paint(mark, MAGENTA if on else VIOLET) + " ") if mark else ""
        row += paint(label, SELECTED, bold=True) if on else paint(label, WHITE)
        note = hints.get(k, "")
        if note:
            row += " " * (labels - visible_width(label) + 3) + paint(note, LILAC if on else GRAY)
        lines.append(row)
    return lines
