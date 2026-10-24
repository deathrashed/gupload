# Gupload Usage Guide

## Plan first, publish explicitly

Gupload runs on macOS and Linux with Python 3.9+ and Bash. Its default is a local plan, not an upload.
Planning reads configuration and source files but does not retrieve credentials, download URLs,
contact GitHub, write history, or change the clipboard.

```bash
./src/bin/gupload ~/Desktop/example.png
./src/bin/gupload file1.jpg file2.pdf --json
printf '%s\n' /path/to/file1.mp3 /path/to/file2.jpg | ./src/bin/gupload
./src/bin/gupload icon.svg --preset wtfpl --name "WTFPL logo.svg"
./src/bin/gupload cover.jpg --format mdimage,jsdelivr,literal --preview
```

`--plan`, `--preview`, and `--dry-run` all request offline planning. Missing files, invalid formats,
and mismatched `--names` counts fail before publication. `--name` requires exactly one input.
An invalid item makes the process fail even when other batch items succeed.

## Configuration and dependencies

Configuration lives at `$XDG_CONFIG_HOME/gupload/config.json`, or `~/.config/gupload/config.json`
when `XDG_CONFIG_HOME` is unset. Start from `src/data/config.example.json`, then set `owner`, `repo`,
and `branch`. Keep real config and credentials outside the repository.

The launcher prefers the project's `.venv`, then Python from `PATH`. It does not automatically install
packages or retrieve a token. Install optional UI, detection, and metadata dependencies explicitly:

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
```

Content-based detection needs `libmagic`. Audio metadata support depends on the metadata module being
installed; path-based naming remains available without it. Use `.venv/bin/python3 -m pip install
mutagen` if your environment does not already provide it.

## Review and apply a saved plan

```bash
./src/bin/gupload cover.jpg --preset album-covers \
  --save-plan /tmp/gupload-review.json
```

A saved plan records the destination, final naming decisions, source hashes, transport, collision
policy, and warnings. Applying it checks that local sources and the destination have not changed.
Source URLs remain unresolved until a network-enabled action downloads them; an offline plan cannot
claim to know their content hash or size.

Publication is an explicit operation. The following example assumes the configured destination is
`deathrashed/gupload`; use your exact configured repository for other destinations:

```bash
./src/bin/gupload --apply-plan /tmp/gupload-review.json \
  --execute --expect-repo deathrashed/gupload
