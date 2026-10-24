#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error

from pathlib import Path

from gupload_state import config_path, data_path, read_json, update_json, write_json


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
    path = config_path() / "config.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing config: {path}")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)

def run(cmd):
    return subprocess.check_output(cmd, text=True).strip()

def download_url(url, output_path=None, max_bytes=None, return_filename=False):
    """Download one URL, cleaning an owned temporary file after every failure."""
    temporary_path = None
    destination = output_path
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "gupload"})
        with urllib.request.urlopen(request, timeout=30) as response:
            disposition = response.headers.get("Content-Disposition", "")
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', disposition, re.I)
            filename = urllib.parse.unquote(match.group(1)) if match else ""
            if not filename:
                filename = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path))
            if not filename or "." not in filename:
                content_type = response.headers.get("Content-Type", "")
                filename = (filename or "download") + (mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".jpg")
            filename = os.path.basename(filename)
            directory = os.path.dirname(os.path.abspath(destination)) if destination is not None else None
            fd, temporary_path = tempfile.mkstemp(
                suffix=os.path.splitext(filename)[1], prefix="gupload_", dir=directory)
            os.close(fd)
            written = 0
            with open(temporary_path, "wb") as stream:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    written += len(chunk)
                    if max_bytes is not None and written > max_bytes:
                        raise RuntimeError(f"Download exceeds configured limit ({max_bytes} bytes): {url}")
                    stream.write(chunk)
        if destination is not None:
            os.replace(temporary_path, destination)
            temporary_path = None
            output_path = destination
        else:
            output_path = temporary_path
        return (output_path, filename) if return_filename else output_path
    except Exception as exc:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc

def is_url(path):
    """Check if the path is a URL."""
    return path.startswith('http://') or path.startswith('https://')

def get_token(cfg):
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    if cfg.get("allow_gh_cli_token", True):
        try:
            token = run(["gh", "auth", "token"])
            if token:
                return token
        except Exception:
            pass
    try:
        from gupload_platform import get_keychain_token
        token = get_keychain_token()
    except (ImportError, OSError):
        token = None
    if token:
        return token
    raise RuntimeError("No GitHub token found. Set GITHUB_TOKEN or run `gh auth login`.")

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
    """Build a jsdelivr URL with independently encoded branch and path components."""
    owner = urllib.parse.quote(owner, safe="")
    repo = urllib.parse.quote(repo, safe="")
    branch = urllib.parse.quote(branch, safe="")
    path = "/".join(urllib.parse.quote(part, safe="") for part in remote_path.lstrip("/").split("/"))
    return f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}"


def commit_message_for(category: str, filename: str) -> str:
    return f"{category.lower()} ⋅ {filename}"


def release_prefix_for(category: str, root: str) -> str:
    return f"{category.lower()}-{root}"


def _markdown_label(value):
    return re.sub(r"([\\`*_{}\[\]()#+!|>-])", r"\\\1", value)


def _markdown_destination(value):
    return urllib.parse.quote(value, safe=":/?#@!$&'*+,;=%-._~")


def render_formats(formats, filename, url, is_image, is_audio, jsdelivr_url=None):
    """Render safe Markdown/HTML links and report unsupported output formats."""
    lines, warnings = [], []
    label, destination = _markdown_label(filename), _markdown_destination(url)
    escaped_name, escaped_url = html.escape(filename, quote=True), html.escape(url, quote=True)
    for fmt in formats:
        if fmt == "mdlink":
            lines.append(f"[{label}]({destination})")
        elif fmt == "mdimage":
            lines.append(f"![{label}]({destination})")
        elif fmt == "literal":
            lines.append(url)
        elif fmt == "html":
            if is_image:
                lines.append(f'<img src="{escaped_url}">')
            elif is_audio:
                lines.append(f'<audio controls src="{escaped_url}"></audio>')
            else:
                lines.append(f'<a href="{escaped_url}">{escaped_name}</a>')
        elif fmt == "jsdelivr":
            if jsdelivr_url:
                lines.append(jsdelivr_url)
            else:
                warnings.append(f"jsdelivr format unavailable for {filename} (release assets have no jsdelivr equivalent) - skipped")
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
    return _github_contents(cfg, token, remote_path) is not None

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

    if custom_name:
        # Keep all existing destination routing; override only the final name.
        routed_path, category = build_repo_path(
            cfg, local_path, token=token, custom_name=None, override_path=override_path
        )
        supplied_ext = os.path.splitext(custom_name)[1]
        source_ext = os.path.splitext(local_path)[1]
        final_name = custom_name if supplied_ext else custom_name + source_ext
        final_name = sanitize_filename(final_name, preserve_spaces=True)
        return f"{os.path.dirname(routed_path)}/{final_name}", category

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
    dedup = cfg.get("dedup_strategy", "hash")
    if dedup == "hash" and cfg.get("append_short_hash", True):
        short = sha1_file(local_path)[:8]
        root, ext = os.path.splitext(fname)
        fname = f"{root}-{short}{ext}"

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

def upload_contents_api(cfg, token, local_path, remote_path, category, sha=None, details=False,
                        expected_sha256=None, expected_size=None):
    owner, repo = cfg["owner"], cfg["repo"]
    branch = cfg.get("branch", "main")
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in remote_path.split("/"))
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}"
    with open(local_path, "rb") as stream:
        blob = stream.read()
    if expected_size is not None and len(blob) != expected_size:
        raise RuntimeError("Source size changed at upload boundary.")
    if expected_sha256 is not None and hashlib.sha256(blob).hexdigest() != expected_sha256:
        raise RuntimeError("Source SHA-256 changed at upload boundary.")
    content = base64.b64encode(blob).decode("ascii")
    payload = {"message": commit_message_for(category, os.path.basename(remote_path)),
               "content": content, "branch": branch}
    if sha:
        payload["sha"] = sha
    response = api_request("PUT", url, token, data=payload)
    remote = response.get("content") if response else None
    if not remote:
        raise RuntimeError("GitHub API returned no content object.")
    return (remote.get("download_url"), remote.get("sha"), remote.get("path")) if details else remote.get("download_url")
