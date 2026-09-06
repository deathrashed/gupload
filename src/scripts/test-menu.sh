#!/bin/bash
# Test script for menu functions without interactive loops

set -u

# Source the menu script functions
source /Volumes/Eksternal/Projects/Gupload/scripts/gupload-menu.sh

# Test files
TEST_LOGO="/Volumes/Eksternal/Audio/Metal/D/Deeds Of Flesh/logo.png"
TEST_COVER="/Volumes/Eksternal/Audio/Metal/D/Deeds Of Flesh/1996 - Trading Pieces/cover.jpg"
TEST_ARTIST="/Volumes/Eksternal/Audio/Metal/D/Deeds Of Flesh/artist.jpg"
TEST_AUDIO="/Volumes/Eksternal/Audio/Metal/D/Deeds Of Flesh/1996 - Trading Pieces/10. Blasted.mp3"
TEST_ARTIST_PATH="/Volumes/Eksternal/Audio/Metal/D/Deeds Of Flesh"

echo "=== Testing Menu Functions ==="
echo

# Test 1: Check if ghu script is found
echo "Test 1: Checking ghu script..."
if check_ghu; then
    echo "✓ GHU found: $GHU"
else
    echo "✗ GHU not found!"
    exit 1
fi
echo

# Test 2: Test upload_with_custom_naming function with default naming
echo "Test 2: Testing default upload (should show upload command)..."
echo "File: $TEST_LOGO"
echo "Expected: Should call ghu with file path"
# We'll just check if it can build the command, not actually upload
echo "Command would be: $GHU \"$TEST_LOGO\""
echo

# Test 3: Test custom naming path building
echo "Test 3: Testing custom naming..."
CUSTOM_NAME="test-deeds-logo.png"
echo "File: $TEST_LOGO"
echo "Custom name: $CUSTOM_NAME"
echo "Command would be: $GHU --name \"$CUSTOM_NAME\" \"$TEST_LOGO\""
echo

# Test 4: Test upload_from_url function (without actually uploading)
echo "Test 4: Testing URL upload function..."
TEST_URL="https://f4.bcbits.com/img/a1454706092_5.jpg"
echo "URL: $TEST_URL"
echo "Custom name: Deeds Of Flesh - 1996 - Trading Pieces.jpg"
echo "Command would be: $GHU --name \"Deeds Of Flesh - 1996 - Trading Pieces.jpg\" \"$TEST_URL\""
echo

# Test 5: Test upload_artist_assets path handling
echo "Test 5: Testing artist assets path handling..."
TEST_PATH_WITH_QUOTES="'/Volumes/Eksternal/Audio/Metal/D/Deeds Of Flesh'"
echo "Input path: $TEST_PATH_WITH_QUOTES"
# Simulate quote stripping
artist_path="$TEST_PATH_WITH_QUOTES"
artist_path="${artist_path#"${artist_path%%[![:space:]]*}"}"
artist_path="${artist_path%"${artist_path##*[![:space:]]}"}"
while [[ "$artist_path" == \'*\' || "$artist_path" == \"*\" ]]; do
    [[ "$artist_path" == \'*\' ]] && artist_path="${artist_path:1:-1}"
    [[ "$artist_path" == \"*\" ]] && artist_path="${artist_path:1:-1}"
done
echo "Stripped path: $artist_path"
if [[ -d "$artist_path" ]]; then
    echo "✓ Path is valid directory"
else
    echo "✗ Path is not valid"
fi
echo

# Test 6: Test upload-artist-assets.sh script
echo "Test 6: Testing upload-artist-assets.sh script..."
if [[ -x "/Volumes/Eksternal/Projects/Gupload/scripts/upload-artist-assets.sh" ]]; then
    echo "✓ Script is executable"
    echo "Would run: GHU=\"$GHU\" /Volumes/Eksternal/Projects/Gupload/scripts/upload-artist-assets.sh \"$TEST_ARTIST_PATH\""
else
    echo "✗ Script not found or not executable"
fi
echo

# Test 7: Test actual upload with dry-run check
echo "Test 7: Testing actual upload commands (DRY RUN - not executing)..."
echo
echo "Command 1: Upload logo with default naming"
echo "  $GHU \"$TEST_LOGO\""
echo
echo "Command 2: Upload logo with custom name"
echo "  $GHU --name \"test-deeds-logo.png\" \"$TEST_LOGO\""
echo
echo "Command 3: Upload cover with default naming"
echo "  $GHU \"$TEST_COVER\""
echo
echo "Command 4: Upload audio track"
echo "  $GHU \"$TEST_AUDIO\""
echo

echo "=== All Tests Completed ==="
echo "Note: These are dry-run tests. Actual uploads require GitHub authentication."