```

`--execute` changes GitHub through its API even though no `git push` is run. The terminal menu and
native dialog show the plan and require a separate confirmation before requesting execution.

## Destination and account safeguards

`--expect-repo OWNER/REPO` must match the configured target. Alternatively, configure exact entries in
`allowed_destinations` for destinations you deliberately permit. `--expect-account LOGIN` or the
`expected_account` configuration key requires the publishing token to belong to that login.
Execution checks token identity and repository visibility before remote mutations.

Authentication is consulted only for execution or an explicitly requested remote inspection:

1. `GITHUB_TOKEN`.
2. `GH_TOKEN`.
3. GitHub CLI, if enabled in configuration.
4. The macOS Keychain service `GuploadGitHubToken`, on macOS only.

GitHub authentication tokens are never saved to disk, embedded in plans, or recorded in history.
However, source file paths and source URLs (including any signed query parameters or URL userinfo supplied
as input) are retained in saved plans and local history records to enable retry and integrity validation. Protect
saved plan files accordingly. Sensitive sources such as real config, environment files, private keys,
tooling caches, and URLs carrying embedded credentials or tokens are identified in plans and blocked
from execution unless `--allow-sensitive` is explicitly supplied.
Review them yourself; this check is not a guarantee that an arbitrary file contains no secrets.
Gupload does not use `.gitignore` as an authorization mechanism for API uploads.
A public repository is required for anonymously accessible raw and jsDelivr URLs. Release assets
attached to draft releases are not public. Planning and execution warn about accessibility limits;
Gupload never changes repository visibility on your behalf.

## File destinations and naming

Repository files are stored below `uploads/`, with an optional `repo_path_prefix` above that root.
Default categories include audio, images, video, scripts, text documents, Office/PDF documents,
data, archives, and other files. Scripts can be grouped by language and recognized package layout.

```text
uploads/
├── audio/                  # Audio, or artist-organized music assets
├── images/                 # Images; optional covers/logos/artists subfolders
├── video/                  # Video files
├── scripts/                # Language and optional package directories
├── documents/              # Text and Markdown
├── docs/                   # PDF and Office-style documents
├── data/                   # JSON, YAML, CSV, and similar data
├── files/licenses/         # License collections
├── icons/                  # Icon files and explicit icon destinations
├── archives/               # Archive files
└── other/                  # Uncategorized files
```

Folder precedence is explicit `--path`, selected preset, configured filename rules, built-in rules,
then automatic category/artist/image/script routing. Custom names still take part in routing and
collision handling. A custom name is not a custom path.

`use_path_for_generic_names` derives useful names for generic images such as `cover.jpg`.
`use_audio_metadata` reads artist/title tags when support is installed; `use_path_for_audio_names`
provides path-based artist/title naming. `organize_by_artist` groups recognized music-related images
and audio under `uploads/audio/<Artist>/`. `use_image_subfolders` controls covers/logos/artists when
artist organization is not selected.

Filename-based license detection recognizes names such as `LICENSE` and `COPYING`; it does not infer
a specific license from file contents. Use a license preset (`gpl`, `lgpl`, `mit`, `bsd`, `apache`, `wtfpl`,
`unlicense`, `cc0`, `cc-by`, `cc-by-sa`, or `license-common` for shared art) to keep license text and artwork together:

```bash
./src/bin/gupload logo.svg --preset wtfpl
./src/bin/gupload LICENSE --path files/licenses/mit
```

Source files are never moved or renamed locally. Uploads write directly to the remote repository,
not the local checkout. URL downloads use temporary storage while retaining the source's suggested
filename for naming; temporary files are cleaned up on success and failure.

## Presets, templates, and collisions

Built-in presets are `wtfpl`, `mit`, `gpl`, and `docker-icons`. Add custom entries under `presets`:

```json
{
  "presets": {
    "album-covers": {
      "path": "images/covers",
      "formats": ["mdimage", "jsdelivr"],
      "collision": "rename"
    }
  }
}
```

Explicit CLI options override preset values. Menu templates save reusable destination, naming,
output, and collision selections and apply them through the same engine as CLI calls.

| Policy | Existing destination |
| --- | --- |
| `skip-identical` | Reuse the link when content matches; reject different content. Default. |
| `rename` | Choose an available numbered filename in the final destination directory. |
| `update` | Explicitly replace different content using the remote file identity. |

Collision checks use the complete destination after artist, image, script, and preset routing.
Non-404 errors such as authentication failures and network errors are not treated as missing files.
Read-only collision inspection requires an explicit remote action; offline plans leave it unresolved.

## Large files and link formats

Files within `contents_max_mb` use the GitHub Contents API. Larger files use Release attachments,
which have filenames rather than directories. The plan and execution share the same Release filename;
custom names are respected. Files over the supported Release size limit fail rather than upload.

`release_draft` defaults to true. Review release publication separately before sharing anonymous links.
The uploader does not publish a draft simply to make a link appear usable.

```bash
./src/bin/gupload file.png --format mdlink,mdimage,literal,html,jsdelivr
```

Available formats are `mdlink`, `mdimage`, `literal`, `html`, and `jsdelivr`. `output_mode` controls
config-driven defaults. HTML output selects image, audio, or ordinary link markup. jsDelivr applies
only to repository files, not Release assets. Unknown formats are rejected before network activity.
Successful execution can copy the resulting links to the clipboard; offline plans do not.

## Terminal menu, history, and remote browsing

```bash
./src/bin/gupload --menu
# Equivalent entry point:
./src/scripts/gupload-menu.sh
```

The menu provides file/URL/folder and artist-asset selection; names and destination overrides;
presets and saved templates; category and artist browsing; history search/export and galleries;
favorites; queue management; config, logs, stats, and help. Remote browsing is an explicit read-only
action and is not performed just by opening the menu.

Durable state is stored in the config directory's `data/` folder. Atomic serialized updates protect
history, favorites, templates, and queues. History records source hashes, actual remote identity,
destination, transport, status, errors, and successful links. Existing `recent.json` history remains
available; planning does not migrate or rewrite it.

Retry failed items without replaying successes:

```bash
./src/bin/gupload --retry-failed --preview
# Publishing retries still requires --execute and the destination guard.
```

Clipboard monitoring is opt-in and queues/plans detected inputs instead of silently publishing them.
Do not enable monitoring while copying credentials or private URLs.

## Native dialogs and platform integration

```bash
./src/bin/gupload --dialog
```

On macOS, native dialogs accept file selections or a URL, custom names, destination presets or paths,
link formats, and collision policy. You can view a plan or cancel; publication requires its own
confirmation. Finder selections can be supplied as workflow inputs.

The bundled Quick Actions are:

- `src/data/gupload.workflow`: dialog-based selections, text entry, and plan review.
- `src/data/gupload-direct.workflow`: direct plan-first invocation with selected files.

Installing a Quick Action into `~/Library/Services` is a separate user action: open the bundled
workflow in Finder and follow macOS's installation prompt. Existing installed workflows are not
replaced by editing these source bundles.

Launcher lookup checks executable `GUPLOAD_BIN`, then `~/.local/bin/gupload`, `~/bin/gupload`,
and `gupload` on `PATH`. If none is found, macOS asks you to choose `src/bin/gupload`.
Keep that launcher executable. To make it discoverable without relying on your terminal's PATH,
you can create a local symlink from the repository root:

```bash
mkdir -p ~/.local/bin
ln -s "$PWD/src/bin/gupload" ~/.local/bin/gupload
```

If that destination already exists, inspect it rather than replacing it blindly.

On Linux, native selection uses Zenity or KDialog when a desktop session is available. Without a
supported desktop picker, use the terminal menu or pass file paths directly. Clipboard tools are
`wl-copy` (Wayland), `xclip`/`xsel` (X11), and `termux-clipboard-set` (Termux). The terminal uploader does
not require Finder, Keychain, AppleScript, or a graphical session.

## Local verification

```bash
.venv/bin/python3 -m pytest -p no:cacheprovider src/tests/ -q
./src/bin/gupload LICENSE --preview --json
./src/scripts/test-menu.sh
```

These checks must not publish, change GitHub account settings, or require live credentials. Use
isolated config/state and offline transport fixtures for development tests. Keep generated caches,
agent plans, and editor-specific state out of the repository.
