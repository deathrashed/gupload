#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
import shutil
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error

CONFIG_PATH = os.path.expanduser("~/.config/gupload/config.json")
DATA_DIR = os.path.expanduser("~/.config/gupload/data")
RECENT_FILE = os.path.join(DATA_DIR, "recent.json")

AUDIO_EXT = {".mp3",".m4a",".aac",".wav",".flac",".ogg",".opus",".aiff",".alac",".wma"}
IMAGE_EXT = {".png",".jpg",".jpeg",".webp",".gif",".tif",".tiff",".bmp",".svg",".heic",".avif"}
VIDEO_EXT = {".mp4",".mov",".mkv",".webm",".avi",".m4v"}
SCRIPT_EXT = {".sh",".bash",".zsh",".fish",".py",".pyw",".rb",".pl",".pm",".js",".ts",".jsx",".tsx",".php",".lua",".r",".R",".swift",".go",".rs",".java",".c",".cpp",".cc",".cxx",".h",".hpp",".cs",".m",".mm",".kt",".scala",".clj",".vim",".ps1",".psm1",".psd1",".bat",".cmd",".applescript",".scpt"}
DOC_EXT   = {".pdf",".rtf",".doc",".docx",".ppt",".pptx",".xls",".xlsx",".odt",".ods",".odp"}
TEXT_EXT  = {".txt",".md",".markdown",".rst",".org",".tex",".latex"}
DATA_EXT  = {".csv",".json",".yaml",".yml",".toml",".xml",".ini",".cfg",".conf",".config"}
ARCH_EXT  = {".zip",".7z",".rar",".tar",".gz",".tgz",".bz2",".xz"}

def eprint(*a):
    print(*a, file=sys.stderr)

def load_config():
    if not os.path.exists(CONFIG_PATH):
        eprint(f"Missing config: {CONFIG_PATH}")
        sys.exit(2)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def run(cmd):
    return subprocess.check_output(cmd, text=True).strip()

def download_url(url, output_path=None):
    """Download a file from a URL to a temporary or specified file path.
    
    Args:
        url: URL to download from
        output_path: Optional path to save file. If None, creates a temp file.
    
    Returns:
        Path to downloaded file
        
    Raises:
        Exception if download fails
    """
    try:
        # Create request with headers to avoid blocking
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        with urllib.request.urlopen(req, timeout=30) as response:
            # Get filename from Content-Disposition header or URL
            content_disposition = response.headers.get('Content-Disposition', '')
            if output_path is None:
                # Try to extract filename from URL or Content-Disposition
                filename = None
                if content_disposition:
                    match = re.search(r'filename=["\']?([^"\']+)["\']?', content_disposition)
                    if match:
                        filename = match.group(1)
                
                if not filename:
                    # Extract from URL
                    parsed = urllib.parse.urlparse(url)
                    filename = os.path.basename(parsed.path)
                    if not filename or '.' not in filename:
                        # Guess extension from Content-Type
                        content_type = response.headers.get('Content-Type', '')
                        ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
                        filename = f"downloaded{ext}"
                
                # Create temp file with proper extension
                fd, output_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1], prefix='gupload_')
                os.close(fd)
            
            # Download to file
            with open(output_path, 'wb') as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
            
            return output_path
    except Exception as e:
        raise RuntimeError(f"Failed to download {url}: {e}")

def is_url(path):
    """Check if the path is a URL."""
    return path.startswith('http://') or path.startswith('https://')

def get_token(cfg):
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        v = os.environ.get(k)
        if v:
            return v
    if cfg.get("allow_gh_cli_token", True):
        try:
            return run(["gh", "auth", "token"])
        except Exception:
            pass
    eprint("No GitHub token found. Set GITHUB_TOKEN or run `gh auth login`.")
    sys.exit(2)

def api_request(method, url, token, data=None, headers=None):
    h = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gupload",
    }
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if raw:
                return json.loads(raw.decode("utf-8"))
            return None
    except urllib.error.HTTPError as err:
        msg = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {err.code}\n{msg}") from None

def sanitize_filename(name: str, preserve_spaces: bool = False) -> str:
    """Sanitize filename for safe filesystem usage.
    
    Args:
        name: Original filename
        preserve_spaces: If True, keep spaces (for titles). If False, replace with hyphens.
    """
    name = name.strip()
    if not preserve_spaces:
        # Standard sanitization: replace spaces with hyphens, remove invalid chars
        name = name.replace(" ", "-")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name)
        name = re.sub(r"-{2,}", "-", name).strip("-")
    else:
        # For titles, keep spaces but remove invalid filesystem chars
        # Keep apostrophes and common punctuation used in song titles
        name = re.sub(r'[<>:"|?*\\]', "", name)
        name = re.sub(r"\s+", " ", name)  # Collapse multiple spaces
        # Remove leading/trailing spaces and periods
        name = name.strip(" .")
    return name or "file"

def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def is_generic_filename(filename):
    """Check if filename is a generic/common name that might conflict."""
    base = os.path.splitext(filename)[0].lower()
    generic_names = {"logo", "artist", "cover", "artwork", "art", "image", "photo", "picture", "pic", "img"}
    return base in generic_names

def get_image_type(filename):
    """Determine image type from filename. Returns 'cover', 'logo', 'artist', or None."""
    base = os.path.splitext(filename)[0].lower()
    if base in {"cover", "artwork", "art"}:
        return "cover"
    elif base in {"logo"}:
        return "logo"
    elif base in {"artist"}:
        return "artist"
    return None

