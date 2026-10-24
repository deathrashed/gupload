#!/usr/bin/env bash

# Upload Artist Assets Script
# Finds and uploads all cover.jpg, logo.png, and artist.jpg files for an artist
#
# Usage:
#   ./upload-artist-assets.sh [--plan|--execute] "/path/to/Artist"
#   Or run without an artist path to be prompted. Plans are the default.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Get script directory (works even when symlinked)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Use GHU from environment if set, otherwise calculate from script location
if [[ -z "${GHU:-}" ]]; then
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
    GHU="$REPO_ROOT/bin/gupload"
fi

if [[ ! -x "$GHU" ]]; then
    if command -v gupload >/dev/null 2>&1; then
        GHU="$(command -v gupload)"
    else
        echo -e "${RED}Error: Gupload script not found${NC}" >&2
        echo -e "${YELLOW}Set GHU to its launcher path or add gupload to PATH.${NC}" >&2
        exit 1
    fi
fi

UPLOAD_MODE=""
MODE_SPECIFIED=0
ARTIST_PATH=""
GUARD_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --plan|--preview|--dry-run|--execute)
            if [[ $MODE_SPECIFIED -eq 1 ]]; then
                echo "Error: specify only one of --plan or --execute." >&2
                exit 2
            fi
            MODE_SPECIFIED=1
            UPLOAD_MODE="$1"
            shift
            ;;
        --expect-repo|--expect-account)
            if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
                echo "Error: $1 requires a value." >&2
                exit 2
            fi
            GUARD_ARGS+=("$1" "$2")
            shift 2
            ;;
        --allow-sensitive)
            GUARD_ARGS+=("$1")
            shift
            ;;
        --)
            shift
            if [[ $# -ne 1 || -n "$ARTIST_PATH" ]]; then
                echo "Usage: $0 [--plan|--execute] [--expect-repo OWNER/REPO] [artist-path]" >&2
                exit 2
            fi
            ARTIST_PATH="$1"
            shift
            ;;
        -*)
            echo "Error: unsupported option: $1" >&2
            exit 2
            ;;
        *)
            if [[ -z "$ARTIST_PATH" ]]; then
                ARTIST_PATH="$1"
                shift
            else
                echo "Usage: $0 [--plan|--execute] [--expect-repo OWNER/REPO] [artist-path]" >&2
                exit 2
            fi
            ;;
    esac
done

if [[ "$UPLOAD_MODE" == "--preview" || "$UPLOAD_MODE" == "--dry-run" ]]; then
    UPLOAD_MODE="--plan"
fi
if [[ -z "$UPLOAD_MODE" ]]; then
    UPLOAD_MODE="--plan"
fi

if [[ -z "$ARTIST_PATH" ]]; then
    echo -e "${CYAN}${BOLD}Upload Artist Assets${NC}\n"
    echo -e "${BLUE}Enter the artist path (e.g., /Volumes/Eksternal/Audio/Metal/C/Cold Steel):${NC}"
    IFS= read -r -e ARTIST_PATH
    echo
fi

