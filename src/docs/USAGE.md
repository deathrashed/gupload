# Gupload Usage Guide

## Basic Usage

### Command Line

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

### Interactive Menu

```bash
./scripts/gupload-menu.sh
```

The interactive menu provides:
- File search with fzf
- Custom naming options
- Browse existing uploads by artist
- Batch upload options
- Configuration options

## Upload Options

### Default Naming
Files are automatically named based on:
- Path structure (for audio files: artist and album from path)
- File metadata (if available and enabled)
- Category-based organization

### Custom Naming
When uploading via the menu, you can choose:
1. **Default** - Auto-generated from path/metadata
2. **Custom filename** - Specify exact filename
3. **Custom path** - Specify folder structure (e.g., `Scripts/MyTool/script.sh`)

## File Organization

### By Category (Default)
```
Audio/
Images/
  ├── Covers/
  ├── Logos/
  └── Artists/
Docs/
Scripts/
Archives/
Other/
```

### By Artist (Optional)
Enable `organize_by_artist: true` in config:
```
Audio/
  ├── Artist Name/
  │   ├── audio files
  │   ├── covers
  │   ├── logos
  │   └── artist images
```

## Output Format

### Markdown (Default)
```markdown
[filename.mp3](https://raw.githubusercontent.com/.../file.mp3)
![cover.jpg](https://raw.githubusercontent.com/.../cover.jpg)
```

### URL Only
```
https://raw.githubusercontent.com/.../file.mp3
```

### Both
Includes both markdown and URL.

Output is automatically copied to clipboard (macOS).
