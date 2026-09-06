<div align="center">
  <img src="src/data/assets/folder.png" alt="Gupload folder icon" width="150">

  <h1>GU·UPLOAD</h1>

  <p><strong>A macOS-first GitHub uploader for turning files, links, and Finder selections into clean, shareable repository assets.</strong></p>

  <p>
    <img src="https://img.shields.io/badge/platform-macOS-1e1e1e?style=for-the-badge&logo=apple&logoColor=b030f0" alt="macOS">
    <img src="https://img.shields.io/badge/runtime-Python%203-1e1e1e?style=for-the-badge&logo=python&logoColor=b030f0" alt="Python 3">
    <img src="https://img.shields.io/badge/transport-GitHub%20API-1e1e1e?style=for-the-badge&logo=github&logoColor=b030f0" alt="GitHub API">
  </p>

  <p>
    <a href="#quick-start">Quick Start</a> |
    <a href="#usage">Usage</a> |
    <a href="#how-it-works">How It Works</a> |
    <a href="#structure">Structure</a> |
    <a href="#security">Security</a>
  </p>
</div>

---

## <img src="https://api.iconify.design/mdi:rocket-launch-outline.svg?color=%23b030f0" height="22"> Quick Start

> [!NOTE]
> The toolkit is organized around `src/`, `src/bin/gupload`, `src/scripts/`, `src/data/`, `src/docs/`, and a lowercase `uploads/` tree.

```bash
git clone https://github.com/OWNER/REPOSITORY.git gupload
cd gupload

chmod +x src/bin/gupload src/scripts/*.sh
cp src/data/config.example.json ~/.config/gupload/config.json
$EDITOR ~/.config/gupload/config.json

./src/bin/gupload ~/Desktop/example.png
```

Gupload needs Python 3 and a GitHub repository. Authentication can come from `GITHUB_TOKEN`, `GH_TOKEN`, GitHub CLI, or the macOS Keychain integration used by the wrapper.

## <img src="https://api.iconify.design/mdi:star-four-points-outline.svg?color=%23b030f0" height="22"> What It Does

| Capability | Result |
| --- | --- |
| Single or batch uploads | Send local files, multiple paths, or newline-separated stdin input. |
| URL downloads | Download a remote asset, assign a custom name, and upload it in one command. |
| Smart categorization | Sort audio, images, video, scripts, documents, data, archives, and other files. |
| Smart naming | Derive useful names from artist, album, path, and audio metadata when enabled. |
| Large-file handling | Use GitHub Contents API for ordinary files and GitHub Releases for large assets. |
| Interactive macOS workflow | Select files through Finder or use the menu-driven shell interface. |
| Upload history | Keep the latest successful uploads in `~/.config/gupload/data/recent.json`. |

## <img src="https://api.iconify.design/mdi:console-line.svg?color=%23b030f0" height="22"> Usage

### Command line

```bash
./src/bin/gupload /path/to/file.mp3
./src/bin/gupload file1.jpg file2.pdf file3.mp4

./src/bin/gupload --name "Deteriorate - 1993 - Rotting in Hell.jpg" \
  https://example.com/cover.jpg

./src/bin/gupload --names "Cover 1.jpg" "Cover 2.jpg" \
  https://example.com/one.jpg https://example.com/two.jpg

printf '%s\n' /path/to/file1.mp3 /path/to/file2.jpg | ./src/bin/gupload
./src/bin/gupload                         # Finder picker
```

### Helper workflows

```bash
./src/scripts/upload-cover.sh \
  https://example.com/cover.jpg "Deteriorate" "1993" "Rotting in Hell"

./src/scripts/upload-artist-assets.sh "/Volumes/Audio/Metal/C/Cold Steel"
./src/scripts/gupload-menu.sh
```

| Option | Purpose |
| --- | --- |
| `--name NAME` | Name one downloaded or uploaded file. |
| `--names NAME...` | Supply names for multiple URL inputs. |
| `--verbose` | Show more request and processing detail. |
| `--help` | Display the command-line help. |

Run `./src/bin/gupload --help` for the authoritative option list.

## <img src="https://api.iconify.design/mdi:source-branch.svg?color=%23b030f0" height="22"> How It Works

```text
input path / URL / Finder selection
              │
              ▼
      src/bin/gupload
              │
              ▼
     src/scripts/gupload.py
       ┌──────┴──────┐
       ▼             ▼
  classify/name   authenticate
       │             │
       └──────┬──────┘
              ▼
       GitHub Contents API
       or GitHub Releases
              │
              ▼
      lowercase uploads/ tree
```

