#!/usr/bin/env bash

# Gupload Interactive Menu
# Interactive terminal menu for Gupload operations

set -uo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Get script directory (works even when symlinked or called via alias)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
GHU="$REPO_ROOT/ghu"
PYTHON_SCRIPT="$REPO_ROOT/scripts/ghuploader.py"
LIST_ARTISTS_SCRIPT="$SCRIPT_DIR/list-repo-artists.py"
UPLOAD_ASSETS_SCRIPT="$SCRIPT_DIR/upload-artist-assets.sh"
LOG="/tmp/gupload.log"
CONFIG="$HOME/.config/ghuploader/config.json"
DATA_DIR="$HOME/.config/ghuploader/data"
FAVORITES_FILE="$DATA_DIR/favorites.json"
RECENT_FILE="$DATA_DIR/recent.json"

# Create data directory if it doesn't exist
mkdir -p "$DATA_DIR"

# DIM color for subtle text
DIM='\033[2m'

# Fallback: If ghu not found at calculated path, try common locations
if [[ ! -x "$GHU" ]]; then
    if [[ -x "/Volumes/Eksternal/Projects/Gupload/ghu" ]]; then
        GHU="/Volumes/Eksternal/Projects/Gupload/ghu"
        REPO_ROOT="/Volumes/Eksternal/Projects/Gupload"
    elif [[ -x "$HOME/Scripts/Riley/Gupload/ghu" ]]; then
        GHU="$HOME/Scripts/Riley/Gupload/ghu"
        REPO_ROOT="$(cd "$(dirname "$GHU")" && pwd -P)"
    elif command -v ghu &> /dev/null; then
        GHU="$(command -v ghu)"
        REPO_ROOT="$(cd "$(dirname "$GHU")" && pwd -P)"
    fi
    # Update script paths based on resolved REPO_ROOT
    if [[ -n "$REPO_ROOT" ]] && [[ -d "$REPO_ROOT" ]]; then
        PYTHON_SCRIPT="$REPO_ROOT/scripts/ghuploader.py"
        LIST_ARTISTS_SCRIPT="$REPO_ROOT/scripts/list-repo-artists.py"
        UPLOAD_ASSETS_SCRIPT="$REPO_ROOT/scripts/upload-artist-assets.sh"
    fi
fi

# Helper functions
print_header() {
    clear
    echo -e "\n${CYAN}${BOLD}═══════════════════════════════════════════════${NC}"
    echo -e "${CYAN}${BOLD}           Gupload - File Upload Tool${NC}"
    echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════${NC}\n"
}

print_menu() {
    echo -e "${BOLD}Main Menu:${NC}\n"
    echo -e "  ${GREEN}1)${NC}  Upload Files"
    echo -e "  ${GREEN}2)${NC}  Browse Repo & Add Files"
    echo -e "  ${GREEN}3)${NC}  Audio Tools"
    echo -e "  ${GREEN}4)${NC}  Quick Access ${DIM}(history, favorites, queue)${NC}"
    echo -e "  ${GREEN}5)${NC}  Advanced Tools ${DIM}(batch, templates, search)${NC}"
    echo -e "  ${GREEN}6)${NC}  Configure Options"
    echo -e "  ${GREEN}7)${NC}  View Logs"
    echo -e "  ${GREEN}8)${NC}  Stats & Info ${DIM}(stats, help)${NC}\n"
    show_inline_help "main"
    show_nav_footer "main"
}

confirm() {
    local prompt="$1"
    local response
    read -p "$(echo -e ${YELLOW}"$prompt [y/N]: "${NC})" -n 1 -r response
    echo
    [[ $response =~ ^[Yy]$ ]]
}

wait_for_q() {
    echo -e "\n${CYAN}Press 'q' + Enter to go back...${NC}"
    local response
    read -r response
    [[ "$response" != "q" ]]
}

check_ghu() {
    # Try to find ghu if not already set or not executable
    if [[ ! -x "$GHU" ]]; then
        # Try common locations
        if [[ -x "/Volumes/Eksternal/Projects/Gupload/ghu" ]]; then
            GHU="/Volumes/Eksternal/Projects/Gupload/ghu"
            REPO_ROOT="/Volumes/Eksternal/Projects/Gupload"
        elif [[ -x "$HOME/Scripts/Riley/Gupload/ghu" ]]; then
            GHU="$HOME/Scripts/Riley/Gupload/ghu"
            REPO_ROOT="$(cd "$(dirname "$GHU")" && pwd -P)"
        elif command -v ghu &> /dev/null; then
            GHU="$(command -v ghu)"
            REPO_ROOT="$(cd "$(dirname "$GHU")" && pwd -P)"
        else
            echo -e "${RED}Error: Gupload script (ghu) not found${NC}" >&2
            echo -e "${YELLOW}Tried locations:${NC}" >&2
            echo -e "  - $GHU" >&2
            echo -e "  - /Volumes/Eksternal/Projects/Gupload/ghu" >&2
            echo -e "  - $HOME/Scripts/Riley/Gupload/ghu" >&2
            echo -e "${YELLOW}Please ensure ghu is in one of these locations or in PATH${NC}" >&2
            return 1
        fi
    fi
    
    if [[ ! -x "$GHU" ]]; then
        echo -e "${RED}Error: Gupload script not found or not executable: $GHU${NC}" >&2
        return 1
    fi
    
    return 0
}

check_fzf() {
    if ! command -v fzf &> /dev/null; then
        return 1
    fi
    return 0
}

get_config_value() {
    local key="$1"
    python3 -c "import json, sys, os; config = json.load(open('$CONFIG')) if os.path.exists('$CONFIG') else {}; print(config.get('$key', ''))" 2>/dev/null || echo ""
}

set_config_value() {
    local key="$1"
    local value="$2"
    python3 <<PYTHON
import json
import os

config_file = '$CONFIG'
os.makedirs(os.path.dirname(config_file), exist_ok=True)

if os.path.exists(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
else:
    config = {}

config['$key'] = $value

with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
PYTHON
}

# Upload Files Submenu
upload_files_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}Upload Files${NC}\n"
        echo -e "  ${GREEN}1)${NC}  Single file (fzf search)"
        echo -e "  ${GREEN}2)${NC}  Single file (manual path)"
        echo -e "  ${GREEN}3)${NC}  Upload from URL"
        echo -e "  ${GREEN}4)${NC}  Multiple files"
        echo -e "  ${GREEN}5)${NC}  From Finder selection"
        echo -e "  ${GREEN}6)${NC}  Folder/archive"
        echo -e "  ${GREEN}q)${NC}  Back to main menu\n"
        
        read -p "Choose option: " option
        echo
        
        case $option in
            1)
                upload_with_fzf
                ;;
            2)
                upload_single_manual
                ;;
            3)
                upload_from_url_submenu
                ;;
            4)
                upload_multiple_files
                ;;
            5)
                upload_finder_selection
                ;;
            6)
                upload_folder
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Upload with fzf
upload_with_fzf() {
    print_header
    echo -e "${BOLD}Upload File (fzf search)${NC}\n"
    
    if ! check_fzf; then
        echo -e "${RED}fzf is not installed.${NC}"
        echo -e "${BLUE}Install with: brew install fzf${NC}\n"
        wait_for_q
        return
    fi
    
    if ! check_ghu; then
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Searching files... (may take a moment)${NC}\n"
    echo -e "${YELLOW}Enter starting directory (or press Enter for $HOME):${NC}"
    read -e start_dir
    
    # Default to home directory
    [[ -z "$start_dir" ]] && start_dir="$HOME"
    start_dir="${start_dir/#\~/$HOME}"
    
    if [[ ! -d "$start_dir" ]]; then
        echo -e "${RED}Error: Directory not found: $start_dir${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Searching from: $start_dir${NC}\n"
    
    # Find all files and use fzf with better search
    local file_path
    file_path=$(find "$start_dir" -type f 2>/dev/null | \
        fzf \
        --height 40% \
        --border \
        --header="Select file to upload (Ctrl+C or ESC to cancel, '/' to search)" \
        --preview="file {} 2>/dev/null && echo && ls -lh {} 2>/dev/null" \
        --preview-window=down:5 \
        --bind="ctrl-/:toggle-preview" \
        2>&1 || echo "")
    
    if [[ -z "$file_path" ]]; then
        return 0
    fi
    
    upload_with_custom_naming "$file_path"
}

# Upload single file manual
upload_single_manual() {
    print_header
    echo -e "${BOLD}Upload File (manual path)${NC}\n"
    
    if ! check_ghu; then
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Enter file path:${NC}"
    read -e file_path
    
    if [[ -z "$file_path" ]] || [[ "$file_path" == "q" ]]; then
        return 0
    fi
    
    # Expand tilde
    file_path="${file_path/#\~/$HOME}"
    
    if [[ ! -f "$file_path" ]]; then
        echo -e "${RED}Error: File not found: $file_path${NC}\n"
        wait_for_q
        return
    fi
    
    upload_with_custom_naming "$file_path"
}

# Upload with custom naming options
upload_with_custom_naming() {
    local file_path="$1"
    
    print_header
    echo -e "${BOLD}Upload: $(basename "$file_path")${NC}\n"
    
    echo -e "${BLUE}File:${NC} $file_path"
    echo -e "${BLUE}Size:${NC} $(du -h "$file_path" | cut -f1)"
    echo
    
    echo -e "${BOLD}Naming Options:${NC}"
    echo -e "  ${GREEN}1)${NC}  Default (auto-generated from path/metadata)"
    echo -e "  ${GREEN}2)${NC}  Custom filename only"
    echo -e "  ${GREEN}3)${NC}  Custom path with folders"
    echo -e "  ${GREEN}q)${NC}  Cancel\n"
    
    read -p "Choose option: " option
    echo
    
    case $option in
        1)
            echo -e "\n${BLUE}Uploading with default naming...${NC}\n"
            "$GHU" "$file_path" 2>&1
            local exit_code=$?
            if [[ $exit_code -eq 0 ]]; then
                echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
            else
                echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
            fi
            wait_for_q
            ;;
        2)
            read -e -p "Enter custom filename (with extension): " custom_name
            if [[ -n "$custom_name" ]] && [[ "$custom_name" != "q" ]]; then
                echo -e "\n${BLUE}Uploading with custom name: $custom_name${NC}\n"
                "$GHU" --name "$custom_name" "$file_path" 2>&1
                local exit_code=$?
                if [[ $exit_code -eq 0 ]]; then
                    echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
                else
                    echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
                fi
            fi
            wait_for_q
            ;;
        3)
            read -e -p "Enter custom path (e.g., MyFolder/myfile.txt or Scripts/Tool/script.py): " custom_path
            if [[ -n "$custom_path" ]] && [[ "$custom_path" != "q" ]]; then
                local filename=$(basename "$custom_path")
                echo -e "\n${BLUE}Uploading to custom path: $custom_path${NC}\n"
                "$GHU" --name "$filename" "$file_path" 2>&1
                local exit_code=$?
                if [[ $exit_code -eq 0 ]]; then
                    echo -e "\n${GREEN}✓ Upload complete!${NC}"
                    echo -e "${YELLOW}Note: File uploaded as '$filename'. Category organization still applies.${NC}\n"
                else
                    echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
                fi
            fi
            wait_for_q
            ;;
        q)
            return 0
            ;;
    esac
}

