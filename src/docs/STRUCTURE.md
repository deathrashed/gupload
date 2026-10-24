# Gupload Repository Structure

## Directory layout

```text
gupload/
├── src/
│   ├── bin/
│   │   └── gupload                  # Portable Python launcher; plan-first by default
│   ├── scripts/
│   │   ├── gupload.py               # Planning, routing, collisions, transport, CLI
│   │   ├── gupload_state.py         # XDG paths and atomic serialized JSON state
│   │   ├── gupload_menu.py          # Terminal workflows using the shared engine
│   │   ├── gupload_platform.py      # Desktop dialogs, selections, clipboard, Keychain
│   │   ├── gupload-menu.sh          # Terminal-menu entry point
│   │   ├── upload-cover.sh          # Cover-image helper; explicit execution required
│   │   ├── upload-artist-assets.sh  # Portable artist-asset batch helper
│   │   ├── list-repo-artists.py     # Explicit read-only repository browsing
│   │   └── test-menu.sh             # Local, non-publishing menu smoke
│   ├── data/
│   │   ├── config.example.json      # Safe template; no real credentials
│   │   ├── assets/                  # README and workflow artwork
│   │   ├── gupload.workflow/        # Dialog-driven macOS Quick Action
│   │   └── gupload-direct.workflow/ # Direct, plan-first macOS Quick Action
│   ├── docs/                        # Usage guide and development notes
│   └── tests/                       # Offline behavior and workflow regression tests
├── uploads/                         # Tracked, publicly hosted assets
│   └── files/licenses/              # Canonical per-license text, snippets, and artwork
├── .venv/                           # Optional, explicitly installed local dependencies
├── requirements.txt                 # Optional content-detection dependency
├── requirements-dev.txt             # Test dependencies
├── .gitignore
├── CLAUDE.md
└── README.md
```

## Ownership and behavior

### Launcher

`src/bin/gupload` locates the project interpreter without assuming one user's home directory.
It prefers the local `.venv`, then Python from `PATH`. It does not install packages or retrieve
credentials before planning. Standard output remains visible, including JSON output and errors.
File arguments, stdin paths, and decoded `file://` inputs reach the same engine.

### Upload engine

`src/scripts/gupload.py` owns filename generation, taxonomy/preset selection, complete destination
paths, transport selection, collision decisions, explicit execution, and link formatting.
Preview, CLI execution, terminal menu, and desktop dialogs share those decisions.

Offline plans do not contact GitHub, download URL inputs, retrieve tokens, write history, or copy
output to the clipboard. Execution requires `--execute` and an approved destination. Explicit
read-only commands such as remote browsing are separate from offline planning.

Repository uploads use lowercase `uploads/` with optional prefix and category/artist/image/script
organization. Large files use Release attachments with planned filenames, not fictional folders.
User sources are not moved; remote uploads do not synchronize the local checkout or obey its
`.gitignore` rules.

### State

`gupload_state.py` provides configuration and data paths plus atomic, serialized JSON updates.
Configuration follows `$XDG_CONFIG_HOME/gupload/config.json`, defaulting to
`~/.config/gupload/config.json`. Durable history, favorites, templates, and queue state live in its
`data/` directory, not the repository. Old `recent.json` records are preserved during history migration.

History records source hashes, destination, actual remote identity, status, errors, and links.
A failed-only retry excludes successful items. Corrupt state must not be silently replaced with
empty data, and importing a module must not create directories or migrate user state.

### Terminal and native interfaces

`gupload_menu.py` keeps user input as Python data and calls the shared engine; the Bash entry point
does not interpolate filenames into Python or shell programs. Its workflows include queues,
templates, destination presets, history and galleries, favorites, and explicit remote browsing.

`gupload_platform.py` provides argv-safe macOS dialogs and Linux Zenity/KDialog selection with
terminal fallback when a graphical session is unavailable. Clipboard support covers macOS, Wayland,
X11, and Termux. Mac-only tools are not required for Linux CLI/menu operation.

The Automator bundles are source assets. Installing them into `~/Library/Services` is a deliberate
user action; development checks never register workflows or change system settings automatically.

## Verification

```bash
.venv/bin/python3 -m pytest -p no:cacheprovider src/tests/ -q
./src/bin/gupload LICENSE --preview --json
./src/scripts/test-menu.sh
```

Tests cover final-path collisions, custom naming, URL filename retention, Release planning, saved-plan
source changes, CLI validation and partial failures, menu quoting, state safety, and platform behavior.
Use isolated configuration and offline transport fixtures. A live upload or account/visibility change
is not an acceptable development smoke check.