# Strip leading/trailing whitespace
ARTIST_PATH="${ARTIST_PATH#"${ARTIST_PATH%%[![:space:]]*}"}"  # Strip leading spaces
ARTIST_PATH="${ARTIST_PATH%"${ARTIST_PATH##*[![:space:]]}"}"  # Strip trailing spaces

# Strip quotes from beginning and end (single or double quotes)
while [[ "$ARTIST_PATH" == \'*\' || "$ARTIST_PATH" == \"*\" ]]; do
    # Remove leading/trailing single quote
    [[ "$ARTIST_PATH" == \'*\' ]] && ARTIST_PATH="${ARTIST_PATH:1:-1}"
    # Remove leading/trailing double quote
    [[ "$ARTIST_PATH" == \"*\" ]] && ARTIST_PATH="${ARTIST_PATH:1:-1}"
done

# Expand tilde
ARTIST_PATH="${ARTIST_PATH/#\~/$HOME}"

# Resolve path to absolute path
if [[ -d "$ARTIST_PATH" ]]; then
    # Directory exists, resolve to absolute path
    ARTIST_PATH="$(cd "$ARTIST_PATH" && pwd)"
elif [[ -e "$ARTIST_PATH" ]]; then
    # File exists, resolve parent directory
    DIR_PATH="$(dirname "$ARTIST_PATH")"
    BASE_NAME="$(basename "$ARTIST_PATH")"
    if [[ -d "$DIR_PATH" ]]; then
        ARTIST_PATH="$(cd "$DIR_PATH" && pwd)/$BASE_NAME"
    fi
else
    # Path doesn't exist yet, try to resolve parent directory
    DIR_PATH="$(dirname "$ARTIST_PATH")"
    BASE_NAME="$(basename "$ARTIST_PATH")"
    if [[ -d "$DIR_PATH" ]]; then
        ARTIST_PATH="$(cd "$DIR_PATH" && pwd)/$BASE_NAME"
    else
        # Can't resolve parent either, use path as-is (will fail validation below)
        :
    fi
fi

# Validate path
if [[ ! -d "$ARTIST_PATH" ]]; then
    echo -e "${RED}Error: Directory not found: $ARTIST_PATH${NC}" >&2
    echo -e "${YELLOW}Please check the path and try again.${NC}" >&2
    exit 1
fi

ARTIST_NAME="$(basename "$ARTIST_PATH")"
echo -e "${CYAN}${BOLD}Uploading assets for: ${ARTIST_NAME}${NC}\n"
echo -e "${BLUE}Path: ${ARTIST_PATH}${NC}\n"

# Find all relevant image files
FILES=()
COVERS=()
LOGOS=()
ARTISTS=()
COVER_COUNT=0
LOGO_COUNT=0
ARTIST_COUNT=0

echo -e "${BLUE}Scanning for assets...${NC}"

# Find cover.jpg files (in album subdirectories)
while IFS= read -r -d '' file; do
    COVERS+=("$file")
    COVER_COUNT=$((COVER_COUNT + 1))
done < <(find "$ARTIST_PATH" -type f -name "cover.jpg" -print0 2>/dev/null)

# Find logo.png files in the artist directory (portable to BSD and GNU find)
while IFS= read -r -d '' file; do
    if [[ "$(dirname "$file")" == "$ARTIST_PATH" ]]; then
        LOGOS+=("$file")
        LOGO_COUNT=$((LOGO_COUNT + 1))
    fi
done < <(find "$ARTIST_PATH" -type f -name "logo.png" -print0 2>/dev/null)

# Find artist.jpg files in the artist directory
while IFS= read -r -d '' file; do
    if [[ "$(dirname "$file")" == "$ARTIST_PATH" ]]; then
        ARTISTS+=("$file")
        ARTIST_COUNT=$((ARTIST_COUNT + 1))
    fi
done < <(find "$ARTIST_PATH" -type f -name "artist.jpg" -print0 2>/dev/null)

# Combine all files using guarded empty-array expansion for Bash 3.2.
FILES=()
FILE_COUNT=0
for f in "${COVERS[@]+"${COVERS[@]}"}" "${LOGOS[@]+"${LOGOS[@]}"}" "${ARTISTS[@]+"${ARTISTS[@]}"}"; do
    if [[ -n "$f" ]]; then
        FILES+=("$f")
        FILE_COUNT=$((FILE_COUNT + 1))
    fi
done

# Display found files
echo -e "\n${BOLD}Found assets:${NC}"
echo -e "  ${GREEN}Covers:${NC} ${COVER_COUNT}"
for cover in "${COVERS[@]+"${COVERS[@]}"}"; do
    rel_path="${cover#$ARTIST_PATH/}"
    echo -e "    - ${rel_path}"
done

echo -e "  ${GREEN}Logos:${NC} ${LOGO_COUNT}"
for logo in "${LOGOS[@]+"${LOGOS[@]}"}"; do
    echo -e "    - $(basename "$logo")"
done

echo -e "  ${GREEN}Artist images:${NC} ${ARTIST_COUNT}"
for artist in "${ARTISTS[@]+"${ARTISTS[@]}"}"; do
    echo -e "    - $(basename "$artist")"
done

if [[ $FILE_COUNT -eq 0 ]]; then
    echo -e "\n${YELLOW}No assets found to upload.${NC}"
    exit 0
fi

echo -e "\n${BOLD}Total files to upload: ${FILE_COUNT}${NC}\n"

if [[ "$UPLOAD_MODE" == "--execute" ]]; then
    PROMPT="Execute upload of these ${FILE_COUNT} files? [y/N]: "
else
    PROMPT="Create an offline plan for these ${FILE_COUNT} files? [y/N]: "
fi
IFS= read -r -n 1 -p "$(echo -e "${YELLOW}${PROMPT}${NC}")" REPLY
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Cancelled.${NC}"
    exit 0
fi

if [[ "$UPLOAD_MODE" == "--execute" ]]; then
    echo -e "\n${BLUE}Executing upload...${NC}\n"
else
    echo -e "\n${BLUE}Creating offline plan...${NC}\n"
fi

if "$GHU" "$UPLOAD_MODE" "${GUARD_ARGS[@]+"${GUARD_ARGS[@]}"}" -- "${FILES[@]}"; then
    if [[ "$UPLOAD_MODE" == "--execute" ]]; then
        echo -e "\n${GREEN}Upload command completed for ${#FILES[@]} files.${NC}"
    else
        echo -e "\n${GREEN}Offline plan completed for ${#FILES[@]} files; no files were uploaded.${NC}"
    fi
else
    status=$?
    echo -e "\n${RED}Gupload failed (exit code: ${status}).${NC}" >&2
    exit "$status"
fi