def _find_release(cfg, token):
    base = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/releases"
    tag = cfg.get("release_tag", "gupload-uploads")
    try:
        return api_request("GET", f"{base}/tags/{urllib.parse.quote(tag, safe='')}", token)
    except RuntimeError as exc:
        if "-> 404" not in str(exc):
            raise
    page = 1
    while True:
        releases = api_request("GET", f"{base}?per_page=100&page={page}", token)
        if not isinstance(releases, list):
            raise RuntimeError("GitHub returned an invalid releases list.")
        existing = next((release for release in releases if release.get("tag_name") == tag), None)
        if existing:
            return existing
        if len(releases) < 100:
            return None
        page += 1


def get_or_create_release(cfg, token, details=False):
    owner, repo = cfg["owner"], cfg["repo"]
    release = _find_release(cfg, token)
    if release is None:
        tag = cfg.get("release_tag", "gupload-uploads")
        payload = {"tag_name": tag, "name": cfg.get("release_name", "Uploads"),
                   "draft": bool(cfg.get("release_draft", True)),
                   "prerelease": bool(cfg.get("release_prerelease", False)),
                   "generate_release_notes": False, "body": "Automated uploads via Gupload."}
        release = api_request("POST", f"https://api.github.com/repos/{owner}/{repo}/releases", token, data=payload)
    return (release["upload_url"], release["id"], release.get("assets", [])) if details else release["upload_url"]

def upload_release_asset(cfg, token, local_path, category, override_path=None, filename=None, details=False):
    if details:
        upload_url_template, release_id, _ = get_or_create_release(cfg, token, details=True)
    else:
        upload_url_template = get_or_create_release(cfg, token)
        release_id = None
    upload_url = upload_url_template.split("{")[0]
    if filename is None:
        filename = _release_filename(cfg, category, os.path.basename(local_path))
    ctype = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    url = f"{upload_url}?name={urllib.parse.quote(filename)}"
    cmd = ["curl", "-fS", "-L", "-X", "POST", "-H", "Accept: application/vnd.github+json",
           "-H", f"Authorization: Bearer {token}", "-H", "X-GitHub-Api-Version: 2022-11-28",
           "-H", f"Content-Type: {ctype}", "--data-binary", f"@{local_path}", url]
    response = json.loads(subprocess.check_output(cmd).decode("utf-8"))
    if details:
        return response.get("browser_download_url"), release_id, response.get("id")
    return response.get("browser_download_url")

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
    
    safe_label = _markdown_label(display_fname)
    safe_url = _markdown_destination(url)
    if is_image:
        md = f"![{safe_label}]({safe_url})"
    else:
        md = f"[{safe_label}]({safe_url})"
    html_url = html.escape(url, quote=True)
    lines = []
    if mode in ("markdown", "both"):
        lines.append(md)
        if extra_audio and os.path.splitext(display_fname)[1].lower() in AUDIO_EXT:
            lines.append(f'<audio controls src="{html_url}"></audio>')
    if mode in ("url", "both"):
        lines.append(url)
    return "\n".join(lines)

PATH_PICK_SENTINEL = "__GUPLOAD_PICK_FOLDER__"





def reject_unknown_flags(unknown):
    """Exit with a usage error when unrecognized flag-like arguments appear.

    Non-flag leftovers keep the legacy positional fold-in; only arguments
    starting with '-' are treated as typos.
    """
    flag_like = [u for u in unknown if u.startswith("-")]
    if flag_like:
        eprint(f"Unrecognized argument(s): {' '.join(flag_like)}")
        eprint("Run with --help to see supported options.")
        sys.exit(2)


def detect_categories(paths):
    """Return [(path, category)] using category_for_path for each input."""
    return [(p, category_for_path(p)) for p in paths]


def get_presets(cfg):
    presets = {
        "wtfpl": {"path": "files/licenses/wtfpl"},
        "mit": {"path": "files/licenses/mit"},
        "gpl": {"path": "files/licenses/gpl"},
        "docker-icons": {"path": "icons/docker"},
    }
    presets.update(cfg.get("presets", {}))
    return presets


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_blob_sha(path):
    digest = hashlib.sha1()
    size = os.path.getsize(path)
    digest.update(f"blob {size}\0".encode())
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_name(source):
    if is_url(source):
        return os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(source).path)) or "download"
    return os.path.basename(os.path.expanduser(source))


