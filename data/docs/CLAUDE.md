# CLAUDE.md

This file is a scoped supplement for `data/docs/`. The canonical Claude Code handoff now lives at the repository root: `../../CLAUDE.md`.

## Documentation Scope

Files in this directory are user-facing reference docs for Gupload. Keep them synchronized with root behavior when changing:

- upload commands
- config paths and keys
- category names
- output formats
- authentication behavior
- GitHub Contents vs Releases behavior
- macOS wrapper/menu workflows

## Current Contract

- Main CLI wrapper: `../../ghu`
- Core uploader: `../../scripts/gupload.py`
- Interactive menu: `../../scripts/gupload-menu.sh`
- Config template: `../config.example.json`
- User config path: `~/.config/gupload/config.json`
- Upload log path: `/tmp/gupload.log`
- Recent upload store: `~/.config/gupload/data/recent.json`

Contents API commit messages use `Category ⋅ filename`, for example:

```text
Images ⋅ mediafire-icon.png
Documents ⋅ Trae Script Naming Rules.md
```

## Editing Rules

- Do not let this file duplicate the full root `CLAUDE.md`; link back to root instead.
- Update `README.md`, `USAGE.md`, `STRUCTURE.md`, and `data/config.example.json` when docs mention changed behavior.
- Never include real GitHub tokens, private config values, or personal upload URLs unless the user explicitly provided them for documentation.