def extract_album_from_path(path):
    """Extract album name from file path. Returns album directory name or None."""
    parent_dir = os.path.dirname(path)
    if not parent_dir or parent_dir == "/":
        return None
    
    # Get the parent directory (should be the album folder)
    album_dir = os.path.basename(parent_dir)
    
    # Check if it looks like an album directory (contains year pattern like "1993 - " or "2025 - ")
    if re.match(r"^\d{4}\s*-\s*.+", album_dir):
        return album_dir
    
    return None

def extract_artist_from_path(path, skip_album_dirs=True):
    """Extract artist name from file path. Returns the artist directory name or None.
    
    Args:
        path: File path
        skip_album_dirs: If True, skip directories that look like album folders
                        (e.g., "1993 - Represent", "2025 - Destination Extinction")
    """
    # Get the parent directory (the directory containing the file)
    parent_dir = os.path.dirname(path)
    if not parent_dir or parent_dir == "/":
        return None
    
    # Get the last component of the path (the folder containing the file)
    candidate = os.path.basename(parent_dir)
    
    # Check if this looks like an album directory (contains year pattern like "1993 - " or "2025 - ")
    if skip_album_dirs and re.match(r"^\d{4}\s*-\s*.+", candidate):
        # This is an album folder, go up one more level to get artist
        grandparent = os.path.dirname(parent_dir)
        if grandparent and grandparent != "/":
            candidate = os.path.basename(grandparent)
        else:
            return None
    
    # Skip if it's just a single letter (like "C", "E", "F" in the path structure)
    if len(candidate) <= 1:
        # Try going up one more level
        great_grandparent = os.path.dirname(os.path.dirname(parent_dir))
        if great_grandparent and great_grandparent != "/":
            candidate = os.path.basename(great_grandparent)
        else:
            return None
    
    return candidate if candidate else None

def sanitize_artist_name(name: str) -> str:
    """Sanitize artist name for filename prefix - compact format (no hyphens)."""
    # Remove special characters, keep alphanumeric only
    name = re.sub(r"[^A-Za-z0-9\s]+", "", name)
    # Remove extra spaces
    name = re.sub(r"\s+", "", name)
    # Lowercase
    return name.lower()

def remove_track_number(filename: str) -> str:
    """Remove leading track number patterns like '01. ', '02.', '1. ', etc."""
    # Match patterns like: "01. ", "02.", "1. ", "10. ", etc.
    # This removes leading numbers followed by optional space and dot
    cleaned = re.sub(r"^\d{1,3}\.?\s*", "", filename)
    return cleaned.strip()

def clipboard_set(text: str):
    # macOS, Wayland, X11, Termux (Android) - first one installed wins.
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"], ["termux-clipboard-set"]):
        if shutil.which(cmd[0]):
            try:
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"))
            except Exception:
                pass
            return

