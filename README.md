<div align="center">

<p align="center"><img alt="gupload: upload, reference, archive" src="https://shieldcn.dev/header/grid.svg?title=gupload&subtitle=upload+%E2%80%A2+reference+%E2%80%A2+archive&logo=https%3A%2F%2Fraw.githubusercontent.com%2Fdeathrashed%2Fgupload%2Frefs%2Fheads%2Fmain%2Fuploads%2Ficons%2Fgithub%2Fgithub.png&mode=dark&font=jetbrains-mono"></p>

  <p align="center">
    <a href="https://www.python.org/downloads/"><picture><source media="(prefers-color-scheme: dark)" srcset="https://shieldcn.dev/badge/Python%203.svg?variant=outline&amp;theme=purple&amp;logo=python&amp;logoColor=ffffff&amp;mode=auto"><img src="https://shieldcn.dev/badge/Python%203.svg?variant=outline&amp;theme=purple&amp;logo=python&amp;logoColor=ffffff&amp;mode=auto" alt="Python 3 runtime"></picture></a>
    <a href="https://docs.github.com/en/rest"><picture><source media="(prefers-color-scheme: dark)" srcset="https://shieldcn.dev/badge/GitHub%20API.svg?variant=outline&amp;theme=purple&amp;logo=github&amp;logoColor=ffffff&amp;mode=auto"><img src="https://shieldcn.dev/badge/GitHub%20API.svg?variant=outline&amp;theme=purple&amp;logo=github&amp;logoColor=ffffff&amp;mode=auto" alt="GitHub API uploads"></picture></a>
    <a href="#license"><picture><source media="(prefers-color-scheme: dark)" srcset="https://shieldcn.dev/badge/GPL%20License-purple.svg?variant=outline&amp;logo=ri%3ATbBrandOpenSource&amp;mode=dark"><img alt="GPL-3.0 license" src="https://shieldcn.dev/badge/GPL%20License-purple.svg?variant=outline&amp;logo=ri%3ATbBrandOpenSource&amp;mode=light"></picture></a>
    <a href="https://www.gnu.org/software/bash/"><picture><source media="(prefers-color-scheme: dark)" srcset="https://shieldcn.dev/badge/Bash.svg?variant=outline&amp;theme=purple&amp;logo=gnubash&amp;logoColor=ffffff&amp;mode=auto"><img src="https://shieldcn.dev/badge/Bash.svg?variant=outline&amp;theme=purple&amp;logo=gnubash&amp;logoColor=ffffff&amp;mode=auto" alt="Bash command wrapper"></picture></a>
  </p>
  <p align="center"><strong>Upload files to GitHub and copy shareable Markdown, HTML, and raw links.</strong></p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> | <a href="#usage">Usage</a> |
    <a href="#assets">Assets</a> | <a href="#configuration">Configuration</a> |
    <a href="#development">Development</a> | <a href="#license">License</a>
  </p>
</div>


---

<a name="quick-start"></a>

## <img src="https://api.iconify.design/lucide/cloud-upload.svg?color=%23b030f0" height="22" alt=""> Quick Start

Requires Python 3.9+ and Bash on macOS or Linux. Ordinary commands produce an **offline plan**:
no token lookup, downloads, GitHub requests, history writes, or clipboard changes.

```bash
git clone https://github.com/deathrashed/gupload.git
cd gupload
mkdir -p ~/.config/gupload
cp -n src/data/config.example.json ~/.config/gupload/config.json
${EDITOR:-nano} ~/.config/gupload/config.json
python3 src/scripts/gupload.py --preview LICENSE
```

Set `owner`, `repo`, and `branch` in the config. Authentication is needed only for explicit
execution or remote browsing, not for local planning.

> [!IMPORTANT]
> `--execute` writes directly to GitHub, even without `git push`. Review the plan and exact
> destination first. Public raw/CDN links require a public repository; draft Release assets are private.

<a name="usage"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%23b030f0" height="22" alt=""> Usage

```bash
# Plan local files; nothing is uploaded
./src/bin/gupload ~/Desktop/example.png
./src/bin/gupload file1.jpg file2.pdf --json
printf '%s\n' /path/to/file1.mp3 /path/to/file2.jpg | ./src/bin/gupload

# Keep license artwork in its canonical collection
./src/bin/gupload logo.svg --preset wtfpl --name "WTFPL logo.svg"

# Save a reviewable plan without publishing
./src/bin/gupload cover.jpg --format mdimage,jsdelivr \
  --save-plan /tmp/gupload-review.json
```

Publishing is a separate action. This example requires the config to target `deathrashed/gupload`:

```bash
./src/bin/gupload --apply-plan /tmp/gupload-review.json \
  --execute --expect-repo deathrashed/gupload
```

