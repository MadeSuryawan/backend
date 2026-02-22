#!/bin/bash

# scripts/clean_browser.sh
# Mitigation for persistent browser auto-launch issues

set -e

PROFILE_DIR="$HOME/.gemini/antigravity-browser-profile"
PREFS_FILE="$PROFILE_DIR/Default/Preferences"

echo "🧹 Starting Antigravity Browser cleanup..."

# 1. Kill lingering processes
echo "🕵️  Checking for lingering Chromium processes..."
PIDS=$(ps aux | grep -i "antigravity-browser-profile" | grep -v grep | awk '{print $2}')
if [ -z "$PIDS" ]; then
    echo "✅ No lingering processes found."
else
    echo "⚠️  Killing lingering processes: $PIDS"
    echo "$PIDS" | xargs kill -9
fi

# 2. Reset Preferences (exit_type)
if [ -f "$PREFS_FILE" ]; then
    echo "🔧 Resetting browser exit_type to 'Normal'..."
    # Use python for safe JSON manipulation
    python3 -c "
import json, sys
try:
    with open('$PREFS_FILE', 'r') as f:
        data = json.load(f)
    if 'profile' in data:
        data['profile']['exit_type'] = 'Normal'
        data['profile']['exited_cleanly'] = True
    else:
        # Some versions have it at top level or different nesting
        data['exit_type'] = 'Normal'
        data['exited_cleanly'] = True
    
    with open('$PREFS_FILE', 'w') as f:
        json.dump(data, f)
    print('✅ exit_type reset successfully.')
except Exception as e:
    print(f'❌ Error resetting Preferences: {e}')
"
fi

# 3. Clear problematic session directories
echo "🗑️  Clearing session and service worker storage..."
rm -rf "$PROFILE_DIR/Default/Service Worker/Database"
rm -rf "$PROFILE_DIR/Default/Session Storage"
rm -rf "$PROFILE_DIR/Default/Sessions"

echo "✨ Browser state cleaned. Please reload your IDE window if the issue persists."