def log_upload(filepath, filename, url, category):
    """Log successful upload to recent uploads file."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)

        # Load existing recent uploads
        if os.path.exists(RECENT_FILE):
            with open(RECENT_FILE, 'r') as f:
                recent = json.load(f)
        else:
            recent = []

        # Add new upload
        upload_info = {
            'filepath': filepath,
            'filename': filename,
            'url': url,
            'category': category,
            'timestamp': dt.datetime.now().isoformat()
        }
        recent.append(upload_info)

        # Keep only last 100 uploads
        if len(recent) > 100:
            recent = recent[-100:]

        # Save back to file
        with open(RECENT_FILE, 'w') as f:
            json.dump(recent, f, indent=2)
    except Exception:
        # Don't fail upload if logging fails
        pass

def sanitize_repo_path(raw: str) -> str:
    """Sanitize a user-supplied repo-relative folder path for --path.

    Strips surrounding whitespace/slashes, collapses repeated slashes,
    and drops any '..' / '.' segments (no parent traversal, no absolute
    escape). Raises ValueError if nothing usable remains.
    """
    raw = raw.strip().strip("/")
    parts = [p for p in raw.split("/") if p not in ("", ".", "..")]
    cleaned = "/".join(parts)
    if not cleaned:
        raise ValueError("Empty or invalid path after sanitization.")
    return cleaned


def build_jsdelivr_url(owner: str, repo: str, branch: str, remote_path: str) -> str:
    """Build a jsdelivr CDN URL for a file tracked via the contents API.

    Not valid for release assets (jsdelivr has no equivalent for those).
    """
    path = remote_path.lstrip("/")
    return f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}"


def commit_message_for(category: str, filename: str) -> str:
    return f"{category.lower()} ⋅ {filename}"


def release_prefix_for(category: str, root: str) -> str:
    return f"{category.lower()}-{root}"


def render_formats(formats, filename, url, is_image, is_audio, jsdelivr_url=None):
    """Render a list of output format keys into display lines.

    Returns (lines, warnings). Unknown/unavailable formats (e.g.
    'jsdelivr' with no jsdelivr_url) are skipped and produce a warning
    instead of raising, so a multi-file/multi-format run doesn't abort.
    """
    lines = []
    warnings = []
    for fmt in formats:
        if fmt == "mdlink":
            lines.append(f"[{filename}]({url})")
        elif fmt == "mdimage":
            lines.append(f"![{filename}]({url})")
        elif fmt == "literal":
            lines.append(url)
        elif fmt == "html":
            if is_image:
                lines.append(f'<img src="{url}">')
            elif is_audio:
                lines.append(f'<audio controls src="{url}"></audio>')
            else:
                lines.append(f'<a href="{url}">{filename}</a>')
        elif fmt == "jsdelivr":
            if jsdelivr_url:
                lines.append(jsdelivr_url)
            else:
                warnings.append(
                    f"jsdelivr format unavailable for {filename} "
                    "(release assets have no jsdelivr equivalent) - skipped"
                )
        else:
            warnings.append(f"Unknown format '{fmt}' - skipped")
    return lines, warnings


DEFAULT_TAXONOMY_RULES = [
    {"match": r"^(licen[cs]e|copying|unlicense|notice)(\..*)?$", "path": "files/licenses"},
    {"match": r"\.(ico|icns)$", "path": "icons"},
]


def taxonomy_path_for(cfg, path: str):
    """Return a taxonomy folder (e.g. 'files/licenses') for a file, or None.

    Rules are regexes tested case-insensitively against the basename. User
    rules from cfg['taxonomy_rules'] are checked before the built-in ones.
    """
    name = os.path.basename(path)
    rules = list(cfg.get("taxonomy_rules") or []) + DEFAULT_TAXONOMY_RULES
    for rule in rules:
        try:
            if re.search(rule["match"], name, re.IGNORECASE):
                return rule["path"].strip("/").lower()
        except (KeyError, re.error):
            continue
    return None


def category_for_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in AUDIO_EXT: return "Audio"
    if ext in IMAGE_EXT: return "Images"
    if ext in VIDEO_EXT: return "Video"
    if ext in SCRIPT_EXT: return "Scripts"
    if ext in TEXT_EXT: return "Documents"
    if ext in DOC_EXT: return "Docs"
    if ext in DATA_EXT: return "Data"
    if ext in ARCH_EXT: return "Archives"
    # fallback by mimetype
    mt = mimetypes.guess_type(path)[0] or ""
    if mt.startswith("audio/"): return "Audio"
    if mt.startswith("image/"): return "Images"
    if mt.startswith("video/"): return "Video"
    # Extensionless files: try a real content sniff (python-magic) before
    # falling back to the plain shebang check.
    if not ext:
        magic_cat = category_from_magic(path)
        if magic_cat:
            return magic_cat
        try:
            with open(path, "rb") as f:
                first_bytes = f.read(2)
                # Check for shebang
                if first_bytes == b"#!":
                    return "Scripts"
        except Exception:
            pass
    return "Other"


def category_from_magic(path: str):
    """Best-effort content-based category for an extensionless file,
    using python-magic/libmagic. Returns None if the library isn't
    available or the MIME type doesn't map to a known category (caller
    falls back to the shebang check either way).
    """
    try:
        import magic
    except ImportError:
        return None
    try:
        mt = magic.from_file(path, mime=True) or ""
    except Exception:
        return None
    if mt.startswith("audio/"): return "Audio"
    if mt.startswith("image/"): return "Images"
    if mt.startswith("video/"): return "Video"
    if mt == "text/x-shellscript" or mt == "text/x-script.python": return "Scripts"
    if mt.startswith("text/"): return "Documents"
    if mt in ("application/zip", "application/x-tar", "application/gzip"): return "Archives"
    return None

def extract_audio_metadata(path: str):
    """Extract artist and title from audio file metadata. Returns (artist, title) or (None, None)."""
    try:
        from mutagen import File
        audio = File(path, easy=True)
        if audio is None:
            return None, None

        # Try common tag formats
        artist = None
        title = None

        # mutagen.File with easy=True returns a dict-like interface
        if hasattr(audio, 'tags') and audio.tags:
            # Try various artist tags
            for key in ['artist', 'ARTIST', 'Artist', 'TPE1', 'albumartist', 'ALBUMARTIST']:
                val = audio.tags.get(key)
                if val:
                    artist = val[0] if isinstance(val, list) else str(val)
                    break

            # Try various title tags
            for key in ['title', 'TITLE', 'Title', 'TIT2']:
                val = audio.tags.get(key)
                if val:
                    title = val[0] if isinstance(val, list) else str(val)
                    break

        return artist, title
    except ImportError:
        # mutagen not installed, silently fall back
        return None, None
    except Exception:
        # Any other error, fall back silently
        return None, None

def get_script_language_subfolder(ext: str) -> str:
    """Get language subfolder name for a script file extension."""
    ext_lower = ext.lower()
    language_map = {
        ".py": "Python",
        ".pyw": "Python",
        ".go": "Go",
        ".rb": "Ruby",
        ".applescript": "Applescript",
        ".scpt": "Applescript",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".jsx": "JavaScript",
        ".tsx": "TypeScript",
        ".sh": "Shell",
        ".bash": "Shell",
        ".zsh": "Shell",
        ".fish": "Shell",
        ".php": "PHP",
        ".lua": "Lua",
        ".pl": "Perl",
        ".pm": "Perl",
        ".r": "R",
        ".R": "R",
        ".swift": "Swift",
        ".rs": "Rust",
        ".java": "Java",
        ".c": "C",
        ".cpp": "C++",
        ".cc": "C++",
        ".cxx": "C++",
        ".h": "C",
        ".hpp": "C++",
        ".cs": "C#",
        ".m": "Objective-C",
        ".mm": "Objective-C++",
        ".kt": "Kotlin",
        ".scala": "Scala",
        ".clj": "Clojure",
        ".vim": "Vim",
        ".ps1": "PowerShell",
        ".psm1": "PowerShell",
        ".psd1": "PowerShell",
        ".bat": "Batch",
        ".cmd": "Batch",
    }
    return language_map.get(ext_lower, "Scripts")

def detect_package_structure(local_path: str) -> tuple:
    """Detect if file is part of a package/module structure.
    
    Returns:
        (is_package, package_root, relative_path) tuple
        - is_package: bool indicating if file is part of a package
        - package_root: absolute path to package root, or None
        - relative_path: relative path from package root, or None
    """
    file_dir = os.path.dirname(local_path)
    file_ext = os.path.splitext(local_path)[1].lower()
    filename = os.path.basename(local_path)
    
    # Package detection indicators by language
    python_indicators = {"__init__.py", "setup.py", "setup.cfg", "pyproject.toml", "Pipfile", "requirements.txt", "requirements-dev.txt", "poetry.lock", "Pipfile.lock"}
    go_indicators = {"go.mod", "go.sum", "go.work"}
    ruby_indicators = {"Gemfile", "Gemfile.lock", "Rakefile", "rakefile", ".gemspec"}
    
    # Walk up the directory tree to find package root
    current_dir = file_dir
    visited_dirs = set()
    
    while current_dir and current_dir != "/" and current_dir not in visited_dirs:
        visited_dirs.add(current_dir)
        
        # Check for package indicators
        dir_contents = set(os.listdir(current_dir)) if os.path.isdir(current_dir) else set()
        
        # Python package/module detection
        if file_ext in {".py", ".pyw"}:
            # Check for Python package indicators (excluding __init__.py for now)
            non_init_indicators = python_indicators - {"__init__.py"}
            if any(indicator in dir_contents for indicator in non_init_indicators):
                # Found a project-level indicator (setup.py, requirements.txt, etc.)
                rel_path = os.path.relpath(local_path, current_dir)
                return True, current_dir, rel_path
            
            # Check for package structure (multiple .py files or __init__.py)
            py_files = [f for f in dir_contents if f.endswith((".py", ".pyw"))]
            if "__init__.py" in dir_contents or len(py_files) > 1:
                # Check if parent also has __init__.py (find outermost package)
                parent_dir = os.path.dirname(current_dir)
                if parent_dir and parent_dir != current_dir and os.path.isdir(parent_dir):
                    parent_contents = set(os.listdir(parent_dir)) if os.path.isdir(parent_dir) else set()
                    if "__init__.py" in parent_contents:
                        # Parent is also a package, continue searching
                        pass
                    else:
                        # This is the outermost package root
                        rel_path = os.path.relpath(local_path, current_dir)
                        return True, current_dir, rel_path
                else:
                    # This is the root, preserve from here
                    rel_path = os.path.relpath(local_path, current_dir)
                    return True, current_dir, rel_path
        
        # Go module detection
        if file_ext == ".go":
            if any(indicator in dir_contents for indicator in go_indicators):
                # This is a Go module, preserve structure from this root
                rel_path = os.path.relpath(local_path, current_dir)
                return True, current_dir, rel_path
            # Also check if multiple .go files in same directory (likely a package)
            go_files = [f for f in dir_contents if f.endswith(".go")]
            if len(go_files) > 1:
                # Multiple .go files = package, preserve directory structure
                rel_path = os.path.relpath(local_path, current_dir)
                return True, current_dir, rel_path
        
        # Ruby gem/project detection
        if file_ext == ".rb":
            if any(indicator in dir_contents for indicator in ruby_indicators):
                # This is a Ruby project, preserve structure from this root
                rel_path = os.path.relpath(local_path, current_dir)
                return True, current_dir, rel_path
            # Check if multiple .rb files in same directory (likely a module)
            rb_files = [f for f in dir_contents if f.endswith(".rb")]
            if len(rb_files) > 1:
                rel_path = os.path.relpath(local_path, current_dir)
                return True, current_dir, rel_path
        
        # AppleScript - if both .applescript and .scpt exist together, preserve structure
        if file_ext in {".applescript", ".scpt"}:
            applescript_files = [f for f in dir_contents if f.endswith((".applescript", ".scpt"))]
            if len(applescript_files) > 1:
                # Multiple AppleScript files together, preserve structure
                rel_path = os.path.relpath(local_path, current_dir)
                return True, current_dir, rel_path
        
        # Move up one directory
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:  # Reached root
            break
        current_dir = parent_dir
    
    # Not part of a package, return as standalone file
    return False, None, None

def check_file_exists_remote(cfg, token, remote_path):
    """Check if a file already exists in the repo. Returns True if exists, False otherwise."""
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")
    
    # URL-encode each path component separately
    path_parts = remote_path.split("/")
    encoded_parts = [urllib.parse.quote(part, safe="") for part in path_parts]
    encoded_path = "/".join(encoded_parts)
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}?ref={branch}"

    try:
        api_request("GET", url, token)
        return True  # File exists
    except Exception:
        return False  # File doesn't exist or other error

def build_repo_path(cfg, local_path, token=None, custom_name=None, override_path=None):
    base = cfg.get("repo_path_prefix", "")
    # Always use lowercase uploads/ as the root folder for uploads.
    uploads_root = "uploads"
    cat = category_for_path(local_path)
    if not override_path:
        # Taxonomy rules (licenses -> files/licenses, .ico -> icons, ...)
        # behave like a built-in path override.
        override_path = taxonomy_path_for(cfg, local_path)
    remote_cat = override_path if override_path else cat.lower()

    # If custom name provided, use it directly (with proper extension)
    if custom_name:
        # Preserve original extension if custom_name doesn't have one
        ext = os.path.splitext(local_path)[1]
        if not os.path.splitext(custom_name)[1]:
            custom_name = custom_name + ext
        # Sanitize the custom name
        fname = sanitize_filename(custom_name, preserve_spaces=True)
        # Build path with custom name
        if base:
            return f"{base}/{uploads_root}/{remote_cat}/{fname}", cat
        else:
            return f"{uploads_root}/{remote_cat}/{fname}", cat

    # Get original filename before sanitization (needed for audio track number removal)
    original_basename = os.path.basename(local_path)
    fname = sanitize_filename(original_basename)
    ext = os.path.splitext(fname)[1]
    base_fname = os.path.splitext(fname)[0]
    # Keep original base name (before sanitization) for audio processing
    original_base = os.path.splitext(original_basename)[0]

    # Check if filename is generic (logo.png, artist.jpg, cover.jpg, etc.) and extract info from path
    if cfg.get("use_path_for_generic_names", True) and is_generic_filename(fname):
        image_type = get_image_type(original_basename)
        artist = extract_artist_from_path(local_path)
        
        # Special handling for album covers - include album name
        if image_type == "cover":
            album = extract_album_from_path(local_path)
            if artist and album:
                # Format: "Artist - Album Name.ext"
                artist_clean = sanitize_filename(artist, preserve_spaces=True)
                album_clean = sanitize_filename(album, preserve_spaces=True)
                fname = f"{artist_clean} - {album_clean}{ext}"
            elif artist:
                # Fallback to just artist if no album found
                use_spaced_format = cfg.get("generic_name_spaced_format", True)
                if use_spaced_format:
                    artist_clean = artist.strip()
                    fname = f"{artist_clean} cover{ext}"
                else:
                    artist_clean = sanitize_artist_name(artist)
                    if artist_clean:
                        fname = f"{artist_clean}-cover{ext}"
        elif artist:
            # For logos and artist images
            use_spaced_format = cfg.get("generic_name_spaced_format", True)
            if use_spaced_format:
                # "Artist Name filename.ext" format (with spaces, capitalized)
                artist_clean = artist.strip()
                fname = f"{artist_clean} {base_fname}{ext}"
            else:
                # "artistname-filename.ext" format (compact, lowercase, no spaces)
                artist_clean = sanitize_artist_name(artist)
                if artist_clean:
                    fname = f"{artist_clean}-{base_fname}{ext}"

    # For audio files, handle path-based artist extraction and track number removal
    if cat == "Audio":
        # Try metadata first if enabled
        use_metadata = cfg.get("use_audio_metadata", False)
        artist_from_metadata = None
        title_from_metadata = None
        
        if use_metadata:
            artist_from_metadata, title_from_metadata = extract_audio_metadata(local_path)
            if artist_from_metadata and title_from_metadata:
                # Create "Artist - Title.ext" format from metadata
                fname = sanitize_filename(f"{artist_from_metadata} - {title_from_metadata}") + ext
        
        # If metadata not available/used, try path-based extraction
        if not (use_metadata and artist_from_metadata and title_from_metadata):
            if cfg.get("use_path_for_audio_names", True):
                artist = extract_artist_from_path(local_path)
                if artist:
                    # Remove track number from original base filename (before sanitization)
                    title_without_track = remove_track_number(original_base)
                    if title_without_track:
                        # Format as "Artist - Title.ext" with proper sanitization
                        # Sanitize artist (preserve spaces) and title (preserve spaces) separately
                        artist_clean = sanitize_filename(artist, preserve_spaces=True)
                        title_clean = sanitize_filename(title_without_track, preserve_spaces=True)
                        # Combine artist and title
                        fname = f"{artist_clean} - {title_clean}{ext}"
                    else:
                        # If no title after removing track number, just use artist
                        fname = sanitize_filename(artist) + ext

    # Optional: strip common garbage patterns (very conservative)
    if cfg.get("clean_filename", True):
        # remove bracket tags like [MacKed], (1080p), etc. but keep extension
        root, ext = os.path.splitext(fname)
        root = re.sub(r"[\[\(].{1,40}?[\]\)]", "", root).strip("-_. ")
        root = re.sub(r"-{2,}", "-", root).strip("-")
        fname = (root or "file") + ext

    # Collision safety strategies
    dedup = cfg.get("dedup_strategy", "hash")  # "hash", "sequential", or "none"

    if dedup == "hash" and cfg.get("append_short_hash", True):
        # Original behavior: append hash
        short = sha1_file(local_path)[:8]
        root, ext = os.path.splitext(fname)
        fname = f"{root}-{short}{ext}"
    elif dedup == "sequential" and token:
        # Check remote and append number if exists
        root, ext = os.path.splitext(fname)
        # Use lowercase uploads/ as root for path checks
        uploads_root = "uploads"
        base_path = f"{base}/{uploads_root}/{remote_cat}" if base else f"{uploads_root}/{remote_cat}"

        # Check if base filename exists
        test_path = f"{base_path}/{fname}"
        if check_file_exists_remote(cfg, token, test_path):
            # Find next available number
            counter = 2
            while counter < 100:  # Limit to prevent infinite loops
                fname = f"{root} ({counter}){ext}"
                test_path = f"{base_path}/{fname}"
                if not check_file_exists_remote(cfg, token, test_path):
                    break
                counter += 1
    # else: dedup == "none", no collision handling

    # Organize by artist if enabled
    organize_by_artist = cfg.get("organize_by_artist", False)
    artist_name = None
    
    if organize_by_artist:
        # Extract artist name from path
        if cat == "Audio":
            artist_name = extract_artist_from_path(local_path)
        elif cat == "Images":
            # For images, check if they're related to an artist (covers, logos, artist images)
            image_type = get_image_type(original_basename)
            if image_type in ("cover", "logo", "artist"):
                artist_name = extract_artist_from_path(local_path)
    
    # Build path with optional base prefix and organization
    # All uploads go under lowercase uploads/ folder
    if override_path:
        # Manual folder override: skip all auto category/subfolder logic,
        # place the (already filename-processed) file directly under it.
        if base:
            return f"{base}/{uploads_root}/{remote_cat}/{fname}", cat
        else:
            return f"{uploads_root}/{remote_cat}/{fname}", cat

    if organize_by_artist and artist_name:
        # Everything goes into uploads/Audio/{Artist}/ folder
        if base:
            return f"{base}/{uploads_root}/audio/{artist_name}/{fname}", cat
        else:
            return f"{uploads_root}/audio/{artist_name}/{fname}", cat
    elif cat == "Scripts":
        # Handle script language subfolders and package structures
        ext = os.path.splitext(local_path)[1].lower()
        language_folder = get_script_language_subfolder(ext).lower()
        
        # Detect if this is part of a package/module structure
        is_package, package_root, rel_path = detect_package_structure(local_path)
        
        if is_package and package_root and rel_path:
        # Preserve package structure under uploads/Scripts/{Language}/package-name/...
            package_name = sanitize_filename(os.path.basename(package_root))
            # Convert relative path to use sanitized filenames but preserve structure
            rel_parts = rel_path.split(os.sep)
            sanitized_parts = [sanitize_filename(part) for part in rel_parts]
            package_path = "/".join(sanitized_parts)
            
            if base:
                return f"{base}/{uploads_root}/{remote_cat}/{language_folder}/{package_name}/{package_path}", cat
            else:
                return f"{uploads_root}/{remote_cat}/{language_folder}/{package_name}/{package_path}", cat
        else:
            # Standalone script, just use language subfolder
            if base:
                return f"{base}/{uploads_root}/{remote_cat}/{language_folder}/{fname}", cat
            else:
                return f"{uploads_root}/{remote_cat}/{language_folder}/{fname}", cat
    elif cat == "Images" and cfg.get("use_image_subfolders", True):
        # Original image subfolder organization (Covers, Logos, Artists)
        image_type = get_image_type(original_basename)
        if image_type:
            subfolder_map = {
                "cover": "covers",
                "logo": "logos", 
                "artist": "artists"
            }
            subfolder = subfolder_map.get(image_type)
            if subfolder:
                if base:
                    return f"{base}/{uploads_root}/{remote_cat}/{subfolder}/{fname}", cat
                else:
                    return f"{uploads_root}/{remote_cat}/{subfolder}/{fname}", cat
    
    # Standard path building - all under uploads/
    if base:
        return f"{base}/{uploads_root}/{remote_cat}/{fname}", cat
    else:
        return f"{uploads_root}/{remote_cat}/{fname}", cat

def upload_contents_api(cfg, token, local_path, remote_path, category):
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")

    # URL-encode each path component separately (don't encode the '/' separators)
    path_parts = remote_path.split("/")
    encoded_parts = [urllib.parse.quote(part, safe="") for part in path_parts]
    encoded_path = "/".join(encoded_parts)
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}"

    with open(local_path, "rb") as f:
        blob = f.read()
    b64 = base64.b64encode(blob).decode("ascii")

    # Use the final processed name in the commit comment, not the source basename.
    msg = commit_message_for(category, os.path.basename(remote_path))

    payload = {"message": msg, "content": b64, "branch": branch}
    resp = api_request("PUT", url, token, data=payload)
    content = resp.get("content") if resp else None
    if not content:
        raise RuntimeError("GitHub API returned no content object.")
    return content.get("download_url")

def get_or_create_release(cfg, token):
    owner = cfg["owner"]
    repo = cfg["repo"]
    tag = cfg.get("release_tag", "gupload-uploads")
    name = cfg.get("release_name", "Uploads")
    draft = bool(cfg.get("release_draft", True))
    prerelease = bool(cfg.get("release_prerelease", False))

    url_get = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    try:
        rel = api_request("GET", url_get, token)
        return rel["upload_url"]
    except Exception:
        pass

    url_create = f"https://api.github.com/repos/{owner}/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": name,
        "draft": draft,
        "prerelease": prerelease,
        "generate_release_notes": False,
        "body": "Automated uploads via Gupload.",
    }
    rel = api_request("POST", url_create, token, data=payload)
    return rel["upload_url"]

def upload_release_asset(cfg, token, local_path, category, override_path=None):
    upload_url_tmpl = get_or_create_release(cfg, token)
    upload_url = upload_url_tmpl.split("{")[0]

    fname = sanitize_filename(os.path.basename(local_path))
    # Prefix category for releases (no folders there). A --path override
    # replaces the category as the prefix, since releases have no folders.
    root, ext = os.path.splitext(fname)
    if override_path:
        prefix = override_path.replace("/", "-")
        root = f"{prefix}-{root}"
    elif cfg.get("release_prefix_category", True):
        root = release_prefix_for(category, root)
    if cfg.get("release_append_timestamp", True):
        root = f"{root}-{int(time.time())}"
    fname = root + ext

    ctype = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    url = f"{upload_url}?name={urllib.parse.quote(fname)}"

    cmd = [
        "curl", "-sS", "-L",
        "-X", "POST",
        "-H", "Accept: application/vnd.github+json",
        "-H", f"Authorization: Bearer {token}",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        "-H", f"Content-Type: {ctype}",
        "--data-binary", f"@{local_path}",
        url
    ]
    out = subprocess.check_output(cmd)
    resp = json.loads(out.decode("utf-8"))
    return resp.get("browser_download_url")

def format_links(cfg, local_path, url, remote_path=None, formats=None, is_release=False):
    # For images and audio: use processed remote filename (better readability)
    # For other files: use original local filename (preserves original name)
    cat = category_for_path(local_path)
    is_image = cat == "Images"
    is_audio = cat == "Audio"

    if remote_path and (is_image or is_audio):
        # Images and audio should use the processed filename
        # Images: e.g., "Cold Steel - 2023 - Deeper Into Greater Pain.jpg"
        # Audio: e.g., "Condition Critical - Voluntary Disfigurement.mp3" (not "04. Voluntary Disfigurement.mp3")
        display_fname = os.path.basename(remote_path)
    else:
        # Other files use original local filename
        display_fname = os.path.basename(local_path)

    if formats:
        # New multi-format path: --format was passed on the CLI.
        jsdelivr_url = None
        if not is_release and remote_path and cfg.get("owner") and cfg.get("repo"):
            jsdelivr_url = build_jsdelivr_url(
                cfg["owner"], cfg["repo"], cfg.get("branch", "main"), remote_path
            )
        lines, warnings = render_formats(
            formats, display_fname, url, is_image=is_image, is_audio=is_audio,
            jsdelivr_url=jsdelivr_url,
        )
        for w in warnings:
            eprint(f"Warning: {w}")
        return "\n".join(lines)

    mode = cfg.get("output_mode", "markdown")  # markdown | url | both
    extra_audio = bool(cfg.get("also_audio_html", True))
    
    # Use image embedding syntax for images (![...])
    if is_image:
        md = f"![{display_fname}]({url})"
    else:
        md = f"[{display_fname}]({url})"
    
    lines = []
    if mode in ("markdown", "both"):
        lines.append(md)
        if extra_audio and os.path.splitext(display_fname)[1].lower() in AUDIO_EXT:
            lines.append(f'<audio controls src="{url}"></audio>')
    if mode in ("url", "both"):
        lines.append(url)
    return "\n".join(lines)

PATH_PICK_SENTINEL = "__GUPLOAD_PICK_FOLDER__"


def fetch_existing_upload_folders(cfg, token):
    """List existing folder paths under uploads/ in the repo, for the
    --path interactive picker. Returns a sorted list of relative paths
    (e.g. 'audio', 'images/covers'). Best-effort: returns [] on any
    error rather than failing the whole picker.
    """
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    try:
        resp = api_request("GET", url, token)
    except Exception:
        return []
    if not resp:
        return []
    folders = set()
    for item in resp.get("tree", []):
        if item.get("type") != "tree":
            continue
        path = item.get("path", "")
        if path.startswith("uploads/"):
            folders.add(path[len("uploads/"):])
        elif path == "uploads":
            continue
    return sorted(folders)


def pick_folder_interactively(cfg, token):
    """Interactive folder picker for --path with no value.

    Uses questionary when available; falls back to a plain numbered
    prompt on stdin otherwise. Returns a sanitized repo-relative path,
    or None if the user cancels.
    """
    folders = fetch_existing_upload_folders(cfg, token)
    new_option = "+ new folder..."

    try:
        import questionary
        choices = folders + [new_option]
        choice = questionary.select(
            "Choose a destination folder under uploads/:", choices=choices
        ).ask()
        if choice is None:
            return None
        if choice == new_option:
            typed = questionary.text("New folder path (under uploads/):").ask()
            if not typed:
                return None
            return sanitize_repo_path(typed)
        return choice
    except ImportError:
        eprint("Existing folders under uploads/:")
        for i, f in enumerate(folders, 1):
            eprint(f"  {i}. {f}")
        eprint(f"  {len(folders) + 1}. {new_option}")
        raw = input("Choose a number or type a new path: ").strip()
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(folders):
                return folders[idx - 1]
            if idx == len(folders) + 1:
                typed = input("New folder path (under uploads/): ").strip()
                if not typed:
                    return None
                return sanitize_repo_path(typed)
            return None
        return sanitize_repo_path(raw)


def print_preview_rows(rows):
    """Render --preview output. Uses a rich table when available,
    otherwise falls back to the original plain-text block format.
    """
    if not rows:
        return
    try:
        from rich.console import Console
        from rich.table import Table
        table = Table(title="Upload preview")
        table.add_column("File")
        table.add_column("Category")
        table.add_column("Filename")
        table.add_column("Remote path")
        table.add_column("Transport")
        table.add_column("Formats")
        for r in rows:
            table.add_row(
                r["original"], r["category"], r["filename"],
                r["remote_path"], r["transport"], r["formats"],
            )
        Console().print(table)
    except ImportError:
        for r in rows:
            print(f"[PREVIEW] {r['original']}")
            print(f"  category: {r['category']}")
            print(f"  filename: {r['filename']}")
            print(f"  remote path: {r['remote_path']}")
            print(f"  transport: {r['transport']}")
            if r["formats"] != "-":
                print(f"  formats: {r['formats']}")


def main(argv):
    # Parse arguments
    parser = argparse.ArgumentParser(description='Upload files to GitHub and get markdown/URL links')
    parser.add_argument('files', nargs='+', help='File paths or URLs to upload')
    parser.add_argument('-n', '--name', dest='custom_name', help='Custom filename for single file upload')
    parser.add_argument('--names', nargs='+', dest='custom_names', help='Custom filenames for multiple files (must match number of files)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--preview', '--dry-run', action='store_true', dest='preview',
                        help='Show proposed names and paths without uploading')
    parser.add_argument('--path', nargs='?', const=PATH_PICK_SENTINEL, default=None,
                        dest='path_override',
                        help='Manual destination folder under uploads/, bypassing auto-categorization. '
                             'Pass with no value for an interactive picker.')
    parser.add_argument('--format', dest='formats',
                        help='Comma-separated output formats: mdlink,mdimage,literal,html,jsdelivr. '
                             'Default: current auto behavior (config output_mode).')

    # Parse known args (allow unknown args for backward compatibility)
    args, unknown = parser.parse_known_args()
    
    # If unknown args exist and no --name/--names, assume old-style usage (backward compatibility)
    if unknown and not args.custom_name and not args.custom_names:
        # Old-style: files as positional args
        all_files = args.files + unknown
        custom_names = None
        verbose = args.verbose
        preview = args.preview
    else:
        all_files = args.files
        custom_names = [args.custom_name] if args.custom_name else (args.custom_names if args.custom_names else None)
        verbose = args.verbose
        preview = args.preview
    
    cfg = load_config()
    token = get_token(cfg)

    if not all_files:
        eprint("Usage: gupload <file1> [file2 ...] [--name custom_name]")
        eprint("       gupload <url1> [url2 ...] [--name custom_name]")
        sys.exit(2)

    override_path = None
    if args.path_override is not None:
        if args.path_override == PATH_PICK_SENTINEL:
            chosen = pick_folder_interactively(cfg, token)
            if chosen is None:
                eprint("No folder chosen, aborting.")
                sys.exit(1)
            override_path = chosen
        else:
            try:
                override_path = sanitize_repo_path(args.path_override)
            except ValueError as e:
                eprint(f"Invalid --path: {e}")
                sys.exit(2)

    formats = None
    if args.formats:
        formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]

    max_contents_mb = float(cfg.get("contents_max_mb", 95))
    if not verbose:
        verbose = bool(cfg.get("verbose", False))
    continue_on_error = bool(cfg.get("continue_on_error", True))
    out_blocks = []
    errors = []
    temp_files = []  # Track temp files for cleanup
    preview_count = 0
    preview_rows = []

    file_iter = enumerate(all_files, 1)
    if not preview and not verbose and len(all_files) > 1:
        try:
            from rich.progress import track
            file_iter = track(file_iter, total=len(all_files), description="Uploading")
        except ImportError:
            pass

    for i, p in file_iter:
        original_path = p
        custom_name = custom_names[i-1] if custom_names and i <= len(custom_names) else None
        is_url_input = is_url(p)
        
        # Download from URL if needed
        if is_url_input:
            try:
                if verbose:
                    eprint(f"[{i}/{len(all_files)}] Downloading from URL: {p}")
                p = download_url(p)
                temp_files.append(p)
                if verbose:
                    eprint(f"  → Downloaded to: {p}")
            except Exception as e:
                msg = f"Error downloading {original_path}: {e}"
                eprint(msg)
                errors.append(msg)
                if not continue_on_error:
                    # Cleanup temp files before exiting
                    for tf in temp_files:
                        try:
                            if os.path.exists(tf):
                                os.remove(tf)
                        except Exception:
                            pass
                    sys.exit(1)
                continue
        else:
            p = os.path.expanduser(p)
        
        # Check if file exists
        if not os.path.exists(p) or not os.path.isfile(p):
            msg = f"Skip (not a file): {p}"
            eprint(msg)
            errors.append(msg)
            continue

        try:
            category = category_for_path(p)
            size_mb = os.path.getsize(p) / (1024 * 1024)

            if verbose:
                eprint(f"[{i}/{len(all_files)}] Uploading {os.path.basename(p)} ({size_mb:.1f} MB) as {category.lower()}...")

            if preview:
                preview_path, preview_category = build_repo_path(
                    cfg, p, token, custom_name=custom_name, override_path=override_path
                )
                transport = "contents" if size_mb <= max_contents_mb else "release"
                preview_rows.append({
                    "original": original_path,
                    "category": preview_category.lower(),
                    "filename": os.path.basename(preview_path),
                    "remote_path": preview_path,
                    "transport": f"GitHub {transport}",
                    "formats": ", ".join(formats) if formats else "-",
                })
                preview_count += 1
                continue

            if size_mb <= max_contents_mb:
                remote_path, cat = build_repo_path(
                    cfg, p, token, custom_name=custom_name, override_path=override_path
                )
                if verbose:
                    eprint(f"  → Repo path: {remote_path}")
                url = upload_contents_api(cfg, token, p, remote_path, cat)
                if not url:
                    raise RuntimeError("No download_url returned for contents upload.")
                # Pass remote_path so format_links uses the processed filename
                out_blocks.append(format_links(cfg, p, url, remote_path, formats=formats, is_release=False))
                # Log successful upload
                log_upload(p, os.path.basename(remote_path), url, cat)
                if verbose:
                    eprint(f"  ✓ Uploaded: {url}")
            else:
                if os.path.getsize(p) > 2 * 1024 * 1024 * 1024:
                    raise RuntimeError(f"File too large (>2 GiB): {p}")
                if verbose:
                    eprint(f"  → Using release asset (large file)...")
                url = upload_release_asset(cfg, token, p, category, override_path=override_path)
                if not url:
                    raise RuntimeError("No browser_download_url returned for release upload.")
                # For release assets, build a remote_path for display purposes (even though file is in release)
                # This ensures audio files show the processed filename in markdown
                remote_path_for_display, _ = build_repo_path(
                    cfg, p, token, custom_name=custom_name, override_path=override_path
                )
                out_blocks.append(format_links(cfg, p, url, remote_path_for_display, formats=formats, is_release=True))
                # Log successful upload
                log_upload(p, os.path.basename(remote_path_for_display), url, category)
                if verbose:
                    eprint(f"  ✓ Uploaded: {url}")

        except Exception as e:
            msg = f"Error uploading {os.path.basename(p)}: {e}"
            eprint(msg)
            errors.append(msg)
            if not continue_on_error:
                # Cleanup temp files before exiting
                for tf in temp_files:
                    try:
                        if os.path.exists(tf):
                            os.remove(tf)
                    except Exception:
                        pass
                sys.exit(1)

    # Cleanup temp files
    for tf in temp_files:
        try:
            if os.path.exists(tf):
                os.remove(tf)
        except Exception:
            pass

    if preview:
        print_preview_rows(preview_rows)
        print(f"Previewed {preview_count} file(s); nothing was uploaded.")
        if errors:
            eprint(f"Encountered {len(errors)} preview error(s).")
        return

    if not out_blocks:
        eprint("No files uploaded successfully.")
        if errors:
            eprint(f"\nEncountered {len(errors)} error(s):")
            for err in errors:
                eprint(f"  - {err}")
        sys.exit(1)

    combined = "\n\n".join(out_blocks).strip() + "\n"
    print(combined)
    clipboard_set(combined)

    if errors and verbose:
        eprint(f"\n⚠ Completed with {len(errors)} error(s), {len(out_blocks)} successful upload(s)")

if __name__ == "__main__":
    main(sys.argv)
