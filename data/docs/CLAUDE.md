# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Gupload** is a GitHub-based file hosting system that uploads files to GitHub repos or releases and returns markdown/HTML links. It automatically categorizes files by type (Audio, Images, Video, Docs, Archives, Other) and handles small files (<95MB) via GitHub Contents API and large files (95MB-2GB) via GitHub Releases.

## Architecture

### Core Components

1. **ghuploader.py** - Main Python upload logic
   - Handles GitHub API authentication (via env vars or `gh` CLI)
   - Two upload paths:
     - **Contents API**: Small files (<95MB) → stored in `uploads/{category}/{filename}` in the repo
     - **Releases API**: Large files (95MB-2GB) → attached to a GitHub release (default: `gupload-uploads` tag)
   - File categorization by extension/mimetype
   - Filename sanitization and collision prevention via SHA1 hash suffix
   - Output formatting (markdown, URL, or both)
   - Clipboard integration (macOS via `pbcopy`)

2. **ghu** - Bash wrapper script for macOS integration
   - Pulls GitHub token from macOS Keychain if not in env
   - Accepts files via: CLI args, stdin, or Finder selection (AppleScript)
   - Normalizes `file://` URLs
   - Logs all operations to `/tmp/gupload.log`

3. **Configuration** - `~/.config/ghuploader/config.json`
   - Required fields: `owner`, `repo`, `branch`
   - Optional behavior toggles for filename cleaning, hash appending, output formats, etc.
   - See example in ghuploader.py:226-237 for structure

### File Flow

```
User Input (file paths)
    ↓
ghu wrapper (macOS integration, token retrieval)
    ↓
ghuploader.py (categorization, size check)
    ↓
    ├─→ <95MB: GitHub Contents API → uploads/{category}/{sanitized-name-hash.ext}
    └─→ ≥95MB: GitHub Releases API → Release asset with category prefix
    ↓
Markdown/HTML output + clipboard copy
```

### Upload Destinations

- **Small files** → Committed to repo: `{category}/{filename-hash.ext}` (e.g., `Audio/Pendulum-Witchcraft-2cece43e.mp3`)
  - Categories at top level by default (configurable via `repo_path_prefix`)
- **Large files** → Attached to GitHub release (draft by default)
- Commit messages include category and timestamp: `Upload (Audio) song.mp3 @ 2026-01-09 01:24:25`

## Key Configuration

All config lives in `~/.config/ghuploader/config.json`:

### Required Settings
- `owner`, `repo`, `branch` - Target GitHub repository

### Path & Organization
- `repo_path_prefix` (default: "") - Optional prefix for all uploads (e.g., "uploads" → `uploads/Audio/file.mp3`)
  - Default changed to empty string - categories now at top level: `Audio/file.mp3`, `Images/pic.jpg`

### Filename Handling
- `clean_filename` (default: true) - Strips bracket patterns like `[1080p]`, `(MacKed)`
- `dedup_strategy` (default: "hash") - How to handle filename collisions:
  - `"hash"` - Appends 8-char SHA1 hash (e.g., `song-2cece43e.mp3`) - fast, guaranteed unique
  - `"sequential"` - Appends numbers if file exists (e.g., `song.mp3`, `song (2).mp3`) - cleaner but requires API check
  - `"none"` - No collision handling - upload will fail if filename exists
- `append_short_hash` (default: true) - Used when `dedup_strategy: "hash"`
- `use_audio_metadata` (default: false) - Extract artist/title from audio file tags
  - Requires `mutagen` library: `pip3 install mutagen`
  - Creates filenames like `Pendulum - Witchcraft.mp3` instead of `12.-Witchcraft.mp3`
  - Falls back to original filename if metadata unavailable

### Upload Behavior
- `contents_max_mb` (default: 95) - Size threshold for Contents vs Releases API
- `continue_on_error` (default: true) - Continue batch uploads even if one file fails
- `verbose` (default: false) - Show detailed progress for each file

### Output Formatting
- `output_mode` - "markdown" (default), "url", or "both"
- `also_audio_html` (default: true) - Adds `<audio>` tags for audio files

### Release Settings (for large files ≥95MB)
- `release_tag`, `release_name`, `release_draft` - GitHub release configuration
- `release_prefix_category` (default: true) - Prefix filename with category
- `release_append_timestamp` (default: true) - Add timestamp to release assets

## Authentication

GitHub token resolution order:
1. `GITHUB_TOKEN` or `GH_TOKEN` environment variable
2. `gh auth token` (GitHub CLI)
3. macOS Keychain: `security find-generic-password -s "GuploadGitHubToken"` (via `ghu` wrapper)

## Setup & Dependencies

### Install Audio Metadata Support (Optional)
```bash
pip3 install mutagen
```
Required for `use_audio_metadata` feature to extract artist/title from audio files.

### Example Configuration
See `config.example.json` for a complete configuration template with all options documented.

### Recommended Configuration for Clean Audio Uploads
```json
{
  "repo_path_prefix": "",
  "use_audio_metadata": true,
  "dedup_strategy": "none",
  "append_short_hash": false,
  "clean_filename": true,
  "verbose": false
}
```
This gives you clean filenames like `Audio/Pendulum - Witchcraft.mp3` without hashes or numbers.

## Development Commands

### Basic Usage
```bash
# Upload single file
./ghu /path/to/file.mp3

# Upload multiple files
./ghu file1.jpg file2.pdf file3.mp4

# Via stdin (paths, one per line)
echo "/path/to/file.mp3" | ./ghu

# Via Finder (macOS) - run without args, select files in Finder
./ghu
```

### Testing
```bash
# Test with small file (Contents API path)
./ghu test-small.txt

# Test with large file (Releases API path, must be 95MB+)
./ghu large-video.mp4

# Check logs
tail -f /tmp/gupload.log
```

### Debugging
```bash
# Test Python script directly (bypass wrapper)
python3 ghuploader.py /path/to/file.mp3

# Check token availability
gh auth token  # Should output token if logged in
security find-generic-password -s "GuploadGitHubToken" -w  # macOS Keychain

# Validate config
cat ~/.config/ghuploader/config.json | python3 -m json.tool
```

## Important Details

- **No duplicate uploads**: SHA1 hash suffix prevents filename collisions (configurable via `append_short_hash`)
- **Size limits**: Max 2GB per file (GitHub Releases limit)
- **Categorization**: Audio (mp3, m4a, flac, etc.), Images (png, jpg, etc.), Video (mp4, mov, etc.), Docs (pdf, txt, etc.), Archives (zip, tar, etc.), Other (fallback)
- **Git workflow**: Small files create commits automatically; large files attach to releases
- **Output**: Clipboard automatically receives output (macOS only via `pbcopy`)
- **Logs**: All uploads logged to `/tmp/gupload.log` with timestamps, args, token presence
- **Batch uploads**: Continues on error by default (`continue_on_error: true`), collecting all successful uploads
- **Metadata extraction**: Audio files can use ID3/metadata tags for cleaner filenames (requires mutagen)

## File Categories

Categorization logic in `ghuploader.py:95-107`:
- Extension-based first (AUDIO_EXT, IMAGE_EXT, VIDEO_EXT, DOC_EXT, ARCH_EXT)
- MIME type fallback if extension unknown
- Default to "Other" category

## Current State

Per git status, the repo contains:
- `uploads/Audio/` - Audio file uploads
- `uploads/Other/` - Miscellaneous file uploads
- Recent commits show automated uploads with timestamps
- `.specstory/` - SpecStory extension artifacts (AI chat history, not part of core functionality)
- `.crush/` - Unknown purpose (database file present, investigation needed if relevant)