def _sensitive_reasons(source):
    if is_url(source):
        parsed = urllib.parse.urlparse(source)
        candidate = urllib.parse.unquote(parsed.path)
        path_values = (candidate,)
    else:
        candidate = os.path.expanduser(source)
        path_values = (candidate, os.path.realpath(candidate))
    names = {os.path.basename(value).lower() for value in path_values}
    parts = {part.lower() for value in path_values for part in Path(value).parts}
    reasons = []
    if is_url(source):
        parsed = urllib.parse.urlparse(source)
        if parsed.username or parsed.password:
            reasons.append("sensitive URL userinfo credentials")
        query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        sensitive_keys = {"token", "access_token", "api_key", "key", "signature", "sig", "password", "secret"}
        if any(k.lower() in sensitive_keys for k in query_params.keys()):
            reasons.append("sensitive query parameters")
    if names & {".env", ".env.local", ".env.production", "config.json", "id_rsa", "id_ed25519"}:
        reasons.append("sensitive filename")
    sensitive_dirs = {".git", ".venv", "venv", "__pycache__", ".cache", "node_modules"}
    if any(part in sensitive_dirs for part in parts):
        reasons.append("sensitive directory")
    if any(name.endswith((".pem", ".key", ".p12", ".pfx")) for name in names):
        reasons.append("private-key file")
    if not is_url(source):
        config_dir = os.path.realpath(str(config_path().parent))
        raw_config_dir = os.path.abspath(str(config_path().parent))
        for check_path in path_values:
            abs_check = os.path.abspath(check_path)
            real_check = os.path.realpath(check_path)
            for cdir in (config_dir, raw_config_dir):
                try:
                    if os.path.commonpath((cdir, abs_check)) == cdir or os.path.commonpath((cdir, real_check)) == cdir:
                        if "sensitive directory" not in reasons:
                            reasons.append("sensitive directory")
                except ValueError:
                    pass
    return reasons


def _apply_name_pattern(pattern, source_name, category):
    stem, ext = os.path.splitext(source_name)
    fields = {"name": stem, "stem": stem, "filename": source_name,
              "ext": ext.lstrip("."), "category": category.lower()}
    if not isinstance(pattern, str):
        raise ValueError("Naming pattern must be a string.")
    tokens = re.findall(r"\{([^{}]+)\}", pattern)
    if any(token not in fields for token in tokens) or pattern.count("{") != len(tokens) or pattern.count("}") != len(tokens):
        raise ValueError("Naming pattern may use only {name}, {stem}, {filename}, {ext}, and {category}.")
    return re.sub(r"\{([^{}]+)\}", lambda match: fields[match.group(1)], pattern)


def _release_settings(cfg):
    return {
        "tag": cfg.get("release_tag", "gupload-uploads"),
        "name": cfg.get("release_name", "Uploads"),
        "draft": bool(cfg.get("release_draft", True)),
        "prerelease": bool(cfg.get("release_prerelease", False)),
        "prefix_category": bool(cfg.get("release_prefix_category", True)),
        "append_timestamp": bool(cfg.get("release_append_timestamp", True)),
    }


def _settings_fingerprint(settings):
    payload = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
def _remote_path(cfg, source, custom_name=None, override_path=None):
    source_name = _source_name(source)
    build_cfg = dict(cfg)
    local = os.path.expanduser(source) if not is_url(source) else source_name
    build_cfg["dedup_strategy"] = "none"
    return build_repo_path(build_cfg, local, custom_name=custom_name, override_path=override_path)


def _release_filename(cfg, category, remote_path):
    root, ext = os.path.splitext(os.path.basename(remote_path))
    if cfg.get("release_prefix_category", True):
        root = release_prefix_for(category, root)
    if cfg.get("release_append_timestamp", True):
        root = f"{root}-{int(time.time())}"
    return root + ext


def build_plan(inputs, cfg, names=None, path=None, collision=None, formats=None):
    if names is not None and len(names) != len(inputs):
        raise ValueError("--names must contain exactly one name per input.")
    policy = collision or cfg.get("collision_policy", "skip-identical")
    if policy not in {"skip-identical", "rename", "update"}:
        raise ValueError("collision must be skip-identical, rename, or update.")
    if path is not None:
        path = sanitize_repo_path(path)
    items = []
    for index, raw_source in enumerate(inputs):
        source = str(raw_source)
        source_name = _source_name(source)
        custom_name = names[index] if names else None
        category = category_for_path(source_name)
        preset = cfg.get("_active_preset", {})
        if not custom_name and preset.get("name_pattern"):
            custom_name = _apply_name_pattern(preset["name_pattern"], source_name, category)
        override = path or preset.get("path")
        remote_path, category = _remote_path(cfg, source, custom_name, override)
        size, digest = None, None
        transport = "unresolved"
        status, error = "unresolved", None
        if not is_url(source):
            local = os.path.expanduser(source)
            if os.path.isfile(local):
                size, digest = os.path.getsize(local), _sha256_file(local)
                transport = "release" if size > float(cfg.get("contents_max_mb", 95)) * 1024 * 1024 else "contents"
                status = "planned"
            else:
                status, error = "failed", "Source is not a readable file."
                transport = "unresolved"
        filename = _release_filename(cfg, category, remote_path) if transport == "release" else os.path.basename(remote_path)
        warnings = _sensitive_reasons(source)
        if cfg.get("public_repo") is not False:
            warnings.append("Repository visibility is not verified offline; uploaded files may be publicly accessible.")
        if transport == "release" and (cfg.get("release_draft", True) or cfg.get("release_prerelease", False)):
            warnings.append("Release asset visibility may be limited by draft/prerelease settings.")
        item_identity = hashlib.sha256(
            (f"{cfg.get('owner')}/{cfg.get('repo')}@{cfg.get('branch', 'main')}\0{source}\0{remote_path}\0{index}").encode("utf-8")
        ).hexdigest()
        items.append({"item_id": item_identity, "source": source, "source_name": source_name, "filename": filename,
                      "remote_path": remote_path, "planned_remote_path": remote_path,
                      "transport": transport, "size_bytes": size, "sha256": digest,
                      "warnings": warnings, "status": status, "error": error, "collision": policy,
                      "custom_name": custom_name, "formats": formats, "path_override": override})
    errors = [f"{item['source']}: {item['error']}" for item in items if item["status"] == "failed"]
    warnings = [warning for item in items for warning in item["warnings"]]
    settings = _release_settings(cfg)
    return {"version": 1, "destination": {"owner": cfg.get("owner"), "repo": cfg.get("repo"),
            "branch": cfg.get("branch", "main")}, "release_settings": settings,
            "settings_fingerprint": _settings_fingerprint(settings),
            "items": items, "warnings": warnings, "errors": errors}


