#!/usr/bin/env python3
"""
Get YouTube OAuth refresh token.

Usage:
    python scripts/youtube_oauth.py

Loads credentials from .env file automatically.

Requires: pip install google-auth-oauthlib python-dotenv
"""

import os
import sys

try:
    from dotenv import load_dotenv
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with:")
    print("  pip install google-auth-oauthlib python-dotenv")
    sys.exit(1)

# Load .env file
load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("Error: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set")
    print()
    print("Usage:")
    print('  YOUTUBE_CLIENT_ID="xxx" YOUTUBE_CLIENT_SECRET="xxx" python scripts/youtube_oauth.py')
    sys.exit(1)

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": ["http://localhost:8080"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    SCOPES,
)

print("Opening browser for authorization...")
print("(Make sure to select the YouTube channel you want to upload to)")
print()

creds = flow.run_local_server(port=8080, prompt="consent")

print()
print("=" * 60)
print("SUCCESS! Add this to your .env file:")
print("=" * 60)
print()
print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
print()