# Upload multiple files
upload_multiple_files() {
    print_header
    echo -e "${BOLD}Upload Multiple Files${NC}\n"
    
    if ! check_ghu; then
        wait_for_q
        return
    fi
    
    echo -e "${YELLOW}Enter file paths (one per line, empty line to finish, 'q' to cancel):${NC}\n"
    
    files=()
    while true; do
        read -e file_path
        if [[ -z "$file_path" ]]; then
            break
        fi
        if [[ "$file_path" == "q" ]]; then
            return 0
        fi
        
        file_path="${file_path/#\~/$HOME}"
        
        if [[ -f "$file_path" ]]; then
            files+=("$file_path")
            echo -e "${GREEN}✓ Added: $(basename "$file_path")${NC}"
        elif [[ -d "$file_path" ]]; then
            if confirm "Add all files from: $(basename "$file_path")?"; then
                while IFS= read -r -d '' f; do
                    files+=("$f")
                done < <(find "$file_path" -type f -print0)
            fi
        else
            echo -e "${RED}✗ Not found: $file_path${NC}"
        fi
    done
    
    if [[ ${#files[@]} -eq 0 ]]; then
        echo -e "\n${YELLOW}No files to upload.${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "\n${BLUE}Uploading ${#files[@]} file(s)...${NC}\n"
    "$GHU" "${files[@]}" 2>&1
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
    else
        echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
    fi
    wait_for_q
}

# Upload folder
upload_folder() {
    print_header
    echo -e "${BOLD}Upload Folder/Archive${NC}\n"
    
    echo -e "${BLUE}Enter folder or archive path:${NC}"
    read -e folder_path
    
    if [[ -z "$folder_path" ]] || [[ "$folder_path" == "q" ]]; then
        return 0
    fi
    
    folder_path="${folder_path/#\~/$HOME}"
    
    if [[ ! -e "$folder_path" ]]; then
        echo -e "${RED}Error: Path not found: $folder_path${NC}\n"
        wait_for_q
        return
    fi
    
    if [[ -f "$folder_path" ]]; then
        upload_with_custom_naming "$folder_path"
        return
    fi
    
    if [[ ! -d "$folder_path" ]]; then
        echo -e "${RED}Error: Not a directory: $folder_path${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Scanning directory...${NC}\n"
    
    local files=()
    while IFS= read -r -d '' file; do
        files+=("$file")
    done < <(find "$folder_path" -type f -print0)
    
    if [[ ${#files[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No files found.${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BOLD}Found ${#files[@]} files:${NC}\n"
    printf "  %s\n" "${files[@]}" | head -20
    [[ ${#files[@]} -gt 20 ]] && echo -e "  ${YELLOW}... and $(( ${#files[@]} - 20 )) more${NC}"
    echo
    
    if confirm "Upload all ${#files[@]} files?"; then
        echo -e "\n${BLUE}Uploading...${NC}\n"
        "$GHU" "${files[@]}" 2>&1
        local exit_code=$?
        if [[ $exit_code -eq 0 ]]; then
            echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
        else
            echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
        fi
    fi
    
    wait_for_q
}

# Browse Repo Submenu
browse_repo_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}Browse Repo & Add Files${NC}\n"
        
        echo -e "${BOLD}Browse by:${NC}"
        echo -e "  ${GREEN}1)${NC}  Artists (Audio category)"
        echo -e "  ${GREEN}2)${NC}  All categories (Images, Docs, Scripts, etc.)"
        echo -e "  ${GREEN}q)${NC}  Back to main menu\n"
        
        read -p "Choose option: " browse_option
        echo
        
        case $browse_option in
            1)
                browse_artists_from_repo
                ;;
            2)
                browse_all_categories
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Browse artists from repo
browse_artists_from_repo() {
    while true; do
        print_header
        echo -e "${BOLD}Browse Artists in Repo${NC}\n"
        
        echo -e "${BLUE}Loading artists from repo...${NC}\n"
        
        # List artists from repo
        local artists=()
        if [[ -x "$LIST_ARTISTS_SCRIPT" ]]; then
            while IFS= read -r artist; do
                [[ -n "$artist" ]] && artists+=("$artist")
            done < <("$LIST_ARTISTS_SCRIPT" 2>/dev/null || true)
        fi
        
        if [[ ${#artists[@]} -eq 0 ]]; then
            echo -e "${YELLOW}No artists found in repo yet.${NC}\n"
            echo -e "${BLUE}Enter artist path manually:${NC}\n"
            read -e -p "Artist path: " artist_path
            if [[ -n "$artist_path" ]] && [[ "$artist_path" != "q" ]]; then
                add_files_to_artist "$artist_path"
            fi
            wait_for_q
            return
        fi
        
        echo -e "${BOLD}Artists in repo:${NC}\n"
        for i in "${!artists[@]}"; do
            echo -e "  ${GREEN}$((i+1)))${NC}  ${artists[i]}"
        done
        echo -e "  ${GREEN}0)${NC}  Enter artist path manually"
        echo -e "  ${GREEN}q)${NC}  Back\n"
        
        read -p "Choose artist: " choice
        echo
        
        if [[ "$choice" == "q" ]]; then
            return 0
        fi
        
        if [[ "$choice" == "0" ]]; then
            read -e -p "Enter artist path: " artist_path
            if [[ -n "$artist_path" ]] && [[ "$artist_path" != "q" ]]; then
                add_files_to_artist "$artist_path"
            fi
            continue
        fi
        
        local idx=$((choice - 1))
        if [[ $idx -ge 0 ]] && [[ $idx -lt ${#artists[@]} ]]; then
            local artist_name="${artists[$idx]}"
            add_files_to_artist_menu "$artist_name"
        else
            echo -e "${RED}Invalid selection${NC}\n"
            sleep 1
        fi
    done
}

# Browse all categories
browse_all_categories() {
    print_header
    echo -e "${BOLD}Browse All Categories${NC}\n"
    
    echo -e "${BLUE}This feature lists all files in the repo by category.${NC}\n"
    echo -e "${BOLD}Categories:${NC}"
    echo -e "  ${GREEN}1)${NC}  Audio"
    echo -e "  ${GREEN}2)${NC}  Images"
    echo -e "  ${GREEN}3)${NC}  Docs"
    echo -e "  ${GREEN}4)${NC}  Scripts"
    echo -e "  ${GREEN}5)${NC}  Archives"
    echo -e "  ${GREEN}6)${NC}  Other"
    echo -e "  ${GREEN}q)${NC}  Back\n"
    
    read -p "Choose category: " category_choice
    echo
    
    if [[ "$category_choice" == "q" ]]; then
        return 0
    fi
    
    local category_map=("" "Audio" "Images" "Docs" "Scripts" "Archives" "Other")
    local category="${category_map[$category_choice]:-}"
    
    if [[ -z "$category" ]]; then
        echo -e "${RED}Invalid category${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Listing files in $category category...${NC}\n"
    echo -e "${YELLOW}Note: Full repo browsing coming soon. For now, use file upload options.${NC}\n"
    wait_for_q
}

# Add files to artist menu
add_files_to_artist_menu() {
    local artist_name="$1"
    
    while true; do
        print_header
        echo -e "${BOLD}Add Files to: $artist_name${NC}\n"
        
        # Try to find artist path locally
        local artist_path=$(find /Volumes/Eksternal/Audio -type d -name "$artist_name" -maxdepth 4 2>/dev/null | head -1)
        
        if [[ -z "$artist_path" ]]; then
            echo -e "${YELLOW}Artist path not found locally.${NC}"
            read -e -p "Enter artist path: " artist_path
            if [[ -z "$artist_path" ]] || [[ "$artist_path" == "q" ]]; then
                return 0
            fi
        fi
        
        if [[ ! -d "$artist_path" ]]; then
            echo -e "${RED}Error: Directory not found: $artist_path${NC}\n"
            wait_for_q
            return 1
        fi
        
        echo -e "${BLUE}Path: $artist_path${NC}\n"
        
        echo -e "${BOLD}Options:${NC}"
        echo -e "  ${GREEN}1)${NC}  Upload audio files (tracks)"
        echo -e "  ${GREEN}2)${NC}  Upload specific files"
        echo -e "  ${GREEN}3)${NC}  Upload all files in directory"
        echo -e "  ${GREEN}q)${NC}  Back\n"
        
        read -p "Choose option: " option
        echo
        
        case $option in
            1)
                upload_artist_audio "$artist_path"
                ;;
            2)
                upload_artist_files "$artist_path"
                ;;
            3)
                upload_directory "$artist_path"
                ;;
            q)
                return 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Add files to artist (generic)
add_files_to_artist() {
    local artist_path="$1"
    add_files_to_artist_menu "$(basename "$artist_path")"
}

# Upload artist audio
upload_artist_audio() {
    local artist_path="$1"
    
    print_header
    echo -e "${BOLD}Upload Audio Files${NC}\n"
    echo -e "${BLUE}Artist: $(basename "$artist_path")${NC}\n"
    
    echo -e "${BLUE}Finding audio files...${NC}\n"
    
    local audio_files=()
    while IFS= read -r -d '' file; do
        audio_files+=("$file")
    done < <(find "$artist_path" -type f \( -name "*.mp3" -o -name "*.flac" -o -name "*.m4a" -o -name "*.wav" -o -name "*.aac" \) -print0 2>/dev/null)
    
    if [[ ${#audio_files[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No audio files found.${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BOLD}Found ${#audio_files[@]} audio files:${NC}\n"
    printf "  %s\n" "${audio_files[@]}" | head -20
    [[ ${#audio_files[@]} -gt 20 ]] && echo -e "  ${YELLOW}... and $(( ${#audio_files[@]} - 20 )) more${NC}"
    echo
    
    if confirm "Upload all ${#audio_files[@]} audio files?"; then
        echo -e "\n${BLUE}Uploading...${NC}\n"
        "$GHU" "${audio_files[@]}" 2>&1
        local exit_code=$?
        if [[ $exit_code -eq 0 ]]; then
            echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
        else
            echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
        fi
    fi
    
    wait_for_q
}

# Upload artist files
upload_artist_files() {
    local artist_path="$1"
    
    print_header
    echo -e "${BOLD}Upload Specific Files${NC}\n"
    echo -e "${BLUE}Artist: $(basename "$artist_path")${NC}\n"
    
    if check_fzf; then
        echo -e "${BLUE}Select files with fzf...${NC}\n"
        # Use mapfile to properly handle filenames with spaces
        local files=()
        while IFS= read -r -d '' file; do
            files+=("$file")
        done < <(find "$artist_path" -type f -print0 2>/dev/null | \
            fzf --multi --height 40% --border \
                --bind="ctrl-/:toggle-preview" \
                --preview="file {} 2>/dev/null && ls -lh {} 2>/dev/null" \
                --preview-window=down:3 \
                --print0 2>/dev/null || true)
    else
        echo -e "${YELLOW}Enter file paths (one per line, empty to finish):${NC}\n"
        local files=()
        while read -e file_path; do
            [[ -z "$file_path" ]] && break
            [[ "$file_path" == "q" ]] && return 0
            file_path="$artist_path/$file_path"
            [[ -f "$file_path" ]] && files+=("$file_path")
        done
    fi
    
    if [[ ${#files[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No files selected.${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "\n${BLUE}Uploading ${#files[@]} file(s)...${NC}\n"
    "$GHU" "${files[@]}" 2>&1
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
    else
        echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
    fi
    wait_for_q
}

# Upload directory
upload_directory() {
    local dir_path="$1"
    
    echo -e "${BLUE}Scanning directory...${NC}\n"
    
    local files=()
    while IFS= read -r -d '' file; do
        files+=("$file")
    done < <(find "$dir_path" -type f -print0)
    
    if [[ ${#files[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No files found.${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BOLD}Found ${#files[@]} files:${NC}\n"
    printf "  %s\n" "${files[@]}" | head -20
    [[ ${#files[@]} -gt 20 ]] && echo -e "  ${YELLOW}... and $(( ${#files[@]} - 20 )) more${NC}"
    echo
    
    if confirm "Upload all ${#files[@]} files?"; then
        echo -e "\n${BLUE}Uploading...${NC}\n"
        "$GHU" "${files[@]}" 2>&1
        local exit_code=$?
        if [[ $exit_code -eq 0 ]]; then
            echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
        else
            echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
        fi
    fi
    
    wait_for_q
}

# Upload artist assets
upload_artist_assets() {
    print_header
    echo -e "${BOLD}Upload Artist Assets${NC}\n"
    
    if [[ ! -x "$UPLOAD_ASSETS_SCRIPT" ]]; then
        echo -e "${RED}Error: Upload artist assets script not found${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Enter artist path (e.g., /Volumes/Eksternal/Audio/Metal/C/Cold Steel):${NC}"
    read -e artist_path
    
    if [[ -z "$artist_path" ]] || [[ "$artist_path" == "q" ]]; then
        return 0
    fi
    
    echo
    
    # Strip quotes from path if present
    artist_path="${artist_path#"${artist_path%%[![:space:]]*}"}"  # Strip leading spaces
    artist_path="${artist_path%"${artist_path##*[![:space:]]}"}"  # Strip trailing spaces
    
    # Strip quotes from beginning and end (single or double quotes)
    while [[ "$artist_path" == \'*\' || "$artist_path" == \"*\" ]]; do
        [[ "$artist_path" == \'*\' ]] && artist_path="${artist_path:1:-1}"
        [[ "$artist_path" == \"*\" ]] && artist_path="${artist_path:1:-1}"
    done
    
    # Expand tilde
    artist_path="${artist_path/#\~/$HOME}"
    
    if [[ ! -d "$artist_path" ]]; then
        echo -e "${RED}Error: Directory not found: $artist_path${NC}\n"
        wait_for_q
        return
    fi
    
    # Pass GHU path to child script via environment
    GHU="$GHU" "$UPLOAD_ASSETS_SCRIPT" "$artist_path"
    local exit_code=$?
    echo
    
    if [[ $exit_code -eq 0 ]]; then
        echo -e "${GREEN}✓ Upload complete!${NC}\n"
    else
        echo -e "${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
    fi
    
    wait_for_q
}

# Upload from Finder
upload_finder_selection() {
    print_header
    echo -e "${BOLD}Upload from Finder Selection${NC}\n"
    
    if ! check_ghu; then
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Please select files in Finder, then press Enter...${NC}"
    read
    
    echo -e "\n${BLUE}Uploading selected files...${NC}\n"
    "$GHU"
    
    echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
    wait_for_q
}

# Audio Tools Submenu
audio_tools_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}Audio Tools${NC}\n"
        echo -e "  ${GREEN}1)${NC}  Browse artists & add files"
        echo -e "  ${GREEN}2)${NC}  Upload artist assets (covers, logos, artist images)"
        echo -e "  ${GREEN}3)${NC}  Upload audio files for artist"
        echo -e "  ${GREEN}4)${NC}  Upload album cover from URL"
        echo -e "  ${GREEN}q)${NC}  Back to main menu\n"
        
        read -p "Choose option: " option
        echo
        
        case $option in
            1)
                browse_artists_from_repo
                ;;
            2)
                upload_artist_assets
                ;;
            3)
                upload_audio_files_artist
                ;;
            4)
                upload_cover_from_url
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Upload audio files for artist
upload_audio_files_artist() {
    print_header
    echo -e "${BOLD}Upload Audio Files for Artist${NC}\n"
    
    # List artists from repo
    echo -e "${BLUE}Loading artists from repo...${NC}\n"
    
    local artists=()
    if [[ -x "$LIST_ARTISTS_SCRIPT" ]]; then
        while IFS= read -r artist; do
            [[ -n "$artist" ]] && artists+=("$artist")
        done < <("$LIST_ARTISTS_SCRIPT" 2>/dev/null || true)
    fi
    
    if [[ ${#artists[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No artists found in repo yet.${NC}\n"
        read -e -p "Enter artist path: " artist_path
        if [[ -n "$artist_path" ]] && [[ "$artist_path" != "q" ]]; then
            upload_artist_audio "$artist_path"
        fi
        wait_for_q
        return
    fi
    
    echo -e "${BOLD}Artists in repo:${NC}\n"
    for i in "${!artists[@]}"; do
        echo -e "  ${GREEN}$((i+1)))${NC}  ${artists[i]}"
    done
    echo -e "  ${GREEN}0)${NC}  Enter artist path manually"
    echo -e "  ${GREEN}q)${NC}  Back\n"
    
    read -p "Choose artist: " choice
    echo
    
    if [[ "$choice" == "q" ]]; then
        return 0
    fi
    
    if [[ "$choice" == "0" ]]; then
        read -e -p "Enter artist path: " artist_path
        if [[ -n "$artist_path" ]] && [[ "$artist_path" != "q" ]]; then
            upload_artist_audio "$artist_path"
        fi
        wait_for_q
        return
    fi
    
    local idx=$((choice - 1))
    if [[ $idx -ge 0 ]] && [[ $idx -lt ${#artists[@]} ]]; then
        local artist_name="${artists[$idx]}"
        local artist_path=$(find /Volumes/Eksternal/Audio -type d -name "$artist_name" -maxdepth 4 2>/dev/null | head -1)
        
        if [[ -z "$artist_path" ]]; then
            read -e -p "Enter artist path: " artist_path
            [[ -z "$artist_path" ]] && return 0
        fi
        
        [[ -d "$artist_path" ]] && upload_artist_audio "$artist_path"
    else
        echo -e "${RED}Invalid selection${NC}\n"
        sleep 1
    fi
    
    wait_for_q
}

# Upload cover from URL
upload_cover_from_url() {
    print_header
    echo -e "${BOLD}Upload Album Cover from URL${NC}\n"
    
    if ! check_ghu; then
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Enter cover image URL:${NC}"
    echo -e "${YELLOW}Example: https://f4.bcbits.com/img/a1454706092_5.jpg${NC}"
    read -e url
    
    if [[ -z "$url" ]] || [[ "$url" == "q" ]]; then
        return 0
    fi
    
    # Basic URL validation
    if [[ ! "$url" =~ ^https?:// ]]; then
        echo -e "${RED}Error: Invalid URL. Must start with http:// or https://${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "\n${BLUE}Enter artist name:${NC}"
    read -e artist_name
    
    if [[ -z "$artist_name" ]] || [[ "$artist_name" == "q" ]]; then
        return 0
    fi
    
    echo -e "${BLUE}Enter year (optional, press Enter to skip):${NC}"
    read -e year
    
    echo -e "${BLUE}Enter album name:${NC}"
    read -e album_name
    
    if [[ -z "$album_name" ]] || [[ "$album_name" == "q" ]]; then
        return 0
    fi
    
    # Build filename
    if [[ -n "$year" ]]; then
        custom_name="${artist_name} - ${year} - ${album_name}.jpg"
    else
        custom_name="${artist_name} - ${album_name}.jpg"
    fi
    
    echo -e "\n${BLUE}Uploading cover: $custom_name${NC}\n"
    
    if [[ -x "$REPO_ROOT/scripts/upload-cover.sh" ]]; then
        # Use helper script if available
        if [[ -n "$year" ]]; then
            "$REPO_ROOT/scripts/upload-cover.sh" "$url" "$artist_name" "$year" "$album_name"
        else
            "$REPO_ROOT/scripts/upload-cover.sh" "$url" "$artist_name" "" "$album_name"
        fi
    else
        # Fallback to direct ghu call
        "$GHU" --name "$custom_name" "$url" 2>&1
    fi
    
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
    else
        echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
    fi
    
    wait_for_q
}

# Configure Options Submenu
configure_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}Configure Options${NC}\n"
        
        local current_mode=$(get_config_value "output_mode" || echo "markdown")
        
        echo -e "  ${GREEN}1)${NC}  Clipboard/Output mode (current: $current_mode)"
        echo -e "  ${GREEN}q)${NC}  Back to main menu\n"
        
        read -p "Choose option: " option
        echo
        
        case $option in
            1)
                configure_clipboard_mode
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Configure clipboard mode
configure_clipboard_mode() {
    while true; do
        print_header
        echo -e "${BOLD}Configure Output/Clipboard Mode${NC}\n"
        
        local current_mode=$(get_config_value "output_mode" || echo "markdown")
        
        echo -e "${BLUE}Current mode: ${BOLD}$current_mode${NC}\n"
        echo -e "${BLUE}This controls what gets copied to clipboard after upload${NC}\n"
        echo -e "${BOLD}Options:${NC}"
        echo -e "  ${GREEN}1)${NC}  Markdown only - [file.jpg](url)"
        echo -e "  ${GREEN}2)${NC}  URLs only - just the raw URLs"
        echo -e "  ${GREEN}3)${NC}  Both markdown and URLs"
        echo -e "  ${GREEN}q)${NC}  Back\n"
        
        read -p "Choose option: " option
        echo
        
        case $option in
            1)
                set_config_value "output_mode" "\"markdown\""
                echo -e "${GREEN}✓ Output mode set to: markdown${NC}\n"
                sleep 1
                return 0
                ;;
            2)
                set_config_value "output_mode" "\"url\""
                echo -e "${GREEN}✓ Output mode set to: url${NC}\n"
                sleep 1
                return 0
                ;;
            3)
                set_config_value "output_mode" "\"both\""
                echo -e "${GREEN}✓ Output mode set to: both${NC}\n"
                sleep 1
                return 0
                ;;
            q)
                return 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# View logs submenu
view_logs_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}View Logs${NC}\n"
        
        echo -e "  ${GREEN}1)${NC}  Recent uploads (last 50 lines)"
        echo -e "  ${GREEN}2)${NC}  Live log (tail -f)"
        echo -e "  ${GREEN}q)${NC}  Back to main menu\n"
        
        read -p "Choose option: " option
        echo
        
        case $option in
            1)
                view_recent_log
                ;;
            2)
                view_log_tail
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# View recent log
view_recent_log() {
    print_header
    echo -e "${BOLD}Recent Uploads Log${NC}\n"
    
    if [[ ! -f "$LOG" ]]; then
        echo -e "${YELLOW}Log file not found: $LOG${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Last 50 lines:${NC}\n"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    tail -50 "$LOG" | sed 's/^/  /'
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    
    wait_for_q
}

# View live log
view_log_tail() {
    print_header
    echo -e "${BOLD}Upload Log (Live)${NC}\n"
    
    if [[ ! -f "$LOG" ]]; then
        echo -e "${YELLOW}Log file not found: $LOG${NC}\n"
        wait_for_q
        return
    fi
    
    echo -e "${BLUE}Following log (Ctrl+C to exit)...${NC}\n"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    
    tail -f "$LOG"
}

# Upload from URL submenu
upload_from_url_submenu() {
    print_header
    echo -e "${BOLD}Upload from URL${NC}\n"

    if ! check_ghu; then
        wait_for_q
        return
    fi

    echo -e "${BLUE}Enter URL to download and upload:${NC}"
    echo -e "${YELLOW}Example: https://example.com/image.jpg${NC}"
    read -e url

    if [[ -z "$url" ]] || [[ "$url" == "q" ]]; then
        return 0
    fi

    # Basic URL validation
    if [[ ! "$url" =~ ^https?:// ]]; then
        echo -e "${RED}Error: Invalid URL. Must start with http:// or https://${NC}\n"
        wait_for_q
        return
    fi

    echo
    echo -e "${BOLD}Custom filename (optional):${NC}"
    echo -e "${DIM}Press Enter to use default filename from URL${NC}"
    read -e custom_name

    echo -e "\n${BLUE}Uploading from URL...${NC}\n"

    if [[ -n "$custom_name" ]] && [[ "$custom_name" != "q" ]]; then
        "$GHU" --name "$custom_name" "$url" 2>&1
    else
        "$GHU" "$url" 2>&1
    fi

    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
    else
        echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
    fi

    wait_for_q
}

# Quick Access Submenu
quick_access_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}Quick Access${NC}\n"
        show_inline_help "quick"

        echo -e "  ${GREEN}1)${NC}  Enhanced History Viewer ${DIM}(search, filter, retry)${NC}"
        echo -e "  ${GREEN}2)${NC}  Upload Queue Manager ${DIM}(batch operations)${NC}"
        echo -e "  ${GREEN}3)${NC}  Favorites ${DIM}(quick paths)${NC}"
        echo -e "  ${GREEN}4)${NC}  Repeat Last Upload"
        echo -e "  ${GREEN}5)${NC}  Common Paths ${DIM}(Downloads, Desktop, etc.)${NC}\n"
        show_nav_footer "submenu"

        read -p "Choose option: " option
        echo

        case $option in
            1)
                enhanced_history_viewer
                ;;
            2)
                upload_queue_manager
                ;;
            3)
                favorites_manager
                ;;
            4)
                repeat_last_upload
                ;;
            5)
                common_paths_menu
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Recent uploads viewer with search and actions
recent_uploads_viewer() {
    print_header
    echo -e "${BOLD}Recent Uploads${NC}\n"

    if [[ ! -f "$RECENT_FILE" ]]; then
        # Create empty recent file if doesn't exist
        echo "[]" > "$RECENT_FILE"
    fi

    # Read recent uploads (stored as JSON array)
    local recent_count=$(python3 -c "import json; print(len(json.load(open('$RECENT_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$recent_count" -eq 0 ]]; then
        echo -e "${YELLOW}No recent uploads found.${NC}\n"
        echo -e "${DIM}Uploads will appear here after you upload files.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BLUE}Found $recent_count recent upload(s)${NC}\n"

    # Display recent uploads with fzf if available
    if check_fzf; then
        local selected=$(python3 <<PYTHON | fzf --height 60% --border --header="Recent Uploads (Enter to copy, Ctrl-C to cancel)" --preview-window=down:3
import json
with open('$RECENT_FILE') as f:
    items = json.load(f)
    for i, item in enumerate(reversed(items[-50:]), 1):
        print(f"{i}. [{item.get('category', 'Unknown')}] {item.get('filename', 'Unknown')} -> {item.get('url', '')}")
PYTHON
)

        if [[ -n "$selected" ]]; then
            # Extract URL and copy to clipboard
            local url=$(echo "$selected" | grep -oE 'https?://[^ ]+' | head -1)
            if [[ -n "$url" ]]; then
                echo "$url" | pbcopy
                echo -e "${GREEN}✓ URL copied to clipboard!${NC}\n"
                echo -e "${BLUE}$url${NC}\n"
            fi
        fi
    else
        # Fallback: simple list
        python3 <<PYTHON
import json
with open('$RECENT_FILE') as f:
    items = json.load(f)
    for i, item in enumerate(reversed(items[-20:]), 1):
        print(f"  {i}. [{item.get('category', 'Unknown')}] {item.get('filename', 'Unknown')}")
        print(f"     {item.get('url', '')}")
        print()
PYTHON
    fi

    wait_for_q
}

# Favorites manager
favorites_manager() {
    while true; do
        print_header
        echo -e "${BOLD}Favorites${NC}\n"

        if [[ ! -f "$FAVORITES_FILE" ]]; then
            echo "[]" > "$FAVORITES_FILE"
        fi

        local fav_count=$(python3 -c "import json; print(len(json.load(open('$FAVORITES_FILE'))))" 2>/dev/null || echo "0")

        echo -e "  ${GREEN}1)${NC}  View favorites ($fav_count items)"
        echo -e "  ${GREEN}2)${NC}  Add path to favorites"
        echo -e "  ${GREEN}3)${NC}  Remove from favorites"
        echo -e "  ${GREEN}4)${NC}  Upload from favorite path"
        echo -e "  ${GREEN}q)${NC}  Back\n"

        read -p "Choose option: " option
        echo

        case $option in
            1)
                view_favorites
                ;;
            2)
                add_to_favorites
                ;;
            3)
                remove_from_favorites
                ;;
            4)
                upload_from_favorites
                ;;
            q)
                return 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# View favorites
view_favorites() {
    print_header
    echo -e "${BOLD}Your Favorites${NC}\n"

    local fav_count=$(python3 -c "import json; print(len(json.load(open('$FAVORITES_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$fav_count" -eq 0 ]]; then
        echo -e "${YELLOW}No favorites yet.${NC}\n"
        wait_for_q
        return
    fi

    python3 <<PYTHON
import json
with open('$FAVORITES_FILE') as f:
    items = json.load(f)
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item.get('name', 'Unknown')}")
        print(f"     ${DIM}{item.get('path', '')}${NC}")
        print()
PYTHON

    wait_for_q
}

# Add to favorites
add_to_favorites() {
    print_header
    echo -e "${BOLD}Add to Favorites${NC}\n"

    echo -e "${BLUE}Enter path to add:${NC}"
    read -e new_path

    if [[ -z "$new_path" ]] || [[ "$new_path" == "q" ]]; then
        return 0
    fi

    new_path="${new_path/#\~/$HOME}"

    if [[ ! -e "$new_path" ]]; then
        echo -e "${RED}Error: Path not found: $new_path${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BLUE}Enter a name for this favorite:${NC}"
    read -e fav_name

    if [[ -z "$fav_name" ]]; then
        fav_name=$(basename "$new_path")
    fi

    # Add to favorites
    python3 <<PYTHON
import json
import os

fav_file = '$FAVORITES_FILE'
new_item = {
    'name': '$fav_name',
    'path': '$new_path',
    'type': 'directory' if os.path.isdir('$new_path') else 'file'
}

if os.path.exists(fav_file):
    with open(fav_file) as f:
        items = json.load(f)
else:
    items = []

items.append(new_item)

with open(fav_file, 'w') as f:
    json.dump(items, f, indent=2)

print("✓ Added to favorites!")
PYTHON

    echo
    wait_for_q
}

# Remove from favorites
remove_from_favorites() {
    print_header
    echo -e "${BOLD}Remove from Favorites${NC}\n"

    local fav_count=$(python3 -c "import json; print(len(json.load(open('$FAVORITES_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$fav_count" -eq 0 ]]; then
        echo -e "${YELLOW}No favorites to remove.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BOLD}Your favorites:${NC}\n"
    python3 <<PYTHON
import json
with open('$FAVORITES_FILE') as f:
    items = json.load(f)
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item.get('name', 'Unknown')}")
PYTHON

    echo
    read -p "Enter number to remove (or 'q' to cancel): " choice

    if [[ "$choice" == "q" ]]; then
        return 0
    fi

    python3 <<PYTHON
import json

with open('$FAVORITES_FILE') as f:
    items = json.load(f)

try:
    idx = int('$choice') - 1
    if 0 <= idx < len(items):
        removed = items.pop(idx)
        with open('$FAVORITES_FILE', 'w') as f:
            json.dump(items, f, indent=2)
        print(f"✓ Removed: {removed.get('name', 'Unknown')}")
    else:
        print("✗ Invalid selection")
except:
    print("✗ Invalid input")
PYTHON

    echo
    wait_for_q
}

# Upload from favorites
upload_from_favorites() {
    print_header
    echo -e "${BOLD}Upload from Favorites${NC}\n"

    local fav_count=$(python3 -c "import json; print(len(json.load(open('$FAVORITES_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$fav_count" -eq 0 ]]; then
        echo -e "${YELLOW}No favorites yet.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BOLD}Select favorite:${NC}\n"

    # Get favorites
    local favorites=()
    while IFS= read -r line; do
        favorites+=("$line")
    done < <(python3 -c "import json; items = json.load(open('$FAVORITES_FILE')); print('\n'.join([item['path'] for item in items]))")

    # Display and select
    python3 <<PYTHON
import json
with open('$FAVORITES_FILE') as f:
    items = json.load(f)
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item.get('name', 'Unknown')}")
        print(f"     ${DIM}{item.get('path', '')}${NC}")
        print()
PYTHON

    read -p "Choose favorite to upload: " choice
    echo

    if [[ "$choice" == "q" ]]; then
        return 0
    fi

    local idx=$((choice - 1))
    if [[ $idx -ge 0 ]] && [[ $idx -lt ${#favorites[@]} ]]; then
        local fav_path="${favorites[$idx]}"

        if [[ -f "$fav_path" ]]; then
            upload_with_custom_naming "$fav_path"
        elif [[ -d "$fav_path" ]]; then
            upload_directory "$fav_path"
        else
            echo -e "${RED}Error: Path not found: $fav_path${NC}\n"
            wait_for_q
        fi
    else
        echo -e "${RED}Invalid selection${NC}\n"
        wait_for_q
    fi
}

# Repeat last upload
repeat_last_upload() {
    print_header
    echo -e "${BOLD}Repeat Last Upload${NC}\n"

    if [[ ! -f "$RECENT_FILE" ]]; then
        echo -e "${YELLOW}No recent uploads found.${NC}\n"
        wait_for_q
        return
    fi

    local last_upload=$(python3 <<PYTHON
import json
try:
    with open('$RECENT_FILE') as f:
        items = json.load(f)
        if items:
            last = items[-1]
            print(f"{last.get('filepath', '')}")
        else:
            print("")
except:
    print("")
PYTHON
)

    if [[ -z "$last_upload" ]]; then
        echo -e "${YELLOW}No recent uploads found.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BLUE}Last upload:${NC} $(basename "$last_upload")\n"

    if [[ ! -f "$last_upload" ]]; then
        echo -e "${RED}Error: File no longer exists: $last_upload${NC}\n"
        wait_for_q
        return
    fi

    if confirm "Re-upload this file?"; then
        echo -e "\n${BLUE}Uploading...${NC}\n"
        "$GHU" "$last_upload" 2>&1
        local exit_code=$?
        if [[ $exit_code -eq 0 ]]; then
            echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
        else
            echo -e "\n${RED}✗ Upload failed (exit code: $exit_code)${NC}\n"
        fi
    fi

    wait_for_q
}

# Common paths menu
common_paths_menu() {
    print_header
    echo -e "${BOLD}Common Paths${NC}\n"

    echo -e "${DIM}Quick access to commonly used directories${NC}\n"

    echo -e "  ${GREEN}1)${NC}  Home directory ($HOME)"
    echo -e "  ${GREEN}2)${NC}  Downloads ($HOME/Downloads)"
    echo -e "  ${GREEN}3)${NC}  Desktop ($HOME/Desktop)"
    echo -e "  ${GREEN}4)${NC}  Documents ($HOME/Documents)"
    echo -e "  ${GREEN}5)${NC}  Pictures ($HOME/Pictures)"
    if [[ -d "/Volumes/Eksternal/Audio" ]]; then
        echo -e "  ${GREEN}6)${NC}  Audio library (/Volumes/Eksternal/Audio)"
    fi
    echo -e "  ${GREEN}q)${NC}  Back\n"

    read -p "Choose path to browse: " option
    echo

    local target_path=""
    case $option in
        1) target_path="$HOME" ;;
        2) target_path="$HOME/Downloads" ;;
        3) target_path="$HOME/Desktop" ;;
        4) target_path="$HOME/Documents" ;;
        5) target_path="$HOME/Pictures" ;;
        6) target_path="/Volumes/Eksternal/Audio" ;;
        q) return 0 ;;
        *)
            echo -e "${RED}Invalid option${NC}\n"
            sleep 1
            return
            ;;
    esac

    if [[ -d "$target_path" ]]; then
        cd "$target_path"
        upload_folder
    else
        echo -e "${RED}Error: Directory not found: $target_path${NC}\n"
        wait_for_q
    fi
}

# Stats & Info Submenu
stats_info_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}Stats & Info${NC}\n"

        echo -e "  ${GREEN}1)${NC}  Upload statistics"
        echo -e "  ${GREEN}2)${NC}  Repository info"
        echo -e "  ${GREEN}3)${NC}  Configuration summary"
        echo -e "  ${GREEN}4)${NC}  Help & keyboard shortcuts"
        echo -e "  ${GREEN}q)${NC}  Back to main menu\n"

        read -p "Choose option: " option
        echo

        case $option in
            1)
                show_upload_stats
                ;;
            2)
                show_repo_info
                ;;
            3)
                show_config_summary
                ;;
            4)
                show_help
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Show upload statistics
show_upload_stats() {
    print_header
    echo -e "${BOLD}Upload Statistics${NC}\n"

    if [[ ! -f "$RECENT_FILE" ]]; then
        echo -e "${YELLOW}No upload history found.${NC}\n"
        wait_for_q
        return
    fi

    python3 <<PYTHON
import json
from collections import Counter
from datetime import datetime

try:
    with open('$RECENT_FILE') as f:
        items = json.load(f)

    if not items:
        print("No uploads recorded yet.\n")
    else:
        print(f"${CYAN}Total Uploads:${NC} {len(items)}")

        # Count by category
        categories = Counter(item.get('category', 'Unknown') for item in items)
        print(f"\n${BOLD}By Category:${NC}")
        for cat, count in categories.most_common():
            print(f"  {cat}: {count}")

        # Recent uploads
        recent = items[-10:]
        print(f"\n${BOLD}Recent 10 Uploads:${NC}")
        for i, item in enumerate(reversed(recent), 1):
            fname = item.get('filename', 'Unknown')
            cat = item.get('category', 'Unknown')
            print(f"  {i}. [{cat}] {fname}")

        print()
except Exception as e:
    print(f"Error reading stats: {e}\n")
PYTHON

    wait_for_q
}

# Show repository info
show_repo_info() {
    print_header
    echo -e "${BOLD}Repository Information${NC}\n"

    if [[ ! -f "$CONFIG" ]]; then
        echo -e "${RED}Config file not found: $CONFIG${NC}\n"
        wait_for_q
        return
    fi

    local owner=$(get_config_value "owner")
    local repo=$(get_config_value "repo")
    local branch=$(get_config_value "branch")

    echo -e "${CYAN}GitHub Repository:${NC}"
    echo -e "  Owner: ${BOLD}$owner${NC}"
    echo -e "  Repo: ${BOLD}$repo${NC}"
    echo -e "  Branch: ${BOLD}$branch${NC}"
    echo -e "  URL: ${BLUE}https://github.com/$owner/$repo${NC}\n"

    # Check if gh CLI is available for more info
    if command -v gh &> /dev/null; then
        echo -e "${CYAN}Fetching repository stats...${NC}\n"
        gh repo view "$owner/$repo" --json name,description,diskUsage,stargazerCount 2>/dev/null | \
            python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(f\"  Name: {data.get('name', 'N/A')}\")
    print(f\"  Description: {data.get('description', 'N/A')}\")
    print(f\"  Size: {data.get('diskUsage', 0)} KB\")
    print(f\"  Stars: {data.get('stargazerCount', 0)}\")
    print()
except:
    pass
"
    fi

    wait_for_q
}

# Show configuration summary
show_config_summary() {
    print_header
    echo -e "${BOLD}Configuration Summary${NC}\n"

    if [[ ! -f "$CONFIG" ]]; then
        echo -e "${RED}Config file not found: $CONFIG${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${CYAN}Current Settings:${NC}\n"

    python3 <<PYTHON
import json
try:
    with open('$CONFIG') as f:
        config = json.load(f)

    print(f"  Output mode: {config.get('output_mode', 'markdown')}")
    print(f"  Organize by artist: {config.get('organize_by_artist', False)}")
    print(f"  Use image subfolders: {config.get('use_image_subfolders', True)}")
    print(f"  Path-based naming: {config.get('use_path_for_generic_names', True)}")
    print(f"  Audio path naming: {config.get('use_path_for_audio_names', True)}")
    print(f"  Audio HTML tags: {config.get('also_audio_html', True)}")
    print(f"  Max file size (Contents API): {config.get('contents_max_mb', 95)} MB")
    print()

    print(f"${CYAN}Paths:${NC}")
    print(f"  Config: $CONFIG")
    print(f"  Log: $LOG")
    print(f"  Favorites: $FAVORITES_FILE")
    print(f"  Recent: $RECENT_FILE")
    print()
except Exception as e:
    print(f"Error reading config: {e}\n")
PYTHON

    wait_for_q
}

# Show help and keyboard shortcuts
show_help() {
    print_header
    echo -e "${BOLD}Help & Keyboard Shortcuts${NC}\n"

    echo -e "${CYAN}Navigation:${NC}"
    echo -e "  ${BOLD}q${NC} or ${BOLD}0${NC}    - Go back / Exit submenu"
    echo -e "  ${BOLD}1-9${NC}      - Select menu option"
    echo -e "  ${BOLD}Ctrl+C${NC}   - Exit program (from anywhere)\n"

    echo -e "${CYAN}File Selection:${NC}"
    echo -e "  ${BOLD}Tab${NC}      - Autocomplete file paths"
    echo -e "  ${BOLD}~${NC}        - Shortcut for home directory"
    echo -e "  ${BOLD}./file${NC}   - Relative path from current directory\n"

    echo -e "${CYAN}fzf Shortcuts (when available):${NC}"
    echo -e "  ${BOLD}Ctrl+/${NC}   - Toggle preview window"
    echo -e "  ${BOLD}/text${NC}    - Search/filter"
    echo -e "  ${BOLD}Tab${NC}      - Select multiple (multi-select mode)"
    echo -e "  ${BOLD}Enter${NC}    - Confirm selection\n"

    echo -e "${CYAN}Quick Tips:${NC}"
    echo -e "  • Use ${BOLD}Quick Access${NC} (option 4) for recent uploads & favorites"
    echo -e "  • Add frequently used paths to ${BOLD}Favorites${NC} for quick access"
    echo -e "  • Check ${BOLD}Stats${NC} to see upload history and repository info"
    echo -e "  • URLs are automatically copied to clipboard after upload\n"

    echo -e "${CYAN}Upload Options:${NC}"
    echo -e "  • ${BOLD}Default naming${NC} - Extracts artist/album from path"
    echo -e "  • ${BOLD}Custom naming${NC} - Specify your own filename"
    echo -e "  • ${BOLD}URL upload${NC} - Download from URL and upload to GitHub\n"

    echo -e "${CYAN}Configuration:${NC}"
    echo -e "  • Config file: ${DIM}$CONFIG${NC}"
    echo -e "  • Edit output mode from ${BOLD}Configure Options${NC} menu"
    echo -e "  • See all settings in ${BOLD}Stats & Info > Configuration${NC}\n"

    wait_for_q
}

# Advanced Tools Submenu
advanced_tools_submenu() {
    while true; do
        print_header
        echo -e "${BOLD}Advanced Tools${NC}\n"
        echo -e "${DIM}Power features for advanced workflows${NC}\n"

        echo -e "  ${GREEN}1)${NC}  Batch URL upload (multiple URLs)"
        echo -e "  ${GREEN}2)${NC}  Duplicate checker (scan before upload)"
        echo -e "  ${GREEN}3)${NC}  Upload templates/presets"
        echo -e "  ${GREEN}4)${NC}  Clipboard monitor (auto-upload)"
        echo -e "  ${GREEN}5)${NC}  File preview before upload"
        echo -e "  ${GREEN}6)${NC}  Search uploaded files"
        echo -e "  ${GREEN}7)${NC}  Export upload history"
        echo -e "  ${GREEN}8)${NC}  Bulk file operations"
        echo -e "  ${GREEN}q)${NC}  Back to main menu\n"

        read -p "Choose option: " option
        echo

        case $option in
            1)
                batch_url_upload
                ;;
            2)
                duplicate_checker
                ;;
            3)
                upload_templates_menu
                ;;
            4)
                clipboard_monitor
                ;;
            5)
                preview_before_upload
                ;;
            6)
                search_uploaded_files
                ;;
            7)
                export_upload_history
                ;;
            8)
                bulk_file_operations
                ;;
            b|0)
                return 0
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Batch URL Upload
batch_url_upload() {
    print_header
    echo -e "${BOLD}Batch URL Upload${NC}\n"
    echo -e "${DIM}Upload multiple URLs at once${NC}\n"

    if ! check_ghu; then
        wait_for_q
        return
    fi

    echo -e "${BLUE}Paste URLs (one per line, empty line to finish):${NC}\n"
    echo -e "${YELLOW}Example:${NC}"
    echo -e "${DIM}  https://example.com/image1.jpg${NC}"
    echo -e "${DIM}  https://example.com/image2.jpg${NC}"
    echo -e "${DIM}  [press Enter on empty line]${NC}\n"

    local urls=()
    while true; do
        read -e url
        if [[ -z "$url" ]]; then
            break
        fi
        if [[ "$url" == "q" ]]; then
            return 0
        fi

        # Validate URL
        if [[ "$url" =~ ^https?:// ]]; then
            urls+=("$url")
            echo -e "${GREEN}✓ Added: $url${NC}"
        else
            echo -e "${RED}✗ Invalid URL (skipped): $url${NC}"
        fi
    done

    if [[ ${#urls[@]} -eq 0 ]]; then
        echo -e "\n${YELLOW}No valid URLs provided.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "\n${BLUE}Found ${#urls[@]} URLs to upload${NC}\n"

    # Ask for batch custom naming
    echo -e "${BOLD}Naming options:${NC}"
    echo -e "  ${GREEN}1)${NC}  Use default names from URLs"
    echo -e "  ${GREEN}2)${NC}  Use common prefix (e.g., 'Album-' for Album-1.jpg, Album-2.jpg...)"
    echo -e "  ${GREEN}3)${NC}  Provide individual names\n"

    read -p "Choose option: " naming_option
    echo

    case $naming_option in
        1)
            # Upload all with default names
            echo -e "${BLUE}Uploading ${#urls[@]} files...${NC}\n"
            "$GHU" "${urls[@]}" 2>&1
            ;;
        2)
            read -e -p "Enter common prefix (e.g., 'Artist - Album - '): " prefix
            if [[ -n "$prefix" ]]; then
                # Generate custom names with prefix and numbering
                local names=()
                for i in "${!urls[@]}"; do
                    local num=$((i + 1))
                    # Get extension from URL
                    local ext="${urls[i]##*.}"
                    [[ "$ext" =~ [?#] ]] && ext="jpg"  # Default if URL has params
                    names+=("--name" "${prefix}${num}.${ext}")
                done
                echo -e "\n${BLUE}Uploading with custom names...${NC}\n"
                "$GHU" "${names[@]}" "${urls[@]}" 2>&1
            fi
            ;;
        3)
            echo -e "${YELLOW}Enter custom names for each URL:${NC}\n"
            local custom_names=()
            for i in "${!urls[@]}"; do
                echo -e "${BLUE}URL $((i+1)): ${urls[i]}${NC}"
                read -e -p "Name (or press Enter for default): " custom_name
                if [[ -n "$custom_name" ]]; then
                    custom_names+=("$custom_name")
                else
                    custom_names+=("")
                fi
            done

            # Build ghu command with custom names
            local ghu_args=()
            for i in "${!urls[@]}"; do
                if [[ -n "${custom_names[i]}" ]]; then
                    ghu_args+=("--name" "${custom_names[i]}" "${urls[i]}")
                else
                    ghu_args+=("${urls[i]}")
                fi
            done

            echo -e "\n${BLUE}Uploading...${NC}\n"
            "$GHU" "${ghu_args[@]}" 2>&1
            ;;
    esac

    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo -e "\n${GREEN}✓ Batch upload complete!${NC}\n"
    else
        echo -e "\n${RED}✗ Batch upload had errors (exit code: $exit_code)${NC}\n"
    fi

    wait_for_q
}

# Duplicate Checker
duplicate_checker() {
    print_header
    echo -e "${BOLD}Duplicate Checker${NC}\n"
    echo -e "${DIM}Check if file already exists before upload${NC}\n"

    if ! check_ghu; then
        wait_for_q
        return
    fi

    if [[ ! -f "$RECENT_FILE" ]]; then
        echo -e "${YELLOW}No upload history found. Cannot check for duplicates.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BLUE}Enter file path to check:${NC}"
    read -e file_path

    if [[ -z "$file_path" ]] || [[ "$file_path" == "q" ]]; then
        return 0
    fi

    file_path="${file_path/#\~/$HOME}"

    if [[ ! -f "$file_path" ]]; then
        echo -e "${RED}Error: File not found: $file_path${NC}\n"
        wait_for_q
        return
    fi

    local filename=$(basename "$file_path")
    echo -e "\n${BLUE}Searching for: $filename${NC}\n"

    # Check in recent uploads
    local found=$(python3 <<PYTHON
import json
import os

search_name = "$filename"
search_path = "$file_path"

try:
    with open('$RECENT_FILE') as f:
        items = json.load(f)

    matches = []
    for item in items:
        if item.get('filename', '') == search_name:
            matches.append(item)
        elif os.path.basename(item.get('filepath', '')) == search_name:
            matches.append(item)

    if matches:
        print(f"${YELLOW}Found {len(matches)} potential duplicate(s):${NC}\n")
        for i, match in enumerate(matches, 1):
            print(f"  {i}. {match.get('filename', 'Unknown')}")
            print(f"     Uploaded: {match.get('timestamp', 'Unknown')}")
            print(f"     URL: {match.get('url', 'Unknown')}")
            print()
        print("true")
    else:
        print("${GREEN}No duplicates found. Safe to upload!${NC}\n")
        print("false")
except Exception as e:
    print(f"Error: {e}\n")
    print("false")
PYTHON
)

    if [[ "$found" == *"true"* ]]; then
        echo -e "${BOLD}Options:${NC}"
        echo -e "  ${GREEN}1)${NC}  Upload anyway (will create duplicate)"
        echo -e "  ${GREEN}2)${NC}  Copy existing URL to clipboard"
        echo -e "  ${GREEN}3)${NC}  Cancel\n"

        read -p "Choose option: " dup_option

        case $dup_option in
            1)
                echo -e "\n${BLUE}Uploading...${NC}\n"
                "$GHU" "$file_path" 2>&1
                ;;
            2)
                # Copy first match URL to clipboard
                local url=$(python3 -c "import json; items = json.load(open('$RECENT_FILE')); matches = [i for i in items if i.get('filename') == '$filename']; print(matches[-1]['url'] if matches else '')")
                if [[ -n "$url" ]]; then
                    echo "$url" | pbcopy
                    echo -e "${GREEN}✓ URL copied to clipboard!${NC}"
                    echo -e "${BLUE}$url${NC}\n"
                fi
                ;;
            3)
                echo -e "${YELLOW}Cancelled.${NC}\n"
                ;;
        esac
    fi

    wait_for_q
}

# Upload Templates Menu
upload_templates_menu() {
    while true; do
        print_header
        echo -e "${BOLD}Upload Templates${NC}\n"
        echo -e "${DIM}Save and reuse upload configurations${NC}\n"

        TEMPLATES_FILE="$DATA_DIR/templates.json"
        [[ ! -f "$TEMPLATES_FILE" ]] && echo "[]" > "$TEMPLATES_FILE"

        local template_count=$(python3 -c "import json; print(len(json.load(open('$TEMPLATES_FILE'))))" 2>/dev/null || echo "0")

        echo -e "  ${GREEN}1)${NC}  Use template ($template_count saved)"
        echo -e "  ${GREEN}2)${NC}  Create new template"
        echo -e "  ${GREEN}3)${NC}  View templates"
        echo -e "  ${GREEN}4)${NC}  Delete template"
        echo -e "  ${GREEN}q)${NC}  Back\n"

        read -p "Choose option: " option
        echo

        case $option in
            1)
                use_upload_template
                ;;
            2)
                create_upload_template
                ;;
            3)
                view_upload_templates
                ;;
            4)
                delete_upload_template
                ;;
            q)
                return 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Create Upload Template