def _validate_local_destination(cfg, expect_repo=None, expect_account=None, require_approval=False):
    owner, repo = cfg.get("owner"), cfg.get("repo")
    if not owner or not repo:
        raise ValueError("Configuration must identify an owner and repository.")
    target = f"{owner}/{repo}".lower()
    if expect_repo and target != expect_repo.lower():
        raise ValueError(f"Configured destination does not match --expect-repo {expect_repo}.")
    allowed = [str(value).lower() for value in cfg.get("allowed_destinations", [])]
    if allowed and target not in allowed:
        raise ValueError("Destination is not in configured allowed_destinations.")
    if require_approval and not expect_repo and target not in allowed:
        raise ValueError("Execution requires --expect-repo or a matching allowed_destinations entry.")
    configured_account = cfg.get("expected_account")
    if expect_account and configured_account and expect_account.lower() != configured_account.lower():
        raise ValueError("--expect-account conflicts with configured expected_account.")


def _github_contents(cfg, token, remote_path):
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in remote_path.split("/"))
    branch = urllib.parse.quote(cfg.get("branch", "main"), safe="")
    url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{encoded}?ref={branch}"
    try:
        return api_request("GET", url, token)
    except RuntimeError as exc:
        if "-> 404" in str(exc):
            return None
        raise


def _guard_destination(cfg, token, plan, expect_repo=None, expect_account=None, require_approval=False):
    destination = plan["destination"]
    target = f"{destination['owner']}/{destination['repo']}"
    if expect_repo and target.lower() != expect_repo.lower():
        raise RuntimeError(f"Destination does not match --expect-repo {expect_repo}.")
    allowed = [str(value).lower() for value in cfg.get("allowed_destinations", [])]
    if require_approval and not expect_repo and target.lower() not in allowed:
        raise RuntimeError("Execution requires --expect-repo or a matching allowed_destinations entry.")
    user = api_request("GET", "https://api.github.com/user", token)
    plan["account"] = user.get("login")
    expected = expect_account or cfg.get("expected_account")
    if expected and (user.get("login") or "").lower() != expected.lower():
        raise RuntimeError(f"Authenticated account does not match {expected}.")
    repository = api_request("GET", f"https://api.github.com/repos/{target}", token)
    for item in plan.get("items", []):
        warnings = item.setdefault("warnings", [])
        uncertainty = "Repository visibility is not verified offline; uploaded files may be publicly accessible."
        if uncertainty in warnings:
            warnings.remove(uncertainty)
        if repository.get("private") is False:
            warning = "Destination repository is public; uploaded files will be publicly accessible."
            if warning not in warnings:
                warnings.append(warning)
        elif repository.get("private") is None:
            warning = "Repository visibility could not be verified; uploaded files may be publicly accessible."
            if warning not in warnings:
                warnings.append(warning)


def _release_assets(cfg, token):
    return _find_release(cfg, token)


def resolve_remote_collision(cfg, token, item, source_path=None):
    """Read-only final destination collision resolution."""
    policy = item.get("collision", cfg.get("collision_policy", "skip-identical"))
    if item["transport"] == "release":
        release = _release_assets(cfg, token)
        assets = release.get("assets", []) if release else []
        existing = next((asset for asset in assets if asset.get("name") == item["filename"]), None)
        if not existing:
            return None
        if policy == "skip-identical" and existing.get("digest", "").endswith(item.get("sha256") or "!"):
            item.update(status="skipped", url=existing.get("browser_download_url"),
                        release_id=release.get("id"), asset_id=existing.get("id"))
            item["output"] = format_links(cfg, item["source"], item["url"], item["remote_path"],
                                          item.get("formats"), is_release=True)
            return existing
        if policy == "update":
            item["_existing_asset"] = {"id": existing.get("id"), "name": existing.get("name")}
            item["_release_id"] = release.get("id")
            return existing
        if policy == "rename":
            root, ext = os.path.splitext(item["filename"])
            for number in range(2, 10000):
                name = f"{root} ({number}){ext}"
                if not any(asset.get("name") == name for asset in assets):
                    item["filename"] = name
                    return None
        item.update(status="failed", error=f"Release asset collision at {item['filename']}.")
        return existing
    existing = _github_contents(cfg, token, item["remote_path"])
    if not existing:
        return None
    if policy == "update":
        item["remote_sha"] = existing.get("sha")
        return existing
    compare_source = source_path or item["source"]
    if policy == "skip-identical" and existing.get("sha") == _git_blob_sha(compare_source):
        item.update(status="skipped", url=existing.get("download_url"))
        item["output"] = format_links(cfg, compare_source, item["url"], item["remote_path"], item.get("formats"))
        return existing
    if policy == "rename":
        root, ext = os.path.splitext(item["remote_path"])
        for number in range(2, 10000):
            candidate = f"{root} ({number}){ext}"
            if _github_contents(cfg, token, candidate) is None:
                item.update(remote_path=candidate, filename=os.path.basename(candidate))
                return None
        item.update(status="failed", error=f"No available renamed path for {item['remote_path']}")
        return existing
    item.update(status="failed", error=f"Destination already exists with different content: {item['remote_path']}")
    return existing


