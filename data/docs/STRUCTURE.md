# Gupload Repository Structure

## Directory Layout

```
Gupload/
├── Root Files
│   ├── ghu                      # Main bash wrapper script
│   ├── README.md                # Main project documentation
│   ├── CLAUDE.md                # Development documentation
│   └── .gitignore               # Git ignore rules
│
├── scripts/                      # All scripts
│   ├── ghuploader.py            # Core Python upload logic
│   ├── gupload-menu.sh          # Interactive menu tool
│   ├── upload-artist-assets.sh  # Batch upload artist assets
│   └── list-repo-artists.py     # List artists from GitHub repo
│
├── data/                         # Data and documentation
│   ├── config.example.json      # Example configuration template
│   ├── docs/                     # Documentation files
│   │   ├── USAGE.md             # Usage guide
│   │   └── STRUCTURE.md         # This file
│   └── logs/                     # Local log files (if used)
│
└── Uploads/                      # All uploads go here (git ignored, personal files)
    └── [category]/               # Category folders:
                                  #   - Audio: Audio files (.mp3, .flac, etc.)
                                  #   - Images: Image files (.png, .jpg, etc.)
                                  #   - Video: Video files (.mp4, .mov, etc.)
                                  #   - Scripts: Scripts organized by language:
                                  #     * Uploads/Scripts/Python/ - Python scripts (.py)
                                  #     * Uploads/Scripts/Go/ - Go modules (.go, preserves module structure)
                                  #     * Uploads/Scripts/Ruby/ - Ruby scripts/gems (.rb, preserves gem structure)
                                  #     * Uploads/Scripts/Applescript/ - AppleScript files (.applescript, .scpt)
                                  #     * Uploads/Scripts/Shell/ - Shell scripts (.sh, .bash, .zsh)
                                  #     * Uploads/Scripts/JavaScript/ - JavaScript/TypeScript (.js, .ts)
                                  #     * Uploads/Scripts/*/ - Other languages in language-specific folders
                                  #     Package/module structures are preserved (e.g., Uploads/Scripts/Python/mypackage/module.py)
                                  #   - Documents: Text files (.txt, .md, etc.)
                                  #   - Docs: Office documents (.pdf, .doc, etc.)
                                  #   - Data: Data files (.json, .yaml, .csv, etc.)
                                  #   - Archives: Archives (.zip, .tar.gz, etc.)
                                  #   - Other: Everything else
                                  #
                                  # Note: Uploads/ folder is excluded from git via .gitignore
                                  #       This allows users to clone the repository without personal uploads
```

## File Purposes

### Core Files (Root)
- **ghu** - Bash wrapper for macOS integration, handles token retrieval and Finder selection

### Scripts (scripts/)
- **ghuploader.py** - Main upload logic, GitHub API interaction, file naming, categorization
- **gupload-menu.sh** - Full-featured interactive menu with fzf search, repo browsing, custom naming
- **upload-artist-assets.sh** - Batch upload script for artist assets (covers, logos, artist images)
- **list-repo-artists.py** - Helper script to query GitHub API and list artists already in repo

### Configuration (data/)
- **config.example.json** - Configuration template with all available options

### Documentation (data/docs/)
- **USAGE.md** - User guide for using Gupload
- **STRUCTURE.md** - Repository structure documentation

## Script Path Resolution

All scripts use relative path resolution:
- Scripts in `scripts/` find repo root by going up one directory
- Works whether scripts are accessed directly or via symlinks
- Toolkit directory `~/Scripts/Riley/Gupload/` contains symlinks to scripts