create_upload_template() {
    print_header
    echo -e "${BOLD}Create Upload Template${NC}\n"

    echo -e "${BLUE}Template name:${NC}"
    read -e template_name

    if [[ -z "$template_name" ]] || [[ "$template_name" == "q" ]]; then
        return 0
    fi

    echo -e "${BLUE}Description (optional):${NC}"
    read -e description

    echo -e "\n${BOLD}Template Configuration:${NC}\n"

    # Naming pattern
    echo -e "${BLUE}Naming pattern (optional):${NC}"
    echo -e "${DIM}Examples: 'Artist - ', 'Project-', 'IMG_'${NC}"
    read -e naming_pattern

    # Category preference
    echo -e "\n${BLUE}Default category (optional):${NC}"
    echo -e "${DIM}Leave empty for auto-detect${NC}"
    read -e default_category

    # Custom output mode
    echo -e "\n${BLUE}Output mode (markdown/url/both, or empty for default):${NC}"
    read -e output_mode

    # Save template
    python3 <<PYTHON
import json
import os

templates_file = '$TEMPLATES_FILE'
new_template = {
    'name': '$template_name',
    'description': '$description',
    'naming_pattern': '$naming_pattern',
    'default_category': '$default_category',
    'output_mode': '$output_mode',
    'created': '$(date +%Y-%m-%d)'
}

if os.path.exists(templates_file):
    with open(templates_file) as f:
        templates = json.load(f)
else:
    templates = []

templates.append(new_template)

with open(templates_file, 'w') as f:
    json.dump(templates, f, indent=2)

print("${GREEN}✓ Template created successfully!${NC}\n")
PYTHON

    wait_for_q
}