def _collision_target(cfg, token, item, source_path=None):
    existing = resolve_remote_collision(cfg, token, item, source_path)
    target = item["filename"] if item["transport"] == "release" else item["remote_path"]
    return target, existing


def read_history():
    history = read_json(data_path("history.json"), None)
    if history is not None:
        if not isinstance(history, list):
            raise ValueError("History file must contain a JSON list.")
        return history
    legacy = read_json(data_path("recent.json"), [])
    return legacy if isinstance(legacy, list) else []



def _history_record(item, destination, batch_id):
    return {key: item.get(key) for key in ("item_id", "source", "source_name", "sha256", "remote_path",
            "filename", "transport", "remote_sha", "release_id", "asset_id", "url", "status", "error",
            "collision", "custom_name", "path_override", "planned_remote_path")} | {"batch_id": batch_id,
            "owner": destination.get("owner"), "repo": destination.get("repo"),
            "branch": destination.get("branch"), "timestamp": dt.datetime.now().isoformat()}


def build_retry_plan(cfg):
    history = read_history()
    latest = {}
    for record in history:
        if record.get("item_id"):
            latest[record["item_id"]] = record
    failures = [record for record in latest.values() if record.get("status") == "failed"]
    destination = {"owner": cfg.get("owner"), "repo": cfg.get("repo"), "branch": cfg.get("branch", "main")}
    items = []
    for record in failures:
        if (record.get("owner"), record.get("repo"), record.get("branch")) != (
                destination["owner"], destination["repo"], destination["branch"]):
            continue
        source = record.get("source", "")
        if not is_url(source):
            local = os.path.expanduser(source)
            if not os.path.isfile(local) or _sha256_file(local) != record.get("sha256"):
                raise ValueError(f"Failed source changed or is missing: {source}")
        is_src_url = is_url(source)
        planned_remote = record.get("planned_remote_path") or _remote_path(cfg, source, record.get("custom_name"), record.get("path_override"))[0]
        remote_path = planned_remote if is_src_url else record.get("remote_path")
        filename = os.path.basename(remote_path) if is_src_url else record.get("filename")
        items.append({"item_id": record["item_id"], "source": source,
                      "source_name": _source_name(source) if is_src_url else (record.get("source_name") or _source_name(source)),
                      "filename": filename, "remote_path": remote_path,
                      "planned_remote_path": planned_remote,
                      "transport": "unresolved" if is_src_url else record.get("transport", "unresolved"),
                      "size_bytes": None if is_src_url else os.path.getsize(os.path.expanduser(source)),
                      "sha256": None if is_src_url else record.get("sha256"), "warnings": _sensitive_reasons(source),
                      "status": "unresolved" if is_src_url else "planned", "error": None,
                      "collision": record.get("collision", cfg.get("collision_policy", "skip-identical")),
                      "custom_name": record.get("custom_name"), "formats": None,
                      "path_override": record.get("path_override")})
    return {"version": 1, "destination": destination, "items": items, "warnings": [], "errors": []}
def _validate_plan_sources(plan, cfg, allow_sensitive=False):
    expected = {"owner": cfg.get("owner"), "repo": cfg.get("repo"), "branch": cfg.get("branch", "main")}
    if plan.get("destination") != expected:
        raise ValueError("Plan destination does not match current configuration.")
    expected_settings = _release_settings(cfg)
    if any(item.get("transport") == "release" for item in plan.get("items", [])):
        if (plan.get("release_settings") != expected_settings or
                plan.get("settings_fingerprint") != _settings_fingerprint(expected_settings)):
            raise ValueError("Release settings changed since this plan was reviewed.")
    prefix = cfg.get("repo_path_prefix", "").strip("/")
    root = f"{prefix}/uploads" if prefix else "uploads"
    for item in plan.get("items", []):
        source = item.get("source", "")
        if item.get("collision") not in {"skip-identical", "rename", "update"}:
            raise ValueError("Plan has an invalid collision policy.")
        if _sensitive_reasons(source) and not allow_sensitive:
            raise ValueError(f"Sensitive source blocked: {source}")
        expected_path, _ = _remote_path(cfg, source, item.get("custom_name"), item.get("path_override"))
        base_path = item.get("planned_remote_path", item.get("remote_path", ""))
        remote_path = item.get("remote_path", "")
        if base_path != expected_path or not base_path.startswith(root + "/"):
            raise ValueError(f"Plan remote path differs from configured routing: {remote_path}")
        if remote_path != base_path:
            base_root, base_ext = os.path.splitext(base_path)
            remote_root, remote_ext = os.path.splitext(remote_path)
            if base_ext != remote_ext or base_root != remote_root.rsplit(" (", 1)[0] or " (" not in remote_root:
                raise ValueError(f"Plan remote path differs from configured routing: {remote_path}")
            try:
                num = remote_root.split("(")[-1].rstrip(")")
                int(num)
            except Exception:
                raise ValueError(f"Plan remote path differs from configured routing: {remote_path}")
            if item.get("collision") != "rename":
                raise ValueError(f"Plan remote path differs from configured routing: {remote_path}")
        if is_url(source):
            if item.get("status") != "unresolved" or item.get("sha256") is not None or item.get("size_bytes") is not None:
                raise ValueError("URL source must remain unresolved until execution.")
            continue
        local = os.path.expanduser(source)
        if not os.path.isfile(local):
            raise ValueError(f"Source is not a readable file: {source}")
        if _sha256_file(local) != item.get("sha256"):
            raise ValueError(f"Source changed since planning: {source}")
        size = os.path.getsize(local)
        transport = "release" if size > float(cfg.get("contents_max_mb", 95)) * 1024 * 1024 else "contents"
        if item.get("size_bytes") != size or item.get("transport") != transport:
            raise ValueError(f"Source size or transport changed since planning: {source}")


