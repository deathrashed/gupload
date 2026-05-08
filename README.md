<div align="center">
  <img src="data/assets/icon.png" alt="Gupload Icon">
  <h1>Gupload</h1>
  <p>A powerful GitHub-based file hosting system that uploads files to GitHub repositories and returns markdown/HTML links. Perfect for hosting media files, scripts, documents, and more with automatic organization and smart naming.</p>
</div>

## 🚀 Quick Start (5 minutes)

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/Gupload.git
cd Gupload

# 2. Make scripts executable
chmod +x ghu scripts/*.sh

# 3. Authenticate with GitHub
gh auth login

# 4. Configure (edit with your GitHub username and repo)
mkdir -p ~/.config/ghuploader
cp data/config.example.json ~/.config/ghuploader/config.json
# Edit config.json with your settings

# 5. Upload a file
./ghu ~/example.png
```

✔ File uploaded to GitHub  
✔ Markdown/URL copied to clipboard  
✔ No server, no config sprawl

---

## Features

### Core Features
- 🚀 **Automatic Categorization** - Files organized by type (Audio, Images, Video, Scripts, Documents, Docs, Data, Archives, Other)
- 📦 **Script Language Organization** - Scripts organized by language (Python, Go, Ruby, AppleScript, Shell, JavaScript, TypeScript, etc.)
- 🏗️ **Package Structure Preservation** - Detects package/module structures (Python packages, Go modules, Ruby gems) and preserves folder hierarchy
- 🎵 **Smart Naming** - Automatically extracts artist/album names from file paths for audio files and images
- 🎨 **Artist Organization** - Optional organization of all artist files (audio, covers, logos) in artist folders
- 📁 **Image Subfolders** - Organizes covers, logos, and artist images into separate subfolders
- 📏 **Size Handling** - Small files (<95MB) via Contents API, large files (95MB-2GB) via Releases API
- 🎛️ **Interactive Menu** - Full-featured terminal menu with fzf search, repo browsing, custom naming, and more
- 📋 **Clipboard Integration** - Automatically copies markdown/URL links to clipboard (macOS)
- 🔐 **Secure Authentication** - Supports multiple authentication methods (environment variables, GitHub CLI, macOS Keychain)

### Advanced Features ⚡
- 🔄 **Batch URL Upload** - Upload multiple files from URLs at once with smart naming
- 🔍 **Duplicate Detection** - Check if files already uploaded before re-uploading
- 📝 **Upload Templates** - Save and reuse upload configurations for common workflows
- 📋 **Clipboard Monitor** - Auto-detect and upload files/URLs copied to clipboard
- 👁️ **File Preview** - View detailed file information before uploading
- 🔎 **Search & Filter** - Search upload history by filename, category, or date range
- 📊 **Export History** - Export upload history to CSV, JSON, or Markdown formats
- 🎨 **Gallery Generation** - Auto-generate image galleries and audio playlists
- ⭐ **Favorites System** - Quick access to frequently-used paths
- 📈 **Upload Statistics** - Track and analyze upload patterns

See [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) for complete guide.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [Usage](#usage)
- [File Organization](#file-organization)
- [Features in Detail](#features-in-detail)
- [Scripts](#scripts)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

<details>
<summary><strong>📦 Installation</strong> (Click to expand)</summary>

### Prerequisites

- Python 3.7+ (comes pre-installed on macOS)
- GitHub account with a repository for file hosting
- macOS (for Keychain integration and Finder selection)

### Setup

1. **Clone or download this repository:**
   ```bash
   # Standard clone (includes Uploads/ folder with all uploads)
   git clone https://github.com/YOUR_USERNAME/Gupload.git
   cd Gupload
   
   # Or clone without Uploads/ folder (recommended, keeps repo smaller)
   git clone --filter=blob:none --sparse https://github.com/YOUR_USERNAME/Gupload.git
   cd Gupload
   git sparse-checkout set --no-cone '/*' '!Uploads'
   ```
   
   **Note:** The `Uploads/` folder contains all uploaded files. If you clone without it, uploaded files will still be accessible via GitHub URLs (raw.githubusercontent.com), but won't be in your local repository.

2. **Make scripts executable:**
   ```bash
   chmod +x ghu scripts/*.sh
   ```

3. **Install optional dependencies:**
   ```bash
   pip3 install mutagen  # Optional: for audio metadata extraction
   ```

4. **Configure:**
   ```bash
   mkdir -p ~/.config/ghuploader
   cp data/config.example.json ~/.config/ghuploader/config.json
   # Edit config.json with your settings (see Configuration section)
   ```

</details>

<details>
<summary><strong>⚙️ Configuration</strong> (Click to expand)</summary>

Edit `~/.config/ghuploader/config.json` with your settings:

```json
{
  "owner": "your-github-username",
  "repo": "your-repo-name",
  "branch": "main",
  
  "use_path_for_generic_names": true,
  "use_path_for_audio_names": true,
  "organize_by_artist": false,
  "use_image_subfolders": true,
  
  "output_mode": "markdown",
  "also_audio_html": true,
  
  "contents_max_mb": 95,
  "release_tag": "gupload-uploads"
}
```

See `data/config.example.json` for all available configuration options.

### Key Configuration Options

- **`owner`** - Your GitHub username (required)
- **`repo`** - Repository name for hosting files (required)
- **`branch`** - Branch to upload files to (default: "main")
- **`organize_by_artist`** - If `true`, organizes all artist files (audio, images) into `Audio/{Artist}/` folders
- **`use_image_subfolders`** - If `true`, organizes images into `Images/Covers/`, `Images/Logos/`, `Images/Artists/`
- **`output_mode`** - Output format: `"markdown"`, `"url"`, or `"both"`
- **`contents_max_mb`** - Maximum file size for Contents API (default: 95MB). Larger files use Releases API.

</details>

<details>
<summary><strong>🔐 Authentication</strong> (Click to expand)</summary>

Gupload supports multiple secure authentication methods (in order of priority):

### 1. Environment Variables (Recommended for CI/CD)
```bash
export GITHUB_TOKEN="your_token_here"
# or
export GH_TOKEN="your_token_here"
```

### 2. GitHub CLI (Recommended for local use)
```bash
gh auth login
```
Gupload will automatically use your GitHub CLI authentication token.

### 3. macOS Keychain (For persistent local authentication)
```bash
security add-generic-password -s "GuploadGitHubToken" -w "YOUR_TOKEN" -a "$USER"
```

⚠️ **Security Note:** Never commit tokens to version control. Always use environment variables, GitHub CLI, or Keychain.

### Creating a GitHub Token

1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Select scopes: `repo` (full control of private repositories)
4. Copy the token immediately (you won't see it again)
5. Use one of the authentication methods above

</details>

## Usage

### Command Line

```bash
# Upload single file
./ghu /path/to/file.mp3

# Upload multiple files
./ghu file1.jpg file2.pdf file3.mp4

# Upload from URL with custom name
./ghu --name "Deteriorate - 1993 - Rotting in Hell.jpg" https://f4.bcbits.com/img/a1454706092_5.jpg

# Upload multiple URLs with custom names
./ghu --names "Cover 1.jpg" "Cover 2.jpg" https://example.com/cover1.jpg https://example.com/cover2.jpg

# Helper script for album covers (auto-formats name)
./scripts/upload-cover.sh https://f4.bcbits.com/img/a1454706092_5.jpg "Deteriorate" "1993" "Rotting in Hell"

# Via stdin (paths, one per line)
echo -e "/path/to/file1.mp3\n/path/to/file2.jpg" | ./ghu

# Via Finder (macOS) - run without args, select files in Finder
./ghu
```

### Interactive Menu

```bash
./scripts/gupload-menu.sh
```

The interactive menu provides:
- 📁 **File Upload** - Single file (fzf search or manual), multiple files, Finder selection, folder/archive
- 🔍 **Browse Repo** - List existing artists/files in repository, add files to existing paths
- 🎵 **Audio Tools** - Browse artists, upload artist assets (covers, logos), upload audio files
- ⚙️ **Configure** - Change clipboard output mode (markdown, URL, both)
- 📜 **View Logs** - View recent uploads or live log tail

### Quick Examples

```bash
# Upload an album cover
./ghu "/Volumes/Audio/Metal/C/Cold Steel/2023 - Deeper Into Greater Pain/cover.jpg"
# Output: ![Cold Steel - 2023 - Deeper Into Greater Pain.jpg](https://raw.githubusercontent.com/...)

# Upload a script
./ghu ~/Scripts/my-script.py
# Output: [my-script.py](https://raw.githubusercontent.com/.../Uploads/Scripts/Python/my-script.py)

# Upload multiple artist assets
./scripts/upload-artist-assets.sh "/Volumes/Audio/Metal/C/Cold Steel"
# Uploads all cover.jpg, logo.png, and artist.jpg files for the artist
```

<details>
<summary><strong>📁 File Organization</strong> (Click to expand)</summary>

### Automatic Categorization

Files are automatically organized into categories:

- **Audio** - `.mp3`, `.flac`, `.wav`, `.m4a`, etc.
- **Images** - `.png`, `.jpg`, `.svg`, `.webp`, etc.
- **Video** - `.mp4`, `.mov`, `.mkv`, `.webm`, etc.
- **Scripts** - Organized by language:
  - `Scripts/Python/` - Python scripts (`.py`)
  - `Scripts/Go/` - Go modules (`.go`, preserves module structure)
  - `Scripts/Ruby/` - Ruby scripts/gems (`.rb`, preserves gem structure)
  - `Scripts/Applescript/` - AppleScript files (`.applescript`, `.scpt`)
  - `Scripts/Shell/` - Shell scripts (`.sh`, `.bash`, `.zsh`)
  - `Scripts/JavaScript/` - JavaScript files (`.js`)
  - `Scripts/TypeScript/` - TypeScript files (`.ts`)
  - And more...
- **Documents** - Text files (`.txt`, `.md`, `.markdown`)
- **Docs** - Office documents (`.pdf`, `.doc`, `.docx`, `.xlsx`)
- **Data** - Data files (`.json`, `.yaml`, `.csv`, `.xml`)
- **Archives** - Archive files (`.zip`, `.tar.gz`, `.7z`)
- **Other** - Everything else

### Default Organization (by Category)

```
Uploads/
├── Audio/
├── Images/
│   ├── Covers/
│   ├── Logos/
│   └── Artists/
├── Video/
├── Scripts/
│   ├── Python/
│   ├── Go/
│   ├── Ruby/
│   └── ...
├── Documents/
├── Docs/
├── Data/
├── Archives/
└── Other/
```

**Note:** The `Uploads/` folder is excluded from git (via `.gitignore`) so users can clone the repository without personal uploads.

### Artist-Based Organization (Optional)

Enable `organize_by_artist: true` in config:

```
Uploads/
└── Audio/
    └── Cold Steel/
        ├── Cold Steel - Rotting Off.mp3
        ├── Cold Steel - 2023 - Deeper Into Greater Pain.jpg
        ├── coldsteel-logo.png
        └── coldsteel-artist.jpg
```

</details>

<details>
<summary><strong>✨ Features in Detail</strong> (Click to expand)</summary>

### Smart Naming

**Generic Image Files:**
- `logo.png` → `carnifex-logo.png` (extracts artist from path)
- `artist.jpg` → `Fat Joe artist.jpg` (with spaced format option)
- `cover.jpg` → `Cold Steel - 2023 - Deeper Into Greater Pain.jpg` (includes album)

**Audio Files:**
- `02. Livin' Fat.mp3` → `Fat Joe - Livin' Fat.mp3` (removes track numbers, adds artist)

**Package Structure:**
- Python packages with `__init__.py` preserve structure: `Uploads/Scripts/Python/mypackage/subpackage/module.py`
- Go modules with `go.mod` preserve structure: `Uploads/Scripts/Go/gomodule/subdir/handler.go`
- Ruby gems with `Gemfile` preserve structure: `Uploads/Scripts/Ruby/mygem/lib/mygem.rb`

### Size Handling

- **Small files (<95MB)**: Uploaded via GitHub Contents API → stored directly in repository
- **Large files (95MB-2GB)**: Uploaded via GitHub Releases API → attached to release (default tag: `gupload-uploads`)

### Output Formats

**Markdown (default):**
```markdown
[Cold Steel - Front to Enemy.mp3](https://raw.githubusercontent.com/...)
<audio controls src="https://raw.githubusercontent.com/..."></audio>

![Cold Steel - 2023 - Deeper Into Greater Pain.jpg](https://raw.githubusercontent.com/...)
```

**URL only:**
```
https://raw.githubusercontent.com/...
```

**Both:**
Includes both markdown and URL.

Output is automatically copied to clipboard (macOS).

</details>

## Scripts

All utility scripts are located in `scripts/`:

- **`gupload-menu.sh`** - Interactive menu for all upload operations
- **`upload-artist-assets.sh`** - Batch upload artist assets (covers, logos, artist images)
- **`list-repo-artists.py`** - List artists already in the repository (used by menu)

## Security

<details>
<summary><strong>🔒 Security Audit & Best Practices</strong> (Click to expand)</summary>

### Security Audit

This repository has been audited for security issues:

✅ **No exposed tokens or secrets found**
- No hardcoded GitHub tokens (ghp_* or github_pat_*)
- No API keys or passwords in code
- Configuration files excluded from git (`.gitignore`)
- Only documentation references to authentication

✅ **Secure Configuration**
- `.gitignore` properly configured to exclude sensitive files
- `config.json` excluded from version control
- Log files excluded from git
- Uploads folder excluded from git

### Security Best Practices

#### Authentication Methods (in order of preference)

1. **GitHub CLI** (Recommended for local use)
   ```bash
   gh auth login
   ```

2. **Environment Variables** (Recommended for CI/CD)
   ```bash
   export GITHUB_TOKEN="your_token_here"
   # or
   export GH_TOKEN="your_token_here"
   ```

3. **macOS Keychain** (For persistent local storage)
   ```bash
   security add-generic-password -s "GuploadGitHubToken" -w "YOUR_TOKEN" -a "$USER"
   ```

#### Token Security

⚠️ **Critical Guidelines:**

- ❌ **Never commit tokens** to version control
- ❌ **Never hardcode tokens** in scripts or config files
- ❌ **Never share tokens** via insecure channels (email, chat, etc.)
- ❌ **Never commit `config.json`** with actual tokens
- ✅ **Use environment variables** or GitHub CLI (preferred)
- ✅ **Limit token scopes** - Only grant necessary permissions (`repo` scope for private repos)
- ✅ **Rotate tokens regularly** - Especially if exposed or shared
- ✅ **Use repository secrets** in CI/CD environments (GitHub Actions secrets, etc.)
- ✅ **Review uploaded files** before making repository public

#### Repository Security

- **Public Repositories**: All uploaded files are publicly accessible via GitHub URLs
- **Private Repositories**: Files are only accessible with proper authentication
- **Large Files**: Files >95MB are uploaded as release assets (check release visibility settings)

### Creating a GitHub Token

1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Select scopes: `repo` (full control of private repositories) - minimum required
4. Copy the token immediately (you won't see it again)
5. Use one of the authentication methods above - **never commit it**

### If You Accidentally Commit a Token

1. **Revoke the token immediately** in GitHub settings
2. **Create a new token** with the same permissions
3. **Update your authentication** method with the new token
4. If the token was pushed to a public repo, consider it compromised and create a new one

### File Security

- Uploaded files are committed to the repository via GitHub API
- Files in `Uploads/` folder are excluded from git (via `.gitignore`)
- Review file contents before uploading (especially scripts or configs)

</details>

<details>
<summary><strong>🛠️ Troubleshooting</strong> (Click to expand)</summary>

### "Bad credentials" error
- Verify your token is valid and has correct permissions
- Try re-authenticating: `gh auth login`
- Check if token expired (tokens can expire if set to expire)

### "File too large" error
- Large files (>95MB) are automatically handled via Releases API
- Very large files (>2GB) are not supported (GitHub limit)

### Script not found errors
- Ensure scripts are executable: `chmod +x ghu scripts/*.sh`
- Check that you're in the correct directory or scripts are in PATH

### Upload failures
- Check repository permissions (you need write access)
- Verify branch name in config matches your repository
- Check network connectivity
- Review logs: `/tmp/gupload.log`

### Package structure not preserved
- Ensure package indicators exist (`__init__.py`, `go.mod`, `Gemfile`, etc.)
- Upload all related files together for best results

</details>

<details>
<summary><strong>🤝 Contributing</strong> (Click to expand)</summary>

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

</details>

## License

This project is licensed under the MIT License - see the LICENSE file for details.

<details>
<summary><strong>📂 Repository Structure</strong> (Click to expand)</summary>

```
Gupload/
├── ghu                      # Main wrapper script (macOS integration)
│
├── scripts/                 # All scripts
│   ├── ghuploader.py        # Core Python upload logic
│   ├── gupload-menu.sh      # Interactive menu tool
│   ├── upload-artist-assets.sh  # Batch upload artist assets
│   └── list-repo-artists.py     # List artists from repo
│
├── data/                    # Data and documentation
│   ├── config.example.json  # Example configuration file
│   ├── docs/                # Documentation files
│   └── logs/                # Log files (if using local logging)
│
└── Uploads/                 # All uploads go here (git ignored, personal files)
    └── [category]/          # Category folders (Audio, Images, Scripts, etc.)
```

## Additional Documentation

- 📖 **[ADVANCED_FEATURES.md](ADVANCED_FEATURES.md)** - Complete guide to all advanced features (batch upload, templates, search, export, etc.)
- 📋 **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Fast reference for common tasks and workflows
- 📝 **[MENU_IMPROVEMENTS.md](MENU_IMPROVEMENTS.md)** - Detailed changelog of menu system improvements
- 📚 **`data/docs/USAGE.md`** - Detailed usage guide
- 🏗️ **`data/docs/STRUCTURE.md`** - Repository structure documentation
- 🔧 **`CLAUDE.md`** - Development documentation

</details>

---

**Made with ❤️ for easy file hosting on GitHub**
