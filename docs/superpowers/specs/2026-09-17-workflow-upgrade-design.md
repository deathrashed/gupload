# gupload workflow upgrade

Status: approved, pending implementation plan.

## Context

`gupload` uploads local files to a GitHub repo (via contents API or release
assets, depending on size) and returns a link. Current known issues /
requested improvements:

1. Category names are Title Case in two remaining spots (folder paths under
   `uploads/` are already lowercased via `remote_cat = cat.lower()` in
   `build_repo_path`, but commit messages and release-asset filename
   prefixes still use the raw Title Case `category` string).
2. The git repo has ~60 stale `Uploads/Images/*` paths tracked in the index
   from before the lowercase fix existed. macOS's case-insensitive
   filesystem hid this; it surfaced when the repo was copied to a
   case-sensitive Linux filesystem, where git correctly reports them as
   missing/deleted.
3. No way to override the destination folder at upload time — always goes
   through `category_for_path` auto-detection. User wants an escape hatch
   for cases they organize manually (e.g. `uploads/icons/wtfpl`,
   `uploads/icons/licenses`) without adding more auto-detection rules.
4. Output format is a single global config value (`output_mode`:
   markdown/url/both). User wants per-run, multi-format output including a
   jsdelivr CDN link format.
5. Opportunity to bring in better tooling for interactive selection,
   preview output, and file-type detection, approved by user with the
   tradeoff that the project moves from zero-dependency stdlib to
   needing a venv.

## Non-goals