# Use Upload Template
use_upload_template() {
    print_header
    echo -e "${BOLD}Use Upload Template${NC}\n"

    local template_count=$(python3 -c "import json; print(len(json.load(open('$TEMPLATES_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$template_count" -eq 0 ]]; then
        echo -e "${YELLOW}No templates saved yet.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BOLD}Available templates:${NC}\n"
    python3 <<PYTHON
import json
with open('$TEMPLATES_FILE') as f:
    templates = json.load(f)
    for i, tmpl in enumerate(templates, 1):
        print(f"  {i}. {tmpl.get('name', 'Unknown')}")
        if tmpl.get('description'):
            print(f"     ${DIM}{tmpl.get('description')}${NC}")
        print()
PYTHON

    read -p "Select template number: " choice
    echo

    if [[ "$choice" == "q" ]]; then
        return 0
    fi

    # Get template config
    local template_config=$(python3 -c "import json; templates = json.load(open('$TEMPLATES_FILE')); idx = int('$choice') - 1; print(templates[idx] if 0 <= idx < len(templates) else '')" 2>/dev/null)

    if [[ -z "$template_config" ]]; then
        echo -e "${RED}Invalid template selection${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BLUE}Select file(s) to upload with this template:${NC}\n"
    # Continue with file selection and upload using template settings
    # (Implementation would apply template naming patterns, etc.)

    echo -e "${YELLOW}Template application coming soon in next update!${NC}\n"
    wait_for_q
}