def execute_plan(plan, cfg, allow_sensitive=False, expect_repo=None, expect_account=None):
    _validate_plan_sources(plan, cfg, allow_sensitive)
    _validate_local_destination(cfg, expect_repo, expect_account, require_approval=True)
    token = get_token(cfg)
    _guard_destination(cfg, token, plan, expect_repo, expect_account or cfg.get("expected_account"),
                       require_approval=True)
    for item in plan["items"]:
        if item.get("status") == "failed":
            continue
        temp_paths = []
        source = item["source"]
        try:
            if _sensitive_reasons(source) and not allow_sensitive:
                raise RuntimeError("Sensitive source blocked; use --allow-sensitive to explicitly permit it.")
            source_was_url = is_url(item["source"])
            if source_was_url:
                source, content_name = download_url(
                    item["source"], max_bytes=int(float(cfg.get("download_max_mb", 512)) * 1024 * 1024),
                    return_filename=True)
                temp_paths.append(source)
                item["source_name"] = content_name
                item["remote_path"], _ = _remote_path(
                    cfg, content_name, item.get("custom_name"), item.get("path_override"))
                item["filename"] = os.path.basename(item["remote_path"])
            if not os.path.isfile(source):
                raise RuntimeError("Source is not a readable file.")
            if source_was_url:
                item["size_bytes"], item["sha256"] = os.path.getsize(source), _sha256_file(source)
                item["transport"] = "release" if item["size_bytes"] > float(cfg.get("contents_max_mb", 95)) * 1024 * 1024 else "contents"
                if item["transport"] == "release":
                    if item["size_bytes"] > 2 * 1024 * 1024 * 1024:
                        raise RuntimeError(f"File too large (>2 GiB): {item['source_name']}")
                    item["filename"] = _release_filename(cfg, category_for_path(item["source_name"]), item["remote_path"])
            else:
                current_size = os.path.getsize(source)
                current_sha = _sha256_file(source)
                current_transport = "release" if current_size > float(cfg.get("contents_max_mb", 95)) * 1024 * 1024 else "contents"
                if current_sha != item.get("sha256"):
                    raise RuntimeError(f"Source file content changed on disk before upload: {source}")
                if current_size != item.get("size_bytes") or current_transport != item.get("transport"):
                    raise RuntimeError(f"Source file size or transport changed on disk before upload: {source}")
                if current_transport == "release" and current_size > 2 * 1024 * 1024 * 1024:
                    raise RuntimeError(f"File too large (>2 GiB): {item['source_name']}")
            target, existing = _collision_target(cfg, token, item, source)
            if item.get("status") == "failed":
                continue
            if item.get("status") == "skipped":
                continue
            category = category_for_path(item["source_name"])
            if item["transport"] == "contents":
                url, remote_sha, actual_path = upload_contents_api(
                    cfg, token, source, target, category,
                    sha=existing.get("sha") if existing and item["collision"] == "update" else None,
                    details=True)
                item.update(remote_path=actual_path or target, remote_sha=remote_sha)
            else:
                previous = item.get("_existing_asset") if item.get("collision") == "update" else None
                if previous:
                    asset_url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/releases/assets/{previous['id']}"
                    backup_name = f".gupload-backup-{previous['id']}-{int(time.time())}"
                    api_request("PATCH", asset_url, token, data={"name": backup_name})
                    try:
                        url, release_id, asset_id = upload_release_asset(
                            cfg, token, source, category, filename=item["filename"], details=True)
                    except Exception as upload_error:
                        try:
                            api_request("PATCH", asset_url, token, data={"name": previous["name"]})
                        except Exception as restore_error:
                            raise RuntimeError(f"Replacement failed ({upload_error}); restoring prior asset name failed ({restore_error}); prior asset remains as {backup_name}.")
                        raise
                    try:
                        api_request("DELETE", asset_url, token)
                    except Exception as cleanup_error:
                        item.setdefault("warnings", []).append(
                            f"New asset uploaded; prior asset remains as {backup_name}: {cleanup_error}")
                else:
                    url, release_id, asset_id = upload_release_asset(
                        cfg, token, source, category, filename=item["filename"], details=True)
                item.update(release_id=release_id, asset_id=asset_id)
            if not url:
                raise RuntimeError("GitHub returned no download URL.")
            item.update(status="succeeded", url=url)
            item["output"] = format_links(cfg, source, url, item["remote_path"], item.get("formats"),
                                          is_release=item["transport"] == "release")
        except Exception as exc:
            item.update(status="failed", error=str(exc))
        finally:
            for temp in temp_paths:
                try:
                    os.unlink(temp)
                except FileNotFoundError:
                    pass
    batch_id = str(time.time_ns())
    records = [_history_record(item, plan["destination"], batch_id) for item in plan["items"]]
    if records:
        update_json(data_path("history.json"), read_history(), lambda current: current + records)
    return plan