Uploads are written to the remote repository under `uploads/<category>/...`. The current repository categories are `audio`, `images`, `video`, and `icons`.

> [!WARNING]
> GitHub paths are case-sensitive. The canonical upload root is now lowercase `uploads/`.

```text
uploads/
├── audio/
├── images/
├── video/
└── icons/
```

## <img src="https://api.iconify.design/mdi:cog-outline.svg?color=%23b030f0" height="22"> Configuration

```bash
mkdir -p ~/.config/gupload
cp src/data/config.example.json ~/.config/gupload/config.json
```

| Key | Role |
| --- | --- |
| `owner` | GitHub account or organization. |
| `repo` | Destination repository. |
| `branch` | Contents API branch; defaults to `main`. |
| `repo_path_prefix` | Optional path prefix before `uploads/`. |
| `organize_by_artist` | Organize supported audio assets below artist directories. |
| `use_path_for_generic_names` | Turn names such as `cover.jpg` into useful names from the source path. |
| `use_metadata` | Use embedded audio metadata for naming where available. |
| `release_*` | Control release name, tag, draft state, and timestamp behavior. |

See [`src/data/config.example.json`](src/data/config.example.json) for the complete set of supported keys.

<details>
<summary><strong>Authentication precedence</strong></summary>

1. `GITHUB_TOKEN`
2. `GH_TOKEN`
3. `gh auth token`, when GitHub CLI is authenticated
4. The macOS Keychain service used by the wrapper

</details>

## <img src="https://api.iconify.design/mdi:folder-cog-outline.svg?color=%23b030f0" height="22"> Structure

```text
gupload/
├── src/
│   ├── bin/
│   │   └── gupload                 # Main executable wrapper
│   ├── scripts/
│   │   ├── gupload.py              # Upload engine and GitHub API logic
│   │   ├── gupload-menu.sh         # Interactive shell workflow
│   │   ├── upload-cover.sh          # Cover-image helper
│   │   ├── upload-artist-assets.sh  # Artist asset batch helper
│   │   ├── list-repo-artists.py     # Repository browsing helper
│   │   └── test-menu.sh             # Menu smoke-test harness
│   ├── data/
│       ├── config.example.json      # Safe configuration template
│       ├── assets/                  # README and workflow artwork
│       └── Gupload.workflow/        # macOS Quick Look workflow
│   └── docs/                        # Extended project documentation
├── uploads/                         # Lowercase remote/local upload tree
├── .gitignore
├── CLAUDE.md
└── README.md
```

The `uploads/` directory is personal output and should remain ignored unless you intentionally want to version uploaded assets in the local checkout.

## <img src="https://api.iconify.design/mdi:shield-lock-outline.svg?color=%23b030f0" height="22"> Security

- Never commit `config.json`, access tokens, or generated credentials.
- Prefer environment variables or GitHub CLI authentication for automation.
- Review a token’s repository and organization permissions before use.
- Treat downloaded URLs as untrusted input and inspect the resulting file before sharing it.
- Keep logs free of tokens and redact private repository URLs when sharing diagnostics.

> [!CAUTION]
> If a GitHub token is ever committed, revoke it immediately, remove it from history, and create a replacement. Deleting the file alone is not sufficient.

## <img src="https://api.iconify.design/mdi:tools.svg?color=%23b030f0" height="22"> Development Checks

```bash
python3 -m py_compile src/scripts/gupload.py src/scripts/list-repo-artists.py
bash -n src/bin/gupload src/scripts/*.sh
```

Before considering the reorganization complete, verify that:

- `src/bin/gupload` resolves `src/scripts/gupload.py` from any working directory.
- Every helper resolves `src/bin/gupload` after the rename from `ghu`.
- `uploads/` is used consistently in generated GitHub paths and documentation.
- Existing upload links should be reviewed whenever the remote directory layout changes.
- The interactive menu and Finder workflow still pass paths containing spaces.

## <img src="https://api.iconify.design/mdi:book-open-page-variant-outline.svg?color=%23b030f0" height="22"> Documentation

- [`src/docs/USAGE.md`](src/docs/USAGE.md) — extended usage notes
- [`src/docs/STRUCTURE.md`](src/docs/STRUCTURE.md) — repository layout
- [`src/docs/CLAUDE.md`](src/docs/CLAUDE.md) — scoped development handoff

## <img src="https://api.iconify.design/mdi:license.svg?color=%23b030f0" height="22"> License

This project uses the [Do What The Fuck You Want To Public License v2](LICENSE), copyright © 2026 deathrashed.
