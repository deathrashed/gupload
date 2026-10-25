#!/usr/bin/env bash
# Exercise the real terminal menu with EOF at its first prompt (safe quit).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
GHU="${GHU:-$(cd "$SCRIPT_DIR/.." && pwd -P)/bin/gupload}"
if [[ ! -x "$GHU" ]]; then
    echo "test-menu: gupload launcher is not executable: $GHU" >&2
    exit 1
fi
output="$("$GHU" --menu </dev/null)"
if [[ "$output" != *"gupload  offline-first uploader for GitHub"* ]]; then
    echo "test-menu: terminal menu did not render its main screen." >&2
    exit 1
fi
echo "test-menu: terminal menu rendered and quit at EOF; no upload was selected."