# View Upload Templates
view_upload_templates() {
    print_header
    echo -e "${BOLD}Saved Templates${NC}\n"

    local template_count=$(python3 -c "import json; print(len(json.load(open('$TEMPLATES_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$template_count" -eq 0 ]]; then
        echo -e "${YELLOW}No templates saved yet.${NC}\n"
        wait_for_q
        return
    fi

    python3 <<PYTHON
import json
with open('$TEMPLATES_FILE') as f:
    templates = json.load(f)
    for i, tmpl in enumerate(templates, 1):
        print(f"${BOLD}{i}. {tmpl.get('name', 'Unknown')}${NC}")
        print(f"   Description: {tmpl.get('description', 'None')}")
        print(f"   Naming: {tmpl.get('naming_pattern', 'Auto') or 'Auto'}")
        print(f"   Category: {tmpl.get('default_category', 'Auto') or 'Auto'}")
        print(f"   Output: {tmpl.get('output_mode', 'Default') or 'Default'}")
        print(f"   Created: {tmpl.get('created', 'Unknown')}")
        print()
PYTHON

    wait_for_q
}

# Delete Upload Template
delete_upload_template() {
    print_header
    echo -e "${BOLD}Delete Template${NC}\n"

    local template_count=$(python3 -c "import json; print(len(json.load(open('$TEMPLATES_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$template_count" -eq 0 ]]; then
        echo -e "${YELLOW}No templates to delete.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BOLD}Saved templates:${NC}\n"
    python3 <<PYTHON
import json
with open('$TEMPLATES_FILE') as f:
    templates = json.load(f)
    for i, tmpl in enumerate(templates, 1):
        print(f"  {i}. {tmpl.get('name', 'Unknown')}")
PYTHON

    echo
    read -p "Enter number to delete (or 'q' to cancel): " choice

    if [[ "$choice" == "q" ]]; then
        return 0
    fi

    python3 <<PYTHON
import json

with open('$TEMPLATES_FILE') as f:
    templates = json.load(f)

try:
    idx = int('$choice') - 1
    if 0 <= idx < len(templates):
        removed = templates.pop(idx)
        with open('$TEMPLATES_FILE', 'w') as f:
            json.dump(templates, f, indent=2)
        print(f"${GREEN}✓ Deleted: {removed.get('name', 'Unknown')}${NC}")
    else:
        print("${RED}✗ Invalid selection${NC}")
except:
    print("${RED}✗ Invalid input${NC}")
PYTHON

    echo
    wait_for_q
}