- No content-aware categorization (e.g. auto-detecting "this SVG is an
  icon vs a photo", or reading license text to classify license type).
  Confirmed out of scope — the `--path` override covers this use case
  instead of building detection logic for it.
- No rewrite of the existing upload transport (`urllib`-based GitHub
  contents/release API calls stay as-is).
- No wholesale switch to PyGithub.

## Design

### 1. Lowercase remaining Title Case usage

In `gupload.py`:
- `upload_contents_api`: commit message `f"{category} ⋅ {...}"` →
  `f"{category.lower()} ⋅ {...}"`.
- `upload_release_asset`: prefix `f"{category}-{root}"` →
  `f"{category.lower()}-{root}"`.
- Preview/verbose output (`preview_category`, category in verbose
  logging) → lowercase for consistency, since it should read the same as
  what actually lands in the repo.

`category_for_path` itself keeps returning Title Case internally (it's
used as a Python identifier/comparison in a few places like
`is_image = cat == "Images"`) — only the *rendered* uses get
`.lower()`'d at the point of output. Low risk, no behavior change beyond
casing.

### 2. Git history cleanup (stale Title-Case paths)

One-time cleanup, done on the Linux copy (`/mnt/nvme/projects/gupload` on
cachy) since that's where the case collision is actually visible:

1. `git status --short` to enumerate every `D  Uploads/...` path.
2. For each, check whether a lowercase equivalent exists in the current
   working tree (`uploads/...`) with the same or renamed content.
   - If an equivalent exists: these are genuinely orphaned duplicate
     history entries — stage the deletion (`git rm --cached` or just let
     `git add -A` pick it up) since the real file already lives at the
     lowercase path.
   - If no equivalent exists (content genuinely only tracked under the
     old Title-Case path and never migrated): investigate before
     deleting — surface the list to the user rather than assuming.
3. Commit as a single cleanup commit: `chore: normalize legacy Uploads/*
   paths to lowercase (case-sensitivity cleanup)`.
4. Push, then pull/reset the Mac-side working copy to match (Mac's
   case-insensitive fs already couldn't see the duplication, so this is
   just syncing the cleaner history back).

This step is diagnostic-first (report findings before deleting anything),
per the safety rule on ambiguous filesystem state.

### 3. `--path` override flag

New argparse option:

```
gupload file.png --path icons/wtfpl
gupload file.png --path          # no value -> interactive picker
```

- With a value: used directly as the folder under `uploads/`, bypassing
  `category_for_path`/`build_repo_path`'s auto category logic entirely.
  Path is sanitized (no `..`, no leading `/`) but otherwise free-form and
  created on first use (contents API creates the path implicitly via the
  commit; release assets don't have folders, so `--path` with release
  assets sets the filename prefix instead of `category`).
- With no value (`nargs='?'`, `const='__PICK__'` sentinel): fetch the
  current folder listing under `uploads/` from the GitHub repo tree via
  the contents API (`GET /repos/{owner}/{repo}/contents/uploads`,
  recursive one level, or `git/trees` with `recursive=1` filtered to
  directories under `uploads/`), present via `questionary.select` /
  `questionary.autocomplete` with an explicit "+ new folder" option that
  drops into `questionary.text` for a fresh path.

### 4. `--format` flag, multi-value

```
gupload file.png --format mdlink,jsdelivr,literal
```

Comma-separated, order-preserving, each format printed on its own line
(or block, for multi-file runs — grouped per file like current output).

Formats:
- `mdlink` — `[filename](url)` (current default non-image behavior)
- `mdimage` — `![filename](url)` (current default image behavior)
- `literal` — raw `url`, nothing else
- `html` — `<img src="url">` for images, `<audio controls src="url">`
  for audio (generalizes the existing audio-only HTML tag logic), plain
  `<a href="url">filename</a>` for everything else
- `jsdelivr` — rewrites a contents-API URL
  (`https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}` or
  the GitHub API content URL) to
  `https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}`. **Only
  valid for contents-API uploads** — release assets have no jsdelivr
  equivalent. If requested for a release-asset upload, print a warning
  to stderr and skip that format for that file (don't fail the whole
  run).

No `--format` given → current behavior unchanged (`output_mode` config,
defaulting to markdown-style with image/audio special-casing).

### 5. New dependencies + venv

Add `requirements.txt`:
```
questionary
rich
python-magic
```

`src/bin/gupload` gets a one-time bootstrap check before invoking the
Python script:
```bash
VENV="$SCRIPT_DIR/../../.venv"
if [[ ! -d "$VENV" ]]; then
  echo "First run: setting up venv..." >&2
  /usr/bin/python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/../../requirements.txt"
fi
PYBIN="$VENV/bin/python3"
```
Falls back to system `/usr/bin/python3` if venv creation fails (degrade
gracefully — `rich`/`questionary` features become no-ops/plain-text, but
core upload still works). `python-magic` needs `libmagic` on the system
(Homebrew: `brew install libmagic`) — bootstrap check prints a clear
error pointing at that if the import fails, rather than crashing
opaquely.

**Use of `rich`:**
- `--preview` output becomes a `rich.table.Table`: columns for local
  filename, category/destination, size, format(s) that will be
  generated.
- Multi-file upload loop gets a `rich.progress.Progress` bar instead of
  the current `eprint(f"[{i}/{len(all_files)}] ...")` lines (verbose
  mode still prints the detailed per-file lines underneath/instead —
  don't remove information, just make the top-level progress visible).

**Use of `python-magic`:**
- `category_for_path`'s extensionless-file fallback currently only
  checks for a `#!` shebang to guess "Scripts". Replace/augment with
  `magic.from_file(path, mime=True)` for a real MIME sniff, falling back
  to the existing shebang check if `python-magic`/`libmagic` isn't
  available (keeps the graceful-degradation story from point above
  consistent).

## Testing

- Unit-level: existing behavior (category detection, filename
  sanitization, path building) should be covered by manual test runs
  against `test-menu.sh`'s existing fixtures if any exist — implementation
  plan should check what test coverage currently exists before assuming
  none.
- New flags: manual test matrix —
  - `--path explicit/value` on a contents-API-sized file and a
    release-sized file
  - `--path` with no value, picker cancel and picker select
  - `--format` single value (regression: matches old default), multiple
    values, `jsdelivr` on both a contents upload (works) and a release
    upload (warns + skips)
- Venv bootstrap: test on a machine/user without the venv dir present
  (fresh clone) to confirm first-run setup works end to end.
- Git history cleanup: dry-run the diagnostic step first, review the
  list with the user before any `git rm`/commit.