| Option | Effect |
| --- | --- |
| `--plan`, `--preview`, `--dry-run` | Offline planning; also the default with file arguments. |
| `--execute` | Explicitly authorize publication through the GitHub API. |
| `--save-plan FILE`, `--apply-plan FILE` | Review and apply a saved plan with source/destination checks. |
| `--expect-repo OWNER/REPO` | Guard execution against the wrong configured repository. |
| `--expect-account LOGIN` | Require the publishing token to belong to the expected login. |
| `--name NAME`, `--names NAME...` | Set one filename, or exactly one name per input. |
| `--path FOLDER`, `--preset NAME` | Choose a folder or saved destination preset below `uploads/`. |
| `--collision POLICY` | `skip-identical`, `rename`, or explicit `update`. |
| `--format LIST` | `mdlink`, `mdimage`, `literal`, `html`, or `jsdelivr`, comma-separated. |
| `--json` | Machine-readable plans/results, with nonzero status for failed inputs. |
| `--check-remote`, `--list-remote [FOLDER]` | Explicit read-only remote inspection; not offline. |
| `--retry-failed` | Select failed history items without replaying successful ones. |
| `--menu`, `--dialog` | Terminal menu or native desktop selections and text entry. |

URL inputs remain unresolved in an offline plan: execution downloads them and preserves their
suggested filename separately from temporary storage. Sensitive files are flagged before publication.
Run `./src/bin/gupload --help` for the full interface.

> [!TIP]
> Add `--json` to any command for machine-readable plans and results. Pair it with `--preview`
> to check where files will land before anything is published.

<details>
<summary><strong>Helpers</strong></summary>

**macOS:** `./src/bin/gupload --dialog` opens file/URL selection, naming, destination, and
preview dialogs. Canceling or viewing a plan never publishes.
[`gupload.workflow`](src/data/gupload.workflow) provides the dialog Quick Action;
[`gupload-direct.workflow`](src/data/gupload-direct.workflow) preserves a direct, plan-first action.
The bundles are not installed into `~/Library/Services` automatically.

**Linux:** the CLI and terminal menu need Python and Bash. Native file selection uses
Zenity or KDialog when available; headless sessions use the terminal menu.
Clipboard output supports `wl-copy`, `xclip`, `xsel`, or `termux-clipboard-set`.
Configuration follows `$XDG_CONFIG_HOME/gupload` or `~/.config/gupload`.

```bash
./src/bin/gupload --menu
./src/bin/gupload --dialog
./src/scripts/upload-cover.sh \
  https://example.com/cover.jpg "Artist" "1993" "Album"
./src/scripts/upload-artist-assets.sh "/path/to/Artist"
```