# Clipboard Monitor
clipboard_monitor() {
    print_header
    echo -e "${BOLD}Clipboard Monitor${NC}\n"
    echo -e "${DIM}Automatically upload files/URLs copied to clipboard${NC}\n"

    if ! check_ghu; then
        wait_for_q
        return
    fi

    echo -e "${YELLOW}⚠️  This will monitor your clipboard and auto-upload:${NC}"
    echo -e "  • File paths copied to clipboard"
    echo -e "  • Image URLs (http/https)"
    echo -e "\n${BLUE}Press Ctrl+C to stop monitoring${NC}\n"

    if ! confirm "Start clipboard monitor?"; then
        return 0
    fi

    echo -e "\n${GREEN}Clipboard monitor started...${NC}\n"
    echo -e "${DIM}Copy a file path or image URL to auto-upload${NC}\n"

    local last_clipboard=""
    while true; do
        sleep 1
        local current_clipboard=$(pbpaste 2>/dev/null || echo "")

        # Skip if clipboard unchanged
        [[ "$current_clipboard" == "$last_clipboard" ]] && continue
        last_clipboard="$current_clipboard"

        # Check if it's a file path
        if [[ -f "$current_clipboard" ]]; then
            echo -e "${CYAN}📋 Detected file: $(basename "$current_clipboard")${NC}"
            if confirm "Upload this file?"; then
                echo
                "$GHU" "$current_clipboard" 2>&1
                echo
            fi
        # Check if it's a URL
        elif [[ "$current_clipboard" =~ ^https?://.*\.(jpg|jpeg|png|gif|webp|svg|mp3|mp4|pdf)$ ]]; then
            echo -e "${CYAN}📋 Detected URL: $current_clipboard${NC}"
            if confirm "Download and upload?"; then
                echo
                "$GHU" "$current_clipboard" 2>&1
                echo
            fi
        fi
    done
}

# File Preview Before Upload
preview_before_upload() {
    print_header
    echo -e "${BOLD}File Preview${NC}\n"
    echo -e "${DIM}Preview file details before uploading${NC}\n"

    echo -e "${BLUE}Enter file path:${NC}"
    read -e file_path

    if [[ -z "$file_path" ]] || [[ "$file_path" == "q" ]]; then
        return 0
    fi

    file_path="${file_path/#\~/$HOME}"

    if [[ ! -f "$file_path" ]]; then
        echo -e "${RED}Error: File not found: $file_path${NC}\n"
        wait_for_q
        return
    fi

    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

    # File info
    echo -e "${BOLD}File Information:${NC}"
    echo -e "  Name: $(basename "$file_path")"
    echo -e "  Path: $file_path"
    echo -e "  Size: $(du -h "$file_path" | cut -f1)"
    echo -e "  Type: $(file -b "$file_path" 2>/dev/null || echo "Unknown")"
    echo -e "  Modified: $(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$file_path" 2>/dev/null || date -r "$file_path" 2>/dev/null || echo "Unknown")"

    # Category detection
    local category=$(python3 "$PYTHON_SCRIPT" --help 2>/dev/null | grep -q "category" && echo "Audio" || echo "Unknown")
    echo -e "  Category: $category (auto-detected)\n"

    # Show image preview for images
    local ext="${file_path##*.}"
    if [[ "$ext" =~ ^(jpg|jpeg|png|gif|webp)$ ]]; then
        if command -v imgcat &> /dev/null; then
            echo -e "${BLUE}Image Preview:${NC}\n"
            imgcat "$file_path" 2>/dev/null || echo -e "${YELLOW}  (Preview not available)${NC}\n"
        fi
    fi

    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

    if confirm "Upload this file?"; then
        echo -e "\n${BLUE}Uploading...${NC}\n"
        "$GHU" "$file_path" 2>&1
        echo -e "\n${GREEN}✓ Upload complete!${NC}\n"
    fi

    wait_for_q
}

# Search Uploaded Files
search_uploaded_files() {
    print_header
    echo -e "${BOLD}Search Uploaded Files${NC}\n"

    if [[ ! -f "$RECENT_FILE" ]]; then
        echo -e "${YELLOW}No upload history found.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BLUE}Search by:${NC}"
    echo -e "  ${GREEN}1)${NC}  Filename"
    echo -e "  ${GREEN}2)${NC}  Category"
    echo -e "  ${GREEN}3)${NC}  Date range"
    echo -e "  ${GREEN}q)${NC}  Back\n"

    read -p "Choose option: " search_type
    echo

    case $search_type in
        1)
            read -e -p "Enter filename to search: " search_term
            if [[ -n "$search_term" ]]; then
                python3 <<PYTHON
import json
with open('$RECENT_FILE') as f:
    items = json.load(f)
    matches = [i for i in items if '$search_term'.lower() in i.get('filename', '').lower()]

    if matches:
        print(f"${GREEN}Found {len(matches)} match(es):${NC}\n")
        for i, item in enumerate(matches, 1):
            print(f"  {i}. {item.get('filename', 'Unknown')}")
            print(f"     Category: {item.get('category', 'Unknown')}")
            print(f"     Uploaded: {item.get('timestamp', 'Unknown')}")
            print(f"     URL: {item.get('url', '')}")
            print()
    else:
        print("${YELLOW}No matches found.${NC}\n")
PYTHON
            fi
            ;;
        2)
            echo -e "${BLUE}Select category:${NC}"
            echo -e "  1) Audio"
            echo -e "  2) Images"
            echo -e "  3) Video"
            echo -e "  4) Scripts"
            echo -e "  5) Documents"
            echo -e "  6) Other\n"

            read -p "Choose category: " cat_choice

            local categories=("" "Audio" "Images" "Video" "Scripts" "Documents" "Other")
            local selected_cat="${categories[$cat_choice]:-}"

            if [[ -n "$selected_cat" ]]; then
                python3 <<PYTHON
import json
with open('$RECENT_FILE') as f:
    items = json.load(f)
    matches = [i for i in items if i.get('category') == '$selected_cat']

    if matches:
        print(f"${GREEN}Found {len(matches)} file(s) in category '$selected_cat':${NC}\n")
        for i, item in enumerate(matches[-20:], 1):  # Show last 20
            print(f"  {i}. {item.get('filename', 'Unknown')}")
            print(f"     {item.get('url', '')}")
            print()
    else:
        print("${YELLOW}No files found in this category.${NC}\n")
PYTHON
            fi
            ;;
        3)
            read -e -p "Start date (YYYY-MM-DD): " start_date
            read -e -p "End date (YYYY-MM-DD): " end_date

            python3 <<PYTHON
import json
from datetime import datetime

with open('$RECENT_FILE') as f:
    items = json.load(f)

try:
    start = datetime.fromisoformat('$start_date')
    end = datetime.fromisoformat('$end_date')

    matches = []
    for item in items:
        try:
            item_date = datetime.fromisoformat(item.get('timestamp', '')[:10])
            if start <= item_date <= end:
                matches.append(item)
        except:
            pass

    if matches:
        print(f"${GREEN}Found {len(matches)} file(s) in date range:${NC}\n")
        for i, item in enumerate(matches, 1):
            print(f"  {i}. {item.get('filename', 'Unknown')}")
            print(f"     Date: {item.get('timestamp', 'Unknown')[:10]}")
            print(f"     {item.get('url', '')}")
            print()
    else:
        print("${YELLOW}No files found in this date range.${NC}\n")
except Exception as e:
    print(f"${RED}Error: {e}${NC}\n")
PYTHON
            ;;
        q)
            return 0
            ;;
    esac

    wait_for_q
}

# Export Upload History
export_upload_history() {
    print_header
    echo -e "${BOLD}Export Upload History${NC}\n"

    if [[ ! -f "$RECENT_FILE" ]]; then
        echo -e "${YELLOW}No upload history found.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "${BLUE}Export format:${NC}"
    echo -e "  ${GREEN}1)${NC}  CSV (spreadsheet-friendly)"
    echo -e "  ${GREEN}2)${NC}  JSON (full data)"
    echo -e "  ${GREEN}3)${NC}  Markdown table"
    echo -e "  ${GREEN}q)${NC}  Back\n"

    read -p "Choose format: " format_choice
    echo

    local export_file=""
    case $format_choice in
        1)
            export_file="$HOME/Downloads/gupload-history-$(date +%Y%m%d-%H%M%S).csv"
            python3 <<PYTHON
import json
import csv

with open('$RECENT_FILE') as f:
    items = json.load(f)

with open('$export_file', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Filename', 'Category', 'URL', 'Timestamp', 'Original Path'])

    for item in items:
        writer.writerow([
            item.get('filename', ''),
            item.get('category', ''),
            item.get('url', ''),
            item.get('timestamp', ''),
            item.get('filepath', '')
        ])

print(f"${GREEN}✓ Exported to: $export_file${NC}\n")
PYTHON
            ;;
        2)
            export_file="$HOME/Downloads/gupload-history-$(date +%Y%m%d-%H%M%S).json"
            cp "$RECENT_FILE" "$export_file"
            echo -e "${GREEN}✓ Exported to: $export_file${NC}\n"
            ;;
        3)
            export_file="$HOME/Downloads/gupload-history-$(date +%Y%m%d-%H%M%S).md"
            python3 <<PYTHON
import json

with open('$RECENT_FILE') as f:
    items = json.load(f)

with open('$export_file', 'w') as f:
    f.write("# Gupload Upload History\n\n")
    f.write(f"Generated: $(date)\n\n")
    f.write("| # | Filename | Category | Date | URL |\n")
    f.write("|---|----------|----------|------|-----|\n")

    for i, item in enumerate(items, 1):
        filename = item.get('filename', 'Unknown')
        category = item.get('category', 'Unknown')
        timestamp = item.get('timestamp', 'Unknown')[:10]
        url = item.get('url', '')
        f.write(f"| {i} | {filename} | {category} | {timestamp} | {url} |\n")

print(f"${GREEN}✓ Exported to: $export_file${NC}\n")
PYTHON
            ;;
        q)
            return 0
            ;;
    esac

    if [[ -f "$export_file" ]]; then
        echo -e "${BLUE}File saved to: $export_file${NC}\n"

        if confirm "Open exported file?"; then
            open "$export_file" 2>/dev/null || echo -e "${YELLOW}Could not open file${NC}\n"
        fi
    fi

    wait_for_q
}

# Bulk File Operations
bulk_file_operations() {
    print_header
    echo -e "${BOLD}Bulk File Operations${NC}\n"
    echo -e "${DIM}Manage multiple uploaded files${NC}\n"

    if [[ ! -f "$RECENT_FILE" ]]; then
        echo -e "${YELLOW}No upload history found.${NC}\n"
        wait_for_q
        return
    fi

    echo -e "  ${GREEN}1)${NC}  Copy multiple URLs to clipboard"
    echo -e "  ${GREEN}2)${NC}  Generate markdown gallery"
    echo -e "  ${GREEN}3)${NC}  Generate HTML gallery"
    echo -e "  ${GREEN}4)${NC}  Clear upload history"
    echo -e "  ${GREEN}q)${NC}  Back\n"

    read -p "Choose option: " option
    echo

    case $option in
        1)
            read -e -p "How many recent uploads? (default: 10): " count
            count=${count:-10}

            local urls=$(python3 -c "import json; items = json.load(open('$RECENT_FILE')); print('\n'.join([i['url'] for i in items[-$count:]]))")

            echo "$urls" | pbcopy
            echo -e "${GREEN}✓ Copied $count URLs to clipboard!${NC}\n"
            ;;
        2)
            read -e -p "Category to include (or 'all'): " category
            local output_file="$HOME/Downloads/gallery-$(date +%Y%m%d-%H%M%S).md"

            python3 <<PYTHON
import json

with open('$RECENT_FILE') as f:
    items = json.load(f)

if '$category' != 'all':
    items = [i for i in items if i.get('category') == '$category']

with open('$output_file', 'w') as f:
    f.write("# Upload Gallery\n\n")

    for item in items:
        filename = item.get('filename', 'Unknown')
        url = item.get('url', '')
        category = item.get('category', '')

        if category == 'Images':
            f.write(f"![{filename}]({url})\n\n")
        elif category == 'Audio':
            f.write(f"### {filename}\n")
            f.write(f'<audio controls src="{url}"></audio>\n\n')
        else:
            f.write(f"- [{filename}]({url})\n")

print(f"${GREEN}✓ Gallery created: $output_file${NC}\n")
PYTHON

            if [[ -f "$output_file" ]]; then
                echo -e "${BLUE}File: $output_file${NC}\n"
                if confirm "Open gallery?"; then
                    open "$output_file" 2>/dev/null
                fi
            fi
            ;;
        3)
            echo -e "${YELLOW}HTML gallery coming in next update!${NC}\n"
            ;;
        4)
            echo -e "${RED}⚠️  This will permanently delete your upload history!${NC}\n"

            if confirm "Are you sure?"; then
                # Backup first
                local backup_file="$DATA_DIR/recent-backup-$(date +%Y%m%d-%H%M%S).json"
                cp "$RECENT_FILE" "$backup_file"

                # Clear history
                echo "[]" > "$RECENT_FILE"

                echo -e "${GREEN}✓ History cleared!${NC}"
                echo -e "${BLUE}Backup saved to: $backup_file${NC}\n"
            else
                echo -e "${YELLOW}Cancelled.${NC}\n"
            fi
            ;;
        q)
            return 0
            ;;
    esac

    wait_for_q
}

# ============================================================================
# NEW FEATURES: Help, Keyboard Shortcuts, Enhanced History, Queue System
# ============================================================================

# Show inline help for any menu
show_inline_help() {
    local menu_name="$1"
    echo -e "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    case "$menu_name" in
        "main")
            echo -e "${DIM}💡 Quick Tips: Use number keys to select | 'q' to go back | Ctrl+C to exit${NC}"
            echo -e "${DIM}📖 For full help, go to: Stats & Info → Help & Keyboard Shortcuts${NC}"
            ;;
        "upload")
            echo -e "${DIM}💡 Tip: Use fzf search (option 1) for fastest file selection${NC}"
            echo -e "${DIM}📝 Custom naming available in option 2 | Drag files to Finder for option 4${NC}"
            ;;
        "quick")
            echo -e "${DIM}💡 Recent uploads shows last 50 | Favorites for quick path access${NC}"
            echo -e "${DIM}⚡ Repeat last upload if you need to re-upload same file${NC}"
            ;;
        "advanced")
            echo -e "${DIM}💡 Batch URL: paste multiple URLs | Templates: save common configs${NC}"
            echo -e "${DIM}🔍 Duplicate checker prevents re-uploads | Preview shows file details${NC}"
            ;;
        "stats")
            echo -e "${DIM}💡 Upload stats show totals by category | Repo info needs 'gh' CLI${NC}"
            echo -e "${DIM}📊 Export history for backup | View config for current settings${NC}"
            ;;
    esac
    echo -e "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# Show navigation footer (hub library style - bottom of page)
