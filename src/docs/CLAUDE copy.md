# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project Overview

Gupload is a macOS-oriented GitHub file hosting toolkit. It uploads local files or URLs to a configured GitHub repository, organizes them by category, and copies Markdown, raw URLs, or both to the clipboard.

Small files use the GitHub Contents API. Large files use GitHub Releases. The main user entry points are the `ghu` wrapper and the interactive menu in `scripts/gupload-menu.sh`.

## Project Structure

```text
Gupload/
├── ghu                         # macOS wrapper around scripts/gupload.py
├── scripts/
│   ├── gupload.py              # Core upload, naming, categorization, output logic
│   ├── gupload-menu.sh         # Interactive terminal menu
│   ├── upload-cover.sh         # Album-cover helper
│   ├── upload-artist-assets.sh # Artist asset batch helper
│   └── list-repo-artists.py    # GitHub repo artist listing helper
├── data/
│   ├── config.example.json     # User config template
│   ├── assets/                 # Project icon/assets
│   └── docs/                   # User-facing/reference docs
└── README.md                   # Main user documentation
```

## Core Flow

```text
Input paths or URLs
  -> ghu wrapper or gupload-menu.sh
  -> scripts/gupload.py
  -> categorize and build remote path
  -> Contents API for files <= contents_max_mb
  -> Releases API for larger files
  -> format output and copy to clipboard
```

## Important Files

- `scripts/gupload.py`: source of truth for upload behavior, path building, category detection, URL downloads, recent upload logging, release asset uploads, and output formatting.
- `ghu`: wrapper for Automator/Finder/CLI use. It resolves GitHub tokens through environment variables, GitHub CLI, then macOS Keychain, and logs to `/tmp/gupload.log`.
- `scripts/gupload-menu.sh`: large Bash UI surface for upload workflows, repo browsing, recent uploads, templates, gallery generation, and config editing.
- `data/config.example.json`: keep this synchronized with any config keys read by `gupload.py` or the menu.
- `README.md` and `data/docs/*.md`: user-facing docs. Update these when behavior, commands, config paths, or output formats change.

## Configuration

User config lives at:

```text
~/.config/gupload/config.json
```

Required keys:

- `owner`
- `repo`
- `branch`

Common behavior keys:

- `repo_path_prefix`: optional prefix above the default remote `Uploads/` tree.
- `contents_max_mb`: threshold for Contents API vs Releases API. Default is `95`.
- `output_mode`: `markdown`, `url`, or `both`.
- `also_audio_html`: adds `<audio>` tags for audio output.
- `dedup_strategy`: `hash`, `sequential`, or `none`.
- `append_short_hash`: appends an 8-character SHA1 suffix when hash dedupe is enabled.
- `use_audio_metadata`: optionally reads audio tags through `mutagen`.
- `use_image_subfolders`: places image assets in cover/logo/artist subfolders when enabled.
- `organize_by_artist`: groups audio and image assets by artist when enabled.

Never commit a real `config.json` or GitHub token.

## Authentication

Token lookup order:

1. `GITHUB_TOKEN` or `GH_TOKEN`
2. `gh auth token`
3. macOS Keychain service `GuploadGitHubToken` through the `ghu` wrapper

Do not hardcode tokens in scripts, docs, examples, tests, or logs.

## Upload Behavior

- Categories are determined in `category_for_path()` in `scripts/gupload.py`.
- Text files such as `.txt` and `.md` are `Documents`.
- Office/PDF-style documents are `Docs`.
- Scripts are grouped under `Scripts`, with language subfolders where applicable.
- Images can be further organized as covers, logos, or artist images.
- Recent successful uploads are stored in `~/.config/gupload/data/recent.json`.
- Contents API commit messages should use `Category ⋅ filename`, for example `Images ⋅ mediafire-icon.png`.

## Development Commands

```bash
# Run the CLI wrapper
./ghu /path/to/file

# Run the core uploader directly
/usr/bin/python3 scripts/gupload.py /path/to/file

# Launch the menu
./scripts/gupload-menu.sh

# Syntax-check Python
/usr/bin/python3 -m py_compile scripts/gupload.py scripts/list-repo-artists.py

# Syntax-check shell scripts
zsh -n ghu scripts/*.sh

# Watch wrapper logs
tail -f /tmp/gupload.log
```

## Verification Expectations

For Python-only changes, run `py_compile` on touched Python files.

For Bash wrapper or menu changes, run `zsh -n` on touched shell scripts. This project is macOS/Zsh-oriented; avoid treating Bash-only behavior as authoritative when a script is meant to run through Zsh.

For behavior touching real uploads, prefer a small disposable test file and verify:

- remote GitHub path/category
- commit message or release asset name
- copied output format
- recent upload log entry
- `/tmp/gupload.log`

Do not perform real uploads unless the user asked for a live test or clearly gave permission.

## Working Rules

- Expect a dirty worktree. Inspect `git status --short` before editing and avoid reverting unrelated changes.
- Keep `scripts/gupload.py`, `scripts/gupload-menu.sh`, `data/config.example.json`, `README.md`, and `data/docs/` synchronized when changing user-visible behavior.
- Preserve macOS integration details: absolute paths in `ghu`, `pbcopy`, `osascript`, Keychain fallback, and `/tmp/gupload.log`.
- Prefer small, direct patches over broad refactors. This is a personal workflow tool; runtime behavior and command ergonomics matter more than abstract cleanup.
- Use structured JSON handling for config and recent-upload data.
- Keep output formats stable unless the user explicitly asks for a change.

## Documentation Notes

Root `CLAUDE.md` is the canonical AI handoff. `data/docs/CLAUDE.md` should remain a short pointer or scoped supplement so it does not drift into a second source of truth.
