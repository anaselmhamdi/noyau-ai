#!/bin/bash
# Refresh Nitter/Twitter session tokens
# Run via cron: 0 3 */10 * * /path/to/refresh_nitter_tokens.sh
#
# Requires: xvfb, chromium (or chrome)
# Install: apt install xvfb chromium-browser

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
BROWSER_SCRIPT="$PROJECT_DIR/nitter/scripts/create_session_browser.py"
SESSIONS_FILE="$PROJECT_DIR/nitter/sessions.jsonl"
LOG_FILE="$PROJECT_DIR/logs/nitter_refresh.log"

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -E '^TWITTER_(USERNAME|PASSWORD|TOTP_SECRET)=' "$PROJECT_DIR/.env" | xargs)
fi

# Validate credentials
if [ -z "$TWITTER_USERNAME" ] || [ -z "$TWITTER_PASSWORD" ]; then
    echo "$(date): ERROR - TWITTER_USERNAME or TWITTER_PASSWORD not set" >> "$LOG_FILE"
    exit 1
fi

# Create logs directory if needed
mkdir -p "$(dirname "$LOG_FILE")"

echo "$(date): Starting token refresh for @$TWITTER_USERNAME" >> "$LOG_FILE"

# Build command
CMD="$VENV_PYTHON $BROWSER_SCRIPT $TWITTER_USERNAME $TWITTER_PASSWORD"
if [ -n "$TWITTER_TOTP_SECRET" ]; then
    CMD="$CMD $TWITTER_TOTP_SECRET"
fi
CMD="$CMD --append $SESSIONS_FILE"

# Run with xvfb (virtual display)
if command -v xvfb-run &> /dev/null; then
    xvfb-run --auto-servernum --server-args="-screen 0 1280x720x24" $CMD >> "$LOG_FILE" 2>&1
    RESULT=$?
else
    echo "$(date): WARNING - xvfb-run not found, trying without display" >> "$LOG_FILE"
    $CMD --headless >> "$LOG_FILE" 2>&1
    RESULT=$?
fi

if [ $RESULT -eq 0 ]; then
    echo "$(date): Token refresh successful" >> "$LOG_FILE"

    # Restart Nitter to pick up new tokens (if running in Docker)
    if command -v docker &> /dev/null; then
        docker restart noyau-ai-nitter-1 2>/dev/null || true
    fi
else
    echo "$(date): Token refresh FAILED with exit code $RESULT" >> "$LOG_FILE"
    exit $RESULT
fi