show_nav_footer() {
    local context="$1"

    case "$context" in
        "main")
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            echo -e "  ${GREEN}1-9${NC}  Select option  │  ${GREEN}0${NC}  Exit  │  ${GREEN}Ctrl+C${NC}  Quick exit"
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            ;;
        "submenu")
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            echo -e "  ${GREEN}1-9${NC}  Select option  │  ${GREEN}b/0${NC}  ← Back  │  ${GREEN}q${NC}  Quit"
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            ;;
        "history-pagination")
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            echo -e "  ${GREEN}n${NC}  Next page  │  ${GREEN}p${NC}  Previous  │  ${GREEN}c${NC}  Copy URL  │  ${GREEN}b${NC}  ← Back  │  ${GREEN}q${NC}  Quit"
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            ;;
        "fzf-help")
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            echo -e "  ${GREEN}Ctrl+/${NC}  Preview  │  ${GREEN}/text${NC}  Search  │  ${GREEN}↑↓${NC}  Navigate  │  ${GREEN}Enter${NC}  Select  │  ${GREEN}Esc${NC}  Cancel"
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            ;;
        "queue")
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            echo -e "  ${GREEN}1-6${NC}  Queue actions  │  ${GREEN}b/0${NC}  ← Back  │  ${GREEN}q${NC}  Quit"
            echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
            ;;
    esac
    echo
}

# Enhanced upload history viewer with filter, search, and actions
enhanced_history_viewer() {
    print_header
    echo -e "${BOLD}📜 Upload History - Enhanced Viewer${NC}\n"

    if [[ ! -f "$RECENT_FILE" ]]; then
        mkdir -p "$DATA_DIR"
        echo "[]" > "$RECENT_FILE"
        echo -e "${YELLOW}No upload history found. Upload files to see history.${NC}\n"
        show_nav_footer "submenu"
        wait_for_q
        return
    fi

    local total_count=$(python3 -c "import json; print(len(json.load(open('$RECENT_FILE'))))" 2>/dev/null || echo "0")

    if [[ "$total_count" == "0" ]]; then
        echo -e "${YELLOW}No upload history found. Upload files to see history.${NC}\n"
        show_nav_footer "submenu"
        wait_for_q
        return
    fi

    echo -e "${CYAN}Total uploads in history: $total_count${NC}\n"
    echo -e "${BOLD}Actions:${NC}"
    echo -e "  ${GREEN}1)${NC}  View all recent uploads"
    echo -e "  ${GREEN}2)${NC}  Search by filename"
    echo -e "  ${GREEN}3)${NC}  Filter by category"
    echo -e "  ${GREEN}4)${NC}  Filter by date range"
    echo -e "  ${GREEN}5)${NC}  Copy specific URL to clipboard"
    echo -e "  ${GREEN}6)${NC}  Retry failed upload"
    echo -e "  ${GREEN}7)${NC}  Delete item from history"
    echo -e "  ${GREEN}8)${NC}  Clear all history (with backup)\n"
    show_nav_footer "submenu"

    read -p "Choose option: " option
    echo

    case $option in
        1)
            view_all_uploads
            ;;
        2)
            search_history_by_filename
            ;;
        3)
            filter_history_by_category
            ;;
        4)
            filter_history_by_date
            ;;
        5)
            copy_specific_url_from_history
            ;;
        6)
            retry_failed_upload_from_history
            ;;
        7)
            delete_item_from_history
            ;;
        8)
            clear_history_with_backup
            ;;
        b|0)
            return
            ;;
        q)
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            sleep 1
            enhanced_history_viewer
            ;;
    esac
}

# View all uploads with pagination
view_all_uploads() {
    local page_size=20
    local offset=0
    local total=$(python3 -c "import json; print(len(json.load(open('$RECENT_FILE'))))" 2>/dev/null || echo "0")

    while true; do
        print_header
        echo -e "${BOLD}All Recent Uploads${NC} (Showing $((offset+1))-$((offset+page_size > total ? total : offset+page_size)) of $total)\n"

        python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = json.load(f)
    # Reverse to show newest first
    uploads = list(reversed(uploads))
    start = $offset
    end = min($offset + $page_size, len(uploads))

    for i, item in enumerate(uploads[start:end], start=start+1):
        print(f"\033[1m{i}.\033[0m {item.get('filename', 'Unknown')}")
        print(f"   \033[2mCategory:\033[0m {item.get('category', 'Unknown')}")
        print(f"   \033[2mURL:\033[0m {item.get('url', 'No URL')}")
        print(f"   \033[2mUploaded:\033[0m {item.get('timestamp', 'Unknown')}")
        print()
EOF

        echo
        show_nav_footer "history-pagination"

        read -p "Action: " action

        case $action in
            n)
                if [[ $((offset + page_size)) -lt $total ]]; then
                    offset=$((offset + page_size))
                else
                    echo -e "${YELLOW}Already at last page${NC}"
                    sleep 1
                fi
                ;;
            p)
                if [[ $offset -gt 0 ]]; then
                    offset=$((offset - page_size))
                    [[ $offset -lt 0 ]] && offset=0
                else
                    echo -e "${YELLOW}Already at first page${NC}"
                    sleep 1
                fi
                ;;
            c)
                read -p "Enter item number to copy URL: " item_num
                if [[ "$item_num" =~ ^[0-9]+$ ]] && [[ "$item_num" -ge 1 ]] && [[ "$item_num" -le "$total" ]]; then
                    local url=$(python3 -c "import json; uploads = list(reversed(json.load(open('$RECENT_FILE')))); print(uploads[$((item_num-1))]['url'])" 2>/dev/null)
                    echo "$url" | pbcopy
                    echo -e "${GREEN}✓ URL copied to clipboard${NC}"
                    sleep 1
                else
                    echo -e "${RED}Invalid item number${NC}"
                    sleep 1
                fi
                ;;
            b)
                return
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}"
                sleep 1
                ;;
        esac
    done
}

# Search history by filename
search_history_by_filename() {
    read -p "Enter search keyword: " keyword

    if [[ -z "$keyword" ]]; then
        echo -e "${YELLOW}Search keyword cannot be empty${NC}"
        sleep 1
        return
    fi

    print_header
    echo -e "${BOLD}Search Results for: \"$keyword\"${NC}\n"

    local results=$(python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = json.load(f)
    matches = [u for u in uploads if '$keyword'.lower() in u.get('filename', '').lower()]
    print(len(matches))
EOF
)

    if [[ "$results" == "0" ]]; then
        echo -e "${YELLOW}No results found for \"$keyword\"${NC}\n"
        wait_for_q
        return
    fi

    python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = json.load(f)
    matches = [u for u in uploads if '$keyword'.lower() in u.get('filename', '').lower()]

    for i, item in enumerate(matches, 1):
        print(f"\033[1m{i}.\033[0m {item.get('filename', 'Unknown')}")
        print(f"   \033[2mCategory:\033[0m {item.get('category', 'Unknown')}")
        print(f"   \033[2mURL:\033[0m {item.get('url', 'No URL')}")
        print(f"   \033[2mUploaded:\033[0m {item.get('timestamp', 'Unknown')}")
        print()
EOF

    echo -e "\n${GREEN}Found $results result(s)${NC}"
    wait_for_q
}

# Filter by category
filter_history_by_category() {
    echo -e "${BOLD}Filter by Category:${NC}\n"
    echo -e "  ${GREEN}1)${NC}  Audio"
    echo -e "  ${GREEN}2)${NC}  Images"
    echo -e "  ${GREEN}3)${NC}  Video"
    echo -e "  ${GREEN}4)${NC}  Scripts"
    echo -e "  ${GREEN}5)${NC}  Documents"
    echo -e "  ${GREEN}6)${NC}  Other\n"

    read -p "Choose category: " cat_choice

    local category=""
    case $cat_choice in
        1) category="Audio" ;;
        2) category="Images" ;;
        3) category="Video" ;;
        4) category="Scripts" ;;
        5) category="Documents" ;;
        6) category="Other" ;;
        *) echo -e "${RED}Invalid option${NC}"; sleep 1; return ;;
    esac

    print_header
    echo -e "${BOLD}Uploads in Category: $category${NC}\n"

    python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = json.load(f)
    matches = [u for u in uploads if u.get('category', '') == '$category']

    if not matches:
        print("\033[1;33mNo uploads found in this category\033[0m")
    else:
        for i, item in enumerate(matches, 1):
            print(f"\033[1m{i}.\033[0m {item.get('filename', 'Unknown')}")
            print(f"   \033[2mURL:\033[0m {item.get('url', 'No URL')}")
            print(f"   \033[2mUploaded:\033[0m {item.get('timestamp', 'Unknown')}")
            print()
        print(f"\033[1;32mTotal: {len(matches)} upload(s)\033[0m")
EOF

    wait_for_q
}

# Filter by date range
filter_history_by_date() {
    read -p "Enter start date (YYYY-MM-DD): " start_date
    read -p "Enter end date (YYYY-MM-DD): " end_date

    if [[ -z "$start_date" ]] || [[ -z "$end_date" ]]; then
        echo -e "${YELLOW}Both dates are required${NC}"
        sleep 1
        return
    fi

    print_header
    echo -e "${BOLD}Uploads between $start_date and $end_date${NC}\n"

    python3 << EOF
import json
from datetime import datetime

with open('$RECENT_FILE', 'r') as f:
    uploads = json.load(f)
    start = datetime.fromisoformat('$start_date')
    end = datetime.fromisoformat('$end_date')

    matches = []
    for u in uploads:
        try:
            upload_date = datetime.fromisoformat(u.get('timestamp', '').split('T')[0])
            if start <= upload_date <= end:
                matches.append(u)
        except:
            pass

    if not matches:
        print("\033[1;33mNo uploads found in this date range\033[0m")
    else:
        for i, item in enumerate(matches, 1):
            print(f"\033[1m{i}.\033[0m {item.get('filename', 'Unknown')}")
            print(f"   \033[2mCategory:\033[0m {item.get('category', 'Unknown')}")
            print(f"   \033[2mURL:\033[0m {item.get('url', 'No URL')}")
            print(f"   \033[2mUploaded:\033[0m {item.get('timestamp', 'Unknown')}")
            print()
        print(f"\033[1;32mTotal: {len(matches)} upload(s)\033[0m")
EOF

    wait_for_q
}

# Copy specific URL from history
copy_specific_url_from_history() {
    local total=$(python3 -c "import json; print(len(json.load(open('$RECENT_FILE'))))" 2>/dev/null || echo "0")

    echo -e "${BOLD}Recent Uploads:${NC}\n"

    python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = list(reversed(json.load(f)))  # Newest first
    for i, item in enumerate(uploads[:20], 1):  # Show last 20
        print(f"{i}. {item.get('filename', 'Unknown')}")
EOF

    echo
    read -p "Enter item number to copy URL (1-$total): " item_num

    if [[ "$item_num" =~ ^[0-9]+$ ]] && [[ "$item_num" -ge 1 ]] && [[ "$item_num" -le "$total" ]]; then
        local url=$(python3 -c "import json; uploads = list(reversed(json.load(open('$RECENT_FILE')))); print(uploads[$((item_num-1))]['url'])" 2>/dev/null)
        echo "$url" | pbcopy
        echo -e "\n${GREEN}✓ URL copied to clipboard:${NC}"
        echo -e "${BLUE}$url${NC}\n"
        sleep 2
    else
        echo -e "${RED}Invalid item number${NC}"
        sleep 1
    fi
}

# Retry failed upload from history
retry_failed_upload_from_history() {
    echo -e "${BOLD}Retry Failed Upload${NC}\n"
    echo -e "${DIM}Note: This will attempt to re-upload the original file if it still exists${NC}\n"

    # Show recent uploads
    python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = list(reversed(json.load(f)))[:20]
    for i, item in enumerate(uploads, 1):
        print(f"{i}. {item.get('filename', 'Unknown')} - {item.get('category', 'Unknown')}")
EOF

    echo
    read -p "Enter item number to retry: " item_num

    if [[ "$item_num" =~ ^[0-9]+$ ]]; then
        local filepath=$(python3 -c "import json; uploads = list(reversed(json.load(open('$RECENT_FILE')))); print(uploads[$((item_num-1))].get('filepath', ''))" 2>/dev/null)

        if [[ -z "$filepath" ]]; then
            echo -e "${RED}Error: Could not find original filepath${NC}"
            sleep 2
            return
        fi

        if [[ ! -f "$filepath" ]]; then
            echo -e "${RED}Error: Original file no longer exists at: $filepath${NC}"
            sleep 2
            return
        fi

        echo -e "\n${CYAN}Re-uploading: $filepath${NC}\n"
        "$GHU" "$filepath"

        echo -e "\n${GREEN}✓ Upload completed${NC}"
        sleep 2
    else
        echo -e "${RED}Invalid item number${NC}"
        sleep 1
    fi
}

# Delete item from history
delete_item_from_history() {
    echo -e "${BOLD}Delete Item from History${NC}\n"
    echo -e "${RED}Warning: This only removes from history, not from GitHub${NC}\n"

    python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = list(reversed(json.load(f)))[:20]
    for i, item in enumerate(uploads, 1):
        print(f"{i}. {item.get('filename', 'Unknown')}")
EOF

    echo
    read -p "Enter item number to delete: " item_num

    if [[ "$item_num" =~ ^[0-9]+$ ]]; then
        if confirm "Delete this item from history?"; then
            python3 << EOF
import json
with open('$RECENT_FILE', 'r') as f:
    uploads = json.load(f)

# Remove item (accounting for reversed display)
total = len(uploads)
actual_index = total - $item_num
if 0 <= actual_index < total:
    removed = uploads.pop(actual_index)
    with open('$RECENT_FILE', 'w') as f:
        json.dump(uploads, f, indent=2)
    print(f"\033[1;32m✓ Deleted: {removed.get('filename', 'Unknown')}\033[0m")
else:
    print("\033[1;31mError: Invalid index\033[0m")
EOF
            sleep 1
        fi
    else
        echo -e "${RED}Invalid item number${NC}"
        sleep 1
    fi
}

