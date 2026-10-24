#!/usr/bin/env bash
# Offline plan by default; pass --execute to explicitly publish.
# Usage: upload-cover.sh [--plan|--execute] [--expect-repo OWNER/REPO] <url> <artist_name> [year] [album_name]

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
    GHU="$REPO_ROOT/bin/gupload"
fi

if [[ ! -x "$GHU" ]]; then
    if command -v gupload >/dev/null 2>&1; then
        GHU="$(command -v gupload)"
    else
        echo -e "${RED}Error: Gupload script not found${NC}" >&2
        echo "Set GHU to its launcher path or add gupload to PATH." >&2
        exit 1
    fi
fi

UPLOAD_MODE="--plan"
MODE_SPECIFIED=0
GUARD_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --execute|--plan|--preview|--dry-run)
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
        -*)
            echo "Error: unsupported option: $1" >&2
            exit 2
            ;;
        *)
            break
            ;;
    esac
done
if [[ "$UPLOAD_MODE" == "--preview" || "$UPLOAD_MODE" == "--dry-run" ]]; then
    UPLOAD_MODE="--plan"
fi

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 [--plan|--execute] [--expect-repo OWNER/REPO] <url> <artist_name> [year] [album_name]"
    echo "       $0 [--plan|--execute] [--expect-repo OWNER/REPO] <url> \"Custom Name.jpg\""
    echo ""
    echo "Examples:"
    echo "  $0 https://f4.bcbits.com/img/a1454706092_5.jpg \"Deteriorate\" \"1993\" \"Rotting in Hell\""
    echo "  $0 https://example.com/cover.jpg \"Deteriorate - 1993 - Rotting in Hell.jpg\""
    exit 1
fi

URL="$1"
shift
case "$URL" in
    http://*|https://*)
        URL_REMAINDER="${URL#*://}"
        URL_HOST="${URL_REMAINDER%%[/?#]*}"
        if [[ -z "$URL_HOST" ]]; then
            echo "Error: cover URL must include a host." >&2
            exit 2
        fi
        ;;
    *)
        echo "Error: cover URL must use HTTP or HTTPS." >&2
        exit 2
        ;;
esac

for arg in "$@"; do
    if [[ "$arg" == --* ]]; then
        echo "Error: upload flags must appear before the URL." >&2
        exit 2
    fi
done
if [[ $# -gt 3 ]]; then
    echo "Error: too many cover naming arguments." >&2
    exit 2
fi
# If only one argument left and it contains " - " or ends with .jpg/.png, treat as custom name
if [[ $# -eq 1 ]] && ([[ "$1" == *" - "* ]] || [[ "$1" == *.jpg ]] || [[ "$1" == *.png ]] || [[ "$1" == *.jpeg ]]); then
    CUSTOM_NAME="$1"
    if [[ "$UPLOAD_MODE" == "--execute" ]]; then
        echo -e "${GREEN}Executing cover upload with custom name: ${CUSTOM_NAME}${NC}"
    else
        echo -e "${GREEN}Creating offline cover plan with custom name: ${CUSTOM_NAME}${NC}"
    fi
    "$GHU" "$UPLOAD_MODE" "${GUARD_ARGS[@]+"${GUARD_ARGS[@]}"}" "--name=$CUSTOM_NAME" -- "$URL"
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
    
    if [[ "$UPLOAD_MODE" == "--execute" ]]; then
        echo -e "${GREEN}Executing cover upload: ${CUSTOM_NAME}${NC}"
    else
        echo -e "${GREEN}Creating offline cover plan: ${CUSTOM_NAME}${NC}"
    fi
    "$GHU" "$UPLOAD_MODE" "${GUARD_ARGS[@]+"${GUARD_ARGS[@]}"}" "--name=$CUSTOM_NAME" -- "$URL"
fi