def _plan_integrity(plan):
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_saved_plan(filename, cfg, expect_repo=None):
    plan = read_json(filename, None)
    if not isinstance(plan, dict) or plan.get("version") != 1 or not isinstance(plan.get("items"), list):
        raise ValueError("Invalid saved plan.")
    if not plan.get("plan_sha256") or plan.get("plan_sha256") != _plan_integrity(plan):
        raise ValueError("Saved plan integrity check failed.")
    expected = {"owner": cfg.get("owner"), "repo": cfg.get("repo"), "branch": cfg.get("branch", "main")}
    if plan.get("destination") != expected:
        raise ValueError("Saved plan destination does not match current configuration.")
    if expect_repo and f"{expected['owner']}/{expected['repo']}".lower() != expect_repo.lower():
        raise ValueError("Destination does not match --expect-repo.")
    _validate_plan_sources(plan, cfg, allow_sensitive=True)
    for item in plan["items"]:
        if not isinstance(item.get("source"), str) or not isinstance(item.get("remote_path"), str):
            raise ValueError("Saved plan contains invalid source or remote path values.")
        if item.get("collision") not in {"skip-identical", "rename", "update"}:
            raise ValueError("Saved plan has an invalid collision policy.")
        if item.get("status") not in {"planned", "unresolved"}:
            raise ValueError("Saved plan contains a non-plan execution status.")
        formats = item.get("formats")
        if formats is not None and (not isinstance(formats, list) or any(
                value not in {"mdlink", "mdimage", "literal", "html", "jsdelivr"} for value in formats)):
            raise ValueError("Saved plan contains invalid output formats.")
        filename = item.get("filename")
        if not isinstance(filename, str) or os.path.basename(filename) != filename:
            raise ValueError("Saved plan contains an invalid filename.")
        if item["transport"] == "contents" and filename != os.path.basename(item["remote_path"]):
            raise ValueError("Saved plan filename does not match its contents path.")
        item["warnings"] = list(dict.fromkeys(item.get("warnings", []) + _sensitive_reasons(item["source"])))
    return plan

def list_remote(cfg, folder=None, expect_repo=None, expect_account=None):
    _validate_local_destination(cfg, expect_repo, expect_account)
    token = get_token(cfg)
    destination = {"destination": {"owner": cfg["owner"], "repo": cfg["repo"],
                                  "branch": cfg.get("branch", "main")}}
    _guard_destination(cfg, token, destination, expect_repo, expect_account or cfg.get("expected_account"))
    prefix = cfg.get("repo_path_prefix", "").strip("/")
    default_root = f"{prefix}/uploads" if prefix else "uploads"
    folder = sanitize_repo_path(folder) if folder else default_root
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in folder.split("/"))
    branch = urllib.parse.quote(cfg.get("branch", "main"), safe="")
    url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{encoded}?ref={branch}"
    try:
        result = api_request("GET", url, token)
    except RuntimeError as exc:
        if "-> 404" in str(exc):
            result = []
        else:
            raise
    entries = result if isinstance(result, list) else [result]
    items = [{"path": entry.get("path"), "name": entry.get("name"), "type": entry.get("type"),
              "size": entry.get("size"), "sha": entry.get("sha")} for entry in entries]
    return {"destination": {"owner": cfg["owner"], "repo": cfg["repo"], "branch": cfg.get("branch", "main")},
            "items": items, "folders": sorted(item["path"] for item in items if item["type"] == "dir")}


class _CliParser(argparse.ArgumentParser):
    def error(self, message):
        if getattr(self, "_json_requested", False):
            print(json.dumps({"destination": None, "items": [], "warnings": [], "errors": [message]}))
            raise SystemExit(2)
        super().error(message)


def _choose_local_path():
    recent = read_history()
    folders = sorted({record.get("remote_path", "").rsplit("/", 1)[0]
                      for record in recent if record.get("remote_path", "").startswith("uploads/")})
    print("Recent upload folders:", file=sys.stderr)
    for index, folder in enumerate(folders, 1):
        print(f"  {index}. {folder.removeprefix('uploads/')}", file=sys.stderr)
    sys.stderr.write("Choose a number or type a folder under uploads/: ")
    sys.stderr.flush()
    choice = input().strip()
    if choice.isdigit() and 1 <= int(choice) <= len(folders):
        folder = folders[int(choice) - 1]
        return sanitize_repo_path(folder[len("uploads/"):])
    if choice.startswith("uploads/"):
        choice = choice[len("uploads/"):]
    return sanitize_repo_path(choice)