# Clear history with automatic backup
clear_history_with_backup() {
    local total=$(python3 -c "import json; print(len(json.load(open('$RECENT_FILE'))))" 2>/dev/null || echo "0")

    echo -e "${BOLD}Clear Upload History${NC}\n"
    echo -e "${YELLOW}Current history: $total uploads${NC}"
    echo -e "${DIM}A backup will be created automatically${NC}\n"

    if confirm "Clear all upload history?"; then
        local backup_file="$DATA_DIR/recent_backup_$(date +%Y%m%d_%H%M%S).json"
        cp "$RECENT_FILE" "$backup_file"
        echo "[]" > "$RECENT_FILE"

        echo -e "\n${GREEN}✓ History cleared${NC}"
        echo -e "${CYAN}Backup saved to: $backup_file${NC}\n"
        sleep 2
    fi
}

# Upload queue system for batch operations
upload_queue_manager() {
    local queue_file="$DATA_DIR/upload_queue.json"

    # Initialize queue if doesn't exist
    if [[ ! -f "$queue_file" ]]; then
        echo "[]" > "$queue_file"
    fi

    while true; do
        print_header
        echo -e "${BOLD}📋 Upload Queue Manager${NC}\n"

        local queue_size=$(python3 -c "import json; print(len(json.load(open('$queue_file'))))" 2>/dev/null || echo "0")

        echo -e "${CYAN}Items in queue: $queue_size${NC}\n"

        if [[ "$queue_size" -gt 0 ]]; then
            echo -e "${BOLD}Queued Files:${NC}"
            python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)
    for i, item in enumerate(queue, 1):
        status_icon = "⏳" if item.get('status') == 'pending' else ("✓" if item.get('status') == 'completed' else "✗")
        print(f"  {status_icon} {i}. {item.get('filename', 'Unknown')}")
EOF
            echo
        fi

        echo -e "${BOLD}Actions:${NC}"
        echo -e "  ${GREEN}1)${NC}  Add files to queue"
        echo -e "  ${GREEN}2)${NC}  Process queue (upload all)"
        echo -e "  ${GREEN}3)${NC}  View queue details"
        echo -e "  ${GREEN}4)${NC}  Remove item from queue"
        echo -e "  ${GREEN}5)${NC}  Clear completed items"
        echo -e "  ${GREEN}6)${NC}  Clear entire queue\n"
        show_nav_footer "queue"

        read -p "Choose option: " option
        echo

        case $option in
            1)
                add_files_to_queue "$queue_file"
                ;;
            2)
                process_upload_queue "$queue_file"
                ;;
            3)
                view_queue_details "$queue_file"
                ;;
            4)
                remove_from_queue "$queue_file"
                ;;
            5)
                clear_completed_from_queue "$queue_file"
                ;;
            6)
                if confirm "Clear entire queue?"; then
                    echo "[]" > "$queue_file"
                    echo -e "${GREEN}✓ Queue cleared${NC}"
                    sleep 1
                fi
                ;;
            b|0)
                return
                ;;
            q)
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}"
                sleep 1
                ;;
        esac
    done
}

# Add files to upload queue
add_files_to_queue() {
    local queue_file="$1"

    echo -e "${BOLD}Add Files to Queue${NC}\n"
    echo -e "  ${GREEN}1)${NC}  Add single file"
    echo -e "  ${GREEN}2)${NC}  Add multiple files (one per line)"
    echo -e "  ${GREEN}3)${NC}  Add all files from directory"
    echo -e "  ${GREEN}q)${NC}  Cancel\n"

    read -p "Choose option: " add_option
    echo

    case $add_option in
        1)
            read -p "Enter file path: " filepath
            filepath="${filepath#"${filepath%%[![:space:]]*}"}"  # Trim leading
            filepath="${filepath%"${filepath##*[![:space:]]}"}"  # Trim trailing
            while [[ "$filepath" == \'*\' || "$filepath" == \"*\" ]]; do
                [[ "$filepath" == \'*\' ]] && filepath="${filepath:1:-1}"
                [[ "$filepath" == \"*\" ]] && filepath="${filepath:1:-1}"
            done
            filepath="${filepath/#\~/$HOME}"

            if [[ -f "$filepath" ]]; then
                python3 << EOF
import json, os
with open('$queue_file', 'r') as f:
    queue = json.load(f)

queue.append({
    'filepath': '$filepath',
    'filename': os.path.basename('$filepath'),
    'status': 'pending',
    'added': '$(date -Iseconds)'
})

with open('$queue_file', 'w') as f:
    json.dump(queue, f, indent=2)

print("\033[1;32m✓ Added to queue\033[0m")
EOF
                sleep 1
            else
                echo -e "${RED}File not found${NC}"
                sleep 1
            fi
            ;;
        2)
            echo -e "Enter file paths (one per line, empty line to finish):"
            local paths=()
            while IFS= read -r line; do
                [[ -z "$line" ]] && break
                paths+=("$line")
            done

            for path in "${paths[@]}"; do
                # Trim and clean path
                path="${path#"${path%%[![:space:]]*}"}"
                path="${path%"${path##*[![:space:]]}"}"
                while [[ "$path" == \'*\' || "$path" == \"*\" ]]; do
                    [[ "$path" == \'*\' ]] && path="${path:1:-1}"
                    [[ "$path" == \"*\" ]] && path="${path:1:-1}"
                done
                path="${path/#\~/$HOME}"

                if [[ -f "$path" ]]; then
                    python3 << EOF
import json, os
with open('$queue_file', 'r') as f:
    queue = json.load(f)

queue.append({
    'filepath': '$path',
    'filename': os.path.basename('$path'),
    'status': 'pending',
    'added': '$(date -Iseconds)'
})

with open('$queue_file', 'w') as f:
    json.dump(queue, f, indent=2)
EOF
                fi
            done
            echo -e "${GREEN}✓ Files added to queue${NC}"
            sleep 1
            ;;
        3)
            read -p "Enter directory path: " dirpath
            dirpath="${dirpath#"${dirpath%%[![:space:]]*}"}"
            dirpath="${dirpath%"${dirpath##*[![:space:]]}"}"
            while [[ "$dirpath" == \'*\' || "$dirpath" == \"*\" ]]; do
                [[ "$dirpath" == \'*\' ]] && dirpath="${dirpath:1:-1}"
                [[ "$dirpath" == \"*\" ]] && dirpath="${dirpath:1:-1}"
            done
            dirpath="${dirpath/#\~/$HOME}"

            if [[ -d "$dirpath" ]]; then
                local file_count=0
                while IFS= read -r file; do
                    python3 << EOF
import json, os
with open('$queue_file', 'r') as f:
    queue = json.load(f)

queue.append({
    'filepath': '$file',
    'filename': os.path.basename('$file'),
    'status': 'pending',
    'added': '$(date -Iseconds)'
})

with open('$queue_file', 'w') as f:
    json.dump(queue, f, indent=2)
EOF
                    ((file_count++))
                done < <(find "$dirpath" -type f -not -path '*/\.*')

                echo -e "${GREEN}✓ Added $file_count files to queue${NC}"
                sleep 2
            else
                echo -e "${RED}Directory not found${NC}"
                sleep 1
            fi
            ;;
        q)
            return
            ;;
    esac
}

# Process upload queue with progress indicators
process_upload_queue() {
    local queue_file="$1"

    local total=$(python3 -c "import json; q=json.load(open('$queue_file')); print(len([x for x in q if x.get('status')=='pending']))" 2>/dev/null || echo "0")

    if [[ "$total" == "0" ]]; then
        echo -e "${YELLOW}No pending items in queue${NC}"
        sleep 1
        return
    fi

    print_header
    echo -e "${BOLD}Processing Upload Queue${NC}\n"
    echo -e "${CYAN}Total items to upload: $total${NC}\n"

    if ! confirm "Start uploading $total file(s)?"; then
        return
    fi

    local completed=0
    local failed=0

    python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)

pending_items = [(i, item) for i, item in enumerate(queue) if item.get('status') == 'pending']

for idx, (i, item) in enumerate(pending_items, 1):
    filepath = item['filepath']
    filename = item['filename']

    print(f"\n\033[1;36m[{idx}/$total]\033[0m Uploading: {filename}")
    print(f"\033[2m{'━' * 50}\033[0m")

    # Write current index to temp file for bash to read
    with open('/tmp/gupload_queue_current.txt', 'w') as tf:
        tf.write(str(i))
EOF

    # Read the queue and upload each file
    while read -r queue_index; do
        local filepath=$(python3 -c "import json; q=json.load(open('$queue_file')); print(q[$queue_index]['filepath'])")
        local filename=$(python3 -c "import json; q=json.load(open('$queue_file')); print(q[$queue_index]['filename'])")

        # Show progress bar
        echo -ne "\r${CYAN}Progress: [$completed/$total]${NC} "
        for ((i=0; i<$completed*50/$total; i++)); do echo -n "█"; done
        echo

        # Attempt upload
        if "$GHU" "$filepath" >> /tmp/gupload_queue.log 2>&1; then
            ((completed++))
            # Update status to completed
            python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)
queue[$queue_index]['status'] = 'completed'
with open('$queue_file', 'w') as f:
    json.dump(queue, f, indent=2)
EOF
            echo -e "${GREEN}✓ Uploaded successfully${NC}"
        else
            ((failed++))
            python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)
queue[$queue_index]['status'] = 'failed'
queue[$queue_index]['error'] = 'Upload failed'
with open('$queue_file', 'w') as f:
    json.dump(queue, f, indent=2)
EOF
            echo -e "${RED}✗ Upload failed${NC}"
        fi
    done < <(python3 -c "import json; q=json.load(open('$queue_file')); print('\n'.join(str(i) for i,x in enumerate(q) if x.get('status')=='pending'))")

    # Final summary
    echo -e "\n${DIM}${'━' * 50}${NC}"
    echo -e "${BOLD}Upload Queue Complete${NC}\n"
    echo -e "${GREEN}✓ Completed: $completed${NC}"
    if [[ $failed -gt 0 ]]; then
        echo -e "${RED}✗ Failed: $failed${NC}"
    fi
    echo

    wait_for_q
}

# View queue details
view_queue_details() {
    local queue_file="$1"

    print_header
    echo -e "${BOLD}Upload Queue - Detailed View${NC}\n"

    python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)

if not queue:
    print("\033[1;33mQueue is empty\033[0m")
else:
    for i, item in enumerate(queue, 1):
        status = item.get('status', 'unknown')
        status_color = '\033[1;32m' if status == 'completed' else ('\033[1;31m' if status == 'failed' else '\033[1;33m')
        status_icon = '✓' if status == 'completed' else ('✗' if status == 'failed' else '⏳')

        print(f"\033[1m{i}. {item.get('filename', 'Unknown')}\033[0m")
        print(f"   Status: {status_color}{status_icon} {status.title()}\033[0m")
        print(f"   Path: \033[2m{item.get('filepath', 'Unknown')}\033[0m")
        print(f"   Added: \033[2m{item.get('added', 'Unknown')}\033[0m")
        if 'error' in item:
            print(f"   Error: \033[1;31m{item['error']}\033[0m")
        print()
EOF

    wait_for_q
}

# Remove item from queue
remove_from_queue() {
    local queue_file="$1"

    echo -e "${BOLD}Remove Item from Queue${NC}\n"

    python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)
for i, item in enumerate(queue, 1):
    print(f"{i}. {item.get('filename', 'Unknown')} - {item.get('status', 'unknown')}")
EOF

    echo
    read -p "Enter item number to remove: " item_num

    if [[ "$item_num" =~ ^[0-9]+$ ]]; then
        python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)

if 1 <= $item_num <= len(queue):
    removed = queue.pop($item_num - 1)
    with open('$queue_file', 'w') as f:
        json.dump(queue, f, indent=2)
    print(f"\033[1;32m✓ Removed: {removed.get('filename', 'Unknown')}\033[0m")
else:
    print("\033[1;31mInvalid item number\033[0m")
EOF
        sleep 1
    fi
}

# Clear completed items from queue
clear_completed_from_queue() {
    local queue_file="$1"

    local completed_count=$(python3 -c "import json; q=json.load(open('$queue_file')); print(len([x for x in q if x.get('status')=='completed']))" 2>/dev/null || echo "0")

    if [[ "$completed_count" == "0" ]]; then
        echo -e "${YELLOW}No completed items to clear${NC}"
        sleep 1
        return
    fi

    if confirm "Remove $completed_count completed item(s) from queue?"; then
        python3 << EOF
import json
with open('$queue_file', 'r') as f:
    queue = json.load(f)

queue = [x for x in queue if x.get('status') != 'completed']

with open('$queue_file', 'w') as f:
    json.dump(queue, f, indent=2)

print(f"\033[1;32m✓ Cleared $completed_count completed item(s)\033[0m")
EOF
        sleep 1
    fi
}

# Main menu loop
main() {
    while true; do
        print_header
        print_menu
        
        read -p "Choose an option [0-8]: " choice
        echo

        case $choice in
            1)
                upload_files_submenu
                ;;
            2)
                browse_repo_submenu
                ;;
            3)
                audio_tools_submenu
                ;;
            4)
                quick_access_submenu
                ;;
            5)
                advanced_tools_submenu
                ;;
            6)
                configure_submenu
                ;;
            7)
                view_logs_submenu
                ;;
            8)
                stats_info_submenu
                ;;
            0)
                echo -e "${GREEN}Goodbye!${NC}\n"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}\n"
                sleep 1
                ;;
        esac
    done
}

# Run main function
main
