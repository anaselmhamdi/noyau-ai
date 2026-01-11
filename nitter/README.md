# Self-Hosted Nitter Setup

Nitter requires real Twitter/X account session tokens to function. This directory contains the configuration for the self-hosted Nitter instance.

## Files

- `nitter.conf` - Nitter configuration (Redis connection, RSS settings)
- `sessions.jsonl` - Twitter session tokens (you must create this)

## Setup Instructions

### 1. Create a Twitter/X Account

Create a dedicated Twitter/X account for Nitter. A throwaway account is recommended as it may get suspended.

### 2. Generate Session Tokens

Clone the Nitter repository and use the session creation scripts:

```bash
# Clone Nitter repo (for the scripts only)
git clone https://github.com/zedeus/nitter.git /tmp/nitter-scripts
cd /tmp/nitter-scripts

# Install dependencies
pip install -r requirements.txt

# Method 1: Browser automation (more reliable, requires display)
python3 create_session_browser.py <username> <password> [totp_secret] --append sessions.jsonl

# Method 2: HTTP requests (faster, may trigger bot detection)
python3 create_session_curl.py <username> <password> [totp_secret] --append sessions.jsonl
```

If your account has 2FA enabled, you need the TOTP secret (the base32 string from X.com's 2FA setup - click "can't scan" on the QR code page).

### 3. Copy Session Tokens

Copy the generated `sessions.jsonl` to this directory:

```bash
cp /tmp/nitter-scripts/sessions.jsonl ./nitter/sessions.jsonl
```

### 4. Start Nitter

```bash
docker compose up -d nitter-redis nitter
```

### 5. Test the Instance

```bash
# Check if Nitter is running
curl -I http://localhost:8080/

# Test RSS feed
curl http://localhost:8080/simonw/rss
```

### 6. Test Ingestion

```bash
# Check token status
python -m app.jobs.ingest token-status

# Test fetching
python -m app.jobs.ingest fetch nitter --dry-run --verbose --limit 5
```

## CLI Commands

```bash
# Check token status and health
python -m app.jobs.ingest token-status

# Manually refresh tokens (uses TWITTER_* env vars)
python -m app.jobs.ingest refresh-tokens

# Test Nitter fetcher
python -m app.jobs.ingest fetch nitter --dry-run --verbose
```

## Automatic Token Refresh

The Nitter fetcher automatically:
1. Checks if session tokens exist
2. Tests token health against the self-hosted instance
3. Attempts to refresh tokens if they're stale

For automatic refresh to work, set these environment variables:
```bash
TWITTER_USERNAME=your_twitter_username
TWITTER_PASSWORD=your_twitter_password
TWITTER_TOTP_SECRET=your_2fa_secret  # Optional, only if 2FA is enabled
```

## Session Token Format

The `sessions.jsonl` file should contain one JSON object per line:

```jsonl
{"kind": "cookie", "auth_token": "abc123...", "ct0": "xyz789...", "username": "your_username", "id": "12345"}
```

## Troubleshooting

### "Rate limited" errors
- Add more accounts to `sessions.jsonl`
- Nitter rotates through available sessions automatically

### "Session expired" errors
- Re-generate the session token for the affected account
- Twitter may have invalidated the session

### Empty RSS feeds
- Check Nitter logs: `docker compose logs nitter`
- Verify Redis is running: `docker compose logs nitter-redis`
- Ensure the Twitter account can access the target profiles

## VM Deployment with Auto-Refresh

### Prerequisites
```bash
# Install xvfb and chromium for headless browser automation
apt update && apt install -y xvfb chromium-browser
```

### Cron Setup
Add a cron job to refresh tokens every 10 days:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 3 AM on days 1, 11, 21 of each month)
0 3 1,11,21 * * /path/to/noyau-ai/scripts/refresh_nitter_tokens.sh
```

### Manual Refresh on VM
```bash
cd /path/to/noyau-ai
xvfb-run --auto-servernum .venv/bin/python nitter/scripts/create_session_browser.py \
  "$TWITTER_USERNAME" "$TWITTER_PASSWORD" --append nitter/sessions.jsonl
```

### Logs
Refresh logs are written to `logs/nitter_refresh.log`

## Production Notes

- Use a dedicated Twitter account for Nitter (may get suspended)
- Monitor `logs/nitter_refresh.log` for failures
- Tokens typically last 2-4 weeks before expiring
- Consider running Nitter behind Caddy for HTTPS