def main(argv=None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    terminator = raw_argv.index("--") if "--" in raw_argv else len(raw_argv)
    option_args = raw_argv[:terminator]
    if "--menu" in option_args:
        option_args.remove("--menu")
        from gupload_menu import main as menu_main
        return menu_main(option_args + raw_argv[terminator:])
    if "--dialog" in option_args:
        option_args.remove("--dialog")
        from gupload_platform import dialog_main
        return dialog_main(option_args + raw_argv[terminator:])
    parser = _CliParser(description="Plan or execute GitHub uploads", allow_abbrev=False)
    parser.add_argument("files", nargs="*")
    parser.add_argument("-n", "--name")
    parser.add_argument("--names", nargs="+")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--plan", "--preview", "--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--check-remote", action="store_true")
    parser.add_argument("--list-remote", nargs="?", const="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--save-plan")
    parser.add_argument("--apply-plan")
    parser.add_argument("--path", nargs="?", const=PATH_PICK_SENTINEL)
    parser.add_argument("--preset")
    parser.add_argument("--collision", choices=("skip-identical", "rename", "update"))
    parser.add_argument("--format")
    parser.add_argument("--allow-sensitive", action="store_true")
    parser.add_argument("--expect-repo")
    parser.add_argument("--expect-account")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--detect-category", action="store_true")
    parser._json_requested = "--json" in raw_argv
    args = parser.parse_args(raw_argv)
    if args.files:
        from gupload_platform import normalize_inputs
        args.files = normalize_inputs(args.files)
    if args.retry_failed and (args.files or args.apply_plan):
        parser.error("--retry-failed cannot be combined with files or --apply-plan.")
    if args.detect_category:
        for path, category in detect_categories(args.files):
            print(f"{path}\t{category}")
        return 0
    if args.apply_plan and not args.execute:
        parser.error("--apply-plan requires --execute.")
    if args.name and (args.names or len(args.files) != 1):
        parser.error("--name requires one input and cannot be combined with --names.")
    if args.names and len(args.names) != len(args.files):
        parser.error("--names must contain exactly one name per input.")
    if args.execute and not args.apply_plan and not args.files and not args.retry_failed and args.list_remote is None:
        parser.error("--execute requires inputs or --apply-plan.")
    if args.execute and args.check_remote:
        parser.error("--execute and --check-remote are separate operations.")
    if args.execute and args.list_remote is not None:
        parser.error("--list-remote is read-only and cannot be combined with --execute.")
    if args.apply_plan and args.files:
        parser.error("--apply-plan cannot be combined with input files.")
    if args.save_plan and args.apply_plan:
        parser.error("--save-plan cannot be combined with --apply-plan.")
    if args.plan and args.execute:
        parser.error("--plan cannot be combined with --execute.")
    if not args.files and not args.apply_plan and not args.retry_failed and args.list_remote is None:
        parser.error("provide files, URLs, --list-remote, or --retry-failed.")
    if args.apply_plan and any((args.path is not None, args.preset is not None, args.name is not None,
                                args.names is not None, args.format is not None, args.collision is not None)):
        parser.error("--apply-plan cannot override reviewed naming, path, format, preset, or collision settings.")
    if args.path == PATH_PICK_SENTINEL:
        if args.json:
            parser.error("--path requires an explicit value when --json is requested.")
        try:
            args.path = _choose_local_path()
        except (EOFError, OSError, ValueError) as exc:
            parser.error(f"Could not choose --path: {exc}")
    try:
        cfg = load_config()
    except (OSError, ValueError) as exc:
        parser.error(f"Could not load configuration: {exc}")
    preset = None
    if args.preset:
        preset = get_presets(cfg).get(args.preset)
        if preset is None:
            parser.error(f"Unknown preset: {args.preset}")
        cfg = dict(cfg)
        cfg["_active_preset"] = {"name": args.preset, **preset}
    if args.list_remote is not None:
        try:
            _validate_local_destination(cfg, args.expect_repo, args.expect_account)
            result = list_remote(cfg, args.list_remote or None, args.expect_repo, args.expect_account)
        except Exception as exc:
            result = {"destination": {"owner": cfg.get("owner"), "repo": cfg.get("repo"),
                                      "branch": cfg.get("branch", "main")}, "items": [], "folders": [],
                      "errors": [str(exc)]}
        print(json.dumps(result, ensure_ascii=False) if args.json else json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result.get("errors") else 0
    formats = [part.strip().lower() for part in args.format.split(",") if part.strip()] if args.format else (preset or {}).get("formats")
    if formats and any(fmt not in {"mdlink", "mdimage", "literal", "html", "jsdelivr"} for fmt in formats):
        parser.error("Invalid --format value.")
    try:
        if args.retry_failed:
            plan = build_retry_plan(cfg)
        elif args.apply_plan:
            plan = _load_saved_plan(args.apply_plan, cfg, args.expect_repo)
        else:
            plan = build_plan(args.files, cfg, [args.name] if args.name else args.names, args.path,
                              args.collision or (preset or {}).get("collision"), formats)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    if args.save_plan:
        try:
            plan["plan_sha256"] = _plan_integrity(plan)
            write_json(args.save_plan, plan)
        except (OSError, ValueError) as exc:
            parser.error(f"Could not save plan: {exc}")
    if args.execute and plan["items"]:
        try:
            plan = execute_plan(plan, cfg, args.allow_sensitive, args.expect_repo, args.expect_account)
        except Exception as exc:
            plan["errors"].append(str(exc))
    elif args.check_remote:
        try:
            _validate_local_destination(cfg, args.expect_repo, args.expect_account)
            token = get_token(cfg)
            _guard_destination(cfg, token, plan, args.expect_repo, args.expect_account or cfg.get("expected_account"))
            for item in plan["items"]:
                if item["status"] == "planned":
                    resolve_remote_collision(cfg, token, item)
        except Exception as exc:
            plan["errors"].append(str(exc))
    plan["errors"] = list(dict.fromkeys(plan.get("errors", []) + [
        f"{item.get('source')}: {item['error']}" for item in plan["items"]
        if item.get("status") == "failed" and item.get("error")]))
    plan["warnings"] = list(dict.fromkeys(
        plan.get("warnings", []) + [warning for item in plan["items"] for warning in item.get("warnings", [])]))
    if args.execute:
        successful_outputs = [item["output"] for item in plan["items"]
                              if item.get("status") == "succeeded" and item.get("output")]
        if successful_outputs:
            try:
                from gupload_platform import clipboard_set
                clipboard_set("\n\n".join(successful_outputs).strip() + "\n")
            except ImportError:
                pass
    if args.json:
        print(json.dumps(plan, ensure_ascii=False))
    else:
        for item in plan["items"]:
            print(f"{item.get('status')}: {item.get('source')} -> {item.get('remote_path')} ({item.get('transport')})")
            for warning in item.get("warnings", []):
                print(f"  warning: {warning}")
            if item.get("output"):
                print(item["output"])
            if item.get("error"):
                eprint(f"Error: {item['error']}")
    return 1 if plan.get("errors") or any(item.get("status") == "failed" for item in plan["items"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
