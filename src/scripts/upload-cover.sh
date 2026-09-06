#!/bin/bash
# Upload album cover from URL with automatic naming
# Usage: upload-cover.sh <url> <artist_name> <year> <album_name>

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory (works even when symlinked)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Use GHU from environment if set, otherwise calculate from script location
if [[ -z "${GHU:-}" ]]; then
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
    GHU="$REPO_ROOT/ghu"
fi

# Fallback: If ghu not found, try to find it via common locations
if [[ ! -x "$GHU" ]]; then
    if [[ -x "/Volumes/Eksternal/Projects/Gupload/ghu" ]]; then
        GHU="/Volumes/Eksternal/Projects/Gupload/ghu"
    elif [[ -x "$HOME/Scripts/Riley/Gupload/ghu" ]]; then
        GHU="$HOME/Scripts/Riley/Gupload/ghu"
    elif command -v ghu &> /dev/null; then
        GHU="$(command -v ghu)"
    else
        echo -e "${RED}Error: Gupload script not found${NC}" >&2
        exit 1
    fi
fi

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <url> <artist_name> [year] [album_name]"
    echo "       $0 <url> \"Custom Name.jpg\""
    echo ""
    echo "Examples:"
    echo "  $0 https://f4.bcbits.com/img/a1454706092_5.jpg \"Deteriorate\" \"1993\" \"Rotting in Hell\""
    echo "  $0 https://example.com/cover.jpg \"Deteriorate - 1993 - Rotting in Hell.jpg\""
    exit 1
fi

URL="$1"
shift

# If only one argument left and it contains " - " or ends with .jpg/.png, treat as custom name
if [[ $# -eq 1 ]] && ([[ "$1" == *" - "* ]] || [[ "$1" == *.jpg ]] || [[ "$1" == *.png ]] || [[ "$1" == *.jpeg ]]); then
    CUSTOM_NAME="$1"
    echo -e "${GREEN}Uploading cover from URL with custom name: ${CUSTOM_NAME}${NC}"
    "$GHU" --name "$CUSTOM_NAME" "$URL"
else
    # Parse artist, year, album
    ARTIST="$1"
    YEAR="${2:-}"
    ALBUM="${3:-}"
    
    if [[ -n "$YEAR" ]] && [[ -n "$ALBUM" ]]; then
        CUSTOM_NAME="${ARTIST} - ${YEAR} - ${ALBUM}.jpg"
    elif [[ -n "$ALBUM" ]]; then
        CUSTOM_NAME="${ARTIST} - ${ALBUM}.jpg"
    else
        CUSTOM_NAME="${ARTIST} cover.jpg"
    fi
    
    echo -e "${GREEN}Uploading cover from URL: ${CUSTOM_NAME}${NC}"
    "$GHU" --name "$CUSTOM_NAME" "$URL"
fi
