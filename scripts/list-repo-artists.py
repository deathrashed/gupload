#!/usr/bin/env python3
"""List artists from GitHub repo - helper script for menu"""
import sys
import json
import os
# Add repo root to path to import ghuploader
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)

from ghuploader import load_config, get_token, api_request

def list_artists():
    """List all artists in the Audio directory of the repo"""
    cfg = load_config()
    token = get_token(cfg)
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")
    
    # Check if organize_by_artist is enabled
    organize_by_artist = cfg.get("organize_by_artist", False)
    
    if organize_by_artist:
        # List Audio directory to get artists
        path = "Audio"
    else:
        # List Images/Covers to get artist names from filenames
        path = "Images/Covers"
    
    # URL-encode path
    encoded_path = path.replace(" ", "%20").replace("/", "/")
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    
    try:
        result = api_request("GET", url, token)
        if not result:
            return []
        
        # If result is a file, return empty (shouldn't happen)
        if not isinstance(result, list):
            return []
        
        artists = []
        for item in result:
            if item.get("type") == "dir":
                artists.append(item["name"])
            elif item.get("type") == "file" and not organize_by_artist:
                # Extract artist from filename like "Cold Steel - Album.jpg"
                name = item["name"]
                if " - " in name:
                    artist = name.split(" - ")[0]
                    if artist not in artists:
                        artists.append(artist)
        
        return sorted(artists)
    except Exception as e:
        # If path doesn't exist, return empty
        return []

def list_artist_files(artist_name):
    """List files for a specific artist"""
    cfg = load_config()
    token = get_token(cfg)
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")
    
    organize_by_artist = cfg.get("organize_by_artist", False)
    
    if organize_by_artist:
        path = f"Audio/{artist_name}"
    else:
        # Would need to search across categories - for now return empty
        return []
    
    # URL-encode path
    path_parts = path.split("/")
    encoded_parts = [part.replace(" ", "%20") for part in path_parts]
    encoded_path = "/".join(encoded_parts)
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}?ref={branch}"
    
    try:
        result = api_request("GET", url, token)
        if not result:
            return []
        
        if not isinstance(result, list):
            return []
        
        files = []
        for item in result:
            files.append({
                "name": item["name"],
                "type": item.get("type", "file"),
                "path": item["path"]
            })
        
        return files
    except Exception:
        return []

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--files":
        # List files for an artist
        artist = sys.argv[2] if len(sys.argv) > 2 else ""
        files = list_artist_files(artist)
        print(json.dumps(files))
    else:
        # List all artists
        artists = list_artists()
        print("\n".join(artists))
