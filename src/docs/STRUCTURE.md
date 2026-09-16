# Gupload Repository Structure

## Directory Layout

```
gupload/
├── src/
│   ├── bin/
│   │   └── gupload                  # Bash wrapper: token retrieval, Finder
│   │                                 # selection, venv bootstrap, macOS integration
│   ├── scripts/
│   │   ├── gupload.py               # Core upload logic, GitHub API, categorization
│   │   ├── gupload-menu.sh          # Interactive menu (fzf search, repo browsing)
│   │   ├── upload-cover.sh          # Cover-image helper
│   │   ├── upload-artist-assets.sh  # Batch upload script for artist assets
│   │   ├── list-repo-artists.py     # Query GitHub API for existing artists
│   │   └── test-menu.sh             # Menu smoke-test harness
│   ├── data/
│   │   ├── config.example.json      # Configuration template with all options
│   │   ├── assets/                  # README/workflow artwork
│   │   └── gupload.workflow/        # macOS Quick Action bundle
│   └── docs/                        # Extended documentation (this file, etc.)
├── tests/                           # pytest unit tests for gupload.py's pure
│                                     # functions (categorization, path building,
│                                     # format rendering) - no network calls
├── uploads/                         # Personal upload tree, git-ignored
│   └── <category>/                  # Lowercase category folders:
│                                     #   - audio, images, video
│                                     #   - scripts/<language>/ (package structure preserved)
│                                     #   - documents, docs, data, archives, other
│                                     # A --path override on the CLI bypasses this
│                                     # auto-categorization entirely, placing the
│                                     # file directly under whatever folder you name.
├── .venv/                           # Auto-created on first run, git-ignored
├── requirements.txt                 # questionary, rich, python-magic
├── requirements-dev.txt             # + pytest
├── .gitignore
├── CLAUDE.md
└── README.md
```

## File Purposes

### Entry point (`src/bin/`)
- **gupload** - Bash wrapper for macOS integration. Resolves a GitHub token
  (env var → `gh` CLI → Keychain), collects input paths (args → stdin →
  Finder selection), bootstraps a `.venv` with the optional dependencies on
  first run (falls back to system Python if that fails), then invokes
  `gupload.py`.

### Scripts (`src/scripts/`)
- **gupload.py** - Main upload logic: categorization, filename generation,
  GitHub Contents API / Releases API upload, output formatting.
- **gupload-menu.sh** - Full-featured interactive menu with fzf search, repo
  browsing, custom naming.
- **upload-cover.sh** / **upload-artist-assets.sh** - Batch helpers for music
  library assets (covers, logos, artist images).
- **list-repo-artists.py** - Query the GitHub API and list artists already in
  the repo.

### Configuration (`src/data/`)
- **config.example.json** - Template for `~/.config/gupload/config.json`.
- **gupload.workflow/** - macOS Automator Quick Action; installed copy lives
  at `~/Library/Services/gupload.workflow` and shells out to `src/bin/gupload`.

### Tests (`tests/`)
- Cover the pure functions in `gupload.py` (no network, no filesystem beyond
  `tmp_path` fixtures): `sanitize_repo_path`, `build_jsdelivr_url`,
  `render_formats`, `category_for_path`/`category_from_magic`, and the
  lowercase-rendering helpers (`commit_message_for`, `release_prefix_for`).
  Run with `.venv/bin/python3 -m pytest tests/`.

## CLI additions worth knowing about

- `--path [FOLDER]` - manual destination folder under `uploads/`, skipping
  auto-categorization. With no value, opens an interactive picker
  (`questionary` if available, plain numbered prompt otherwise) listing the
  repo's existing folders.
- `--format LIST` - comma-separated output formats
  (`mdlink,mdimage,literal,html,jsdelivr`), printed one per line. `jsdelivr`
  only resolves for contents-API uploads; requesting it for a release asset
  prints a warning and skips that line rather than failing the run.

## Script Path Resolution

- `src/bin/gupload` resolves `SCRIPT_DIR` relative to its own location
  (`BASH_SOURCE[0]`), so it works whether invoked directly, via the `gupload`
  shell alias, or from the Automator Quick Action - no hardcoded absolute
  paths inside the script itself (the venv and `gupload.py` paths are derived
  from `SCRIPT_DIR`).