Helpers also plan by default; publication requires explicit execution. The launcher uses the
project `.venv` when present, otherwise Python from `PATH`. It does not install dependencies.
Optional content-based file detection can be installed explicitly:

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
```

`python-magic` needs system `libmagic` (`brew install libmagic` on macOS).
For a graphical Linux picker, install your distribution's `zenity` or `kdialog` package.

</details>

<details>
<summary><strong>Using gupload from scripts and coding agents</strong></summary>

```markdown
## gupload: upload files to GitHub and print shareable links
- `./src/bin/gupload FILE --preview --json`: offline plan, safe to run (no token, network, or clipboard)
- `./src/bin/gupload FILE --save-plan plan.json`: write a reviewable plan
- `./src/bin/gupload --apply-plan plan.json --execute --expect-repo OWNER/REPO`: publish
- Any failed item makes the exit status nonzero; successful items stay recorded
- `--retry-failed` retries only failed history items
```

</details>

<a name="assets"></a>

## <img src="https://api.iconify.design/lucide/folders.svg?color=%23b030f0" height="22" alt=""> Assets

Files below [`uploads/`](uploads/) are tracked intentionally: GitHub raw and jsDelivr URLs
need committed assets. Only disposable uploads under `uploads/test/` are ignored.
GitHub paths are case-sensitive; the upload root and category folders are lowercase.

| Location | Contents |
| --- | --- |
| [`uploads/files/licenses/`](uploads/files/licenses/) | License texts, README snippets, logos, and badges (GPL, LGPL, MIT, BSD, Apache, WTFPL, Unlicense, CC0, CC BY, CC BY-SA), plus shared art in `common/`. |
| [`uploads/icons/`](uploads/icons/) | Non-license icons, service logos, and banners. |
| [`uploads/images/`](uploads/images/) | Image assets. |
| [`uploads/audio/`](uploads/audio/) | Audio assets. |
| [`uploads/video/`](uploads/video/) | Video assets. |
| [`uploads/scripts/`](uploads/scripts/) | Hosted scripts. |

Keep license artwork beside its license text, not duplicated under `icons/` or loose in `files/`.
Built-in presets cover each license folder (`gpl`, `lgpl`, `mit`, `bsd`, `apache`, `wtfpl`, `unlicense`,
`cc0`, `cc-by`, `cc-by-sa`), shared license art (`license-common`), and `docker-icons`; custom presets use the same routing
as `--path`. Automatic license-name detection uses the general `files/licenses/` destination.
Uploads write to the remote repository, not your local checkout, and do not obey `.gitignore`.

<a name="configuration"></a>

## <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%23b030f0" height="22" alt=""> Configuration

Config: `$XDG_CONFIG_HOME/gupload/config.json`, defaulting to `~/.config/gupload/config.json`.
Start from [`src/data/config.example.json`](src/data/config.example.json).

| Key | Purpose |
| --- | --- |
| `owner`, `repo`, `branch` | Destination GitHub repository and branch. |
| `repo_path_prefix` | Optional prefix before `uploads/`. |
| `taxonomy_rules`, `presets` | Filename rules and reusable destination/output settings. |
| `collision_policy` | Default `skip-identical`; different content needs `rename` or explicit `update`. |
| `allowed_destinations` | Exact repositories allowed for execution without `--expect-repo`. |
| `expected_account` | Optional required GitHub token login. |
| `contents_max_mb` | Contents API cutoff, default 95 MiB; larger files use Releases. |
| `download_max_mb` | URL download cap, default 512 MiB. |
| `output_mode` | Default output: `markdown`, `url`, or `both`. |
| `organize_by_artist` | Group supported audio/image assets by artist. |
| `use_audio_metadata` | Read audio tags for naming when optional metadata support is installed. |
| `release_draft` | Defaults to `true`; draft assets are not public downloads. |

<details>
<summary><strong>Authentication, naming, and history</strong></summary>

Execution checks token identity and repository visibility before changing remote state.
Token lookup uses `GITHUB_TOKEN`, `GH_TOKEN`, authenticated GitHub CLI, then macOS Keychain.
An offline plan never consults those sources. Tokens and actual user config are never saved in plans.

Custom names still participate in artist/image/script routing and collision decisions.
`use_path_for_generic_names` derives names from paths for generic filenames such as `cover.jpg`;
`--path` or a preset overrides automatic folder selection.

Durable upload history lives under the config directory's `data/` folder, alongside queue,
favorites, and templates. Writes are atomic; records include hashes, destination, status,
and remote identity. Existing `recent.json` records are retained during migration.
Retrying failures excludes already successful items. jsDelivr applies to Contents API files,
not Release attachments.

</details>

## <img src="https://api.iconify.design/lucide/folder-tree.svg?color=%23b030f0" height="22" alt=""> Structure

```text
gupload/
├── src/
│   ├── bin/gupload              # Portable, plan-first launcher
│   ├── scripts/                 # Shared engine, state, terminal menu, desktop adapters
│   ├── data/                    # Config, artwork, dialog and direct Quick Actions
│   ├── docs/                    # Usage guide and layout reference
│   └── tests/                   # Offline behavior and workflow regression tests
├── uploads/                     # Publicly hosted assets
│   ├── files/licenses/          # License collections + shared common/ art
│   ├── icons/                   # Other icons and logos
│   ├── images/                  # Images
│   ├── audio/                   # Audio
│   ├── video/                   # Video
│   └── scripts/                 # Hosted scripts
├── requirements.txt             # Pinned optional UI/detection dependencies
├── requirements-dev.txt         # Development dependencies
└── LICENSE                      # Project license
```

<a name="development"></a>

## <img src="https://api.iconify.design/lucide/wrench.svg?color=%23b030f0" height="22" alt=""> Development

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements-dev.txt
.venv/bin/python3 -m pytest -p no:cacheprovider src/tests/ -q
for script in src/bin/gupload src/scripts/*.sh; do bash -n "$script"; done
```

The suite uses isolated state and offline transport fixtures. Do not use live uploads or GitHub
account changes to verify development work. See the [usage guide](src/docs/USAGE.md) for
platform setup, publication safeguards, and menu workflows.

<a name="license"></a>

## <a href="https://www.gnu.org/licenses/gpl-3.0.html"><img src="https://raw.githubusercontent.com/deathrashed/gupload/refs/heads/main/uploads/files/licenses/common/free-works-logo.svg" height="20" alt="GPL-3.0-or-later license website"></a> License

<div align="center">

[**𝗚𝗡𝗨 𝗚𝗣𝗟 𝗟𝗜𝗖𝗘𝗡𝗦𝗘**](https://raw.githubusercontent.com/deathrashed/gupload/refs/heads/main/uploads/files/licenses/gpl/LICENSE)

<a href="https://raw.githubusercontent.com/deathrashed/gupload/refs/heads/main/uploads/files/licenses/gpl/LICENSE"><img src="https://raw.githubusercontent.com/deathrashed/gupload/refs/heads/main/uploads/files/licenses/gpl/gpl-license-badge.svg" alt="GPL Badge" width="180"></a>

**𝗖𝗢𝗣𝗬𝗥𝗜𝗚𝗛𝗧 © 𝟮𝟬𝟮𝟲 𝗗𝗘𝗔𝗧𝗛𝗥𝗔𝗦𝗛𝗘𝗗**

</div>


