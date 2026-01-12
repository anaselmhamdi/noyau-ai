#!/usr/bin/env python3
"""
Extract Twitter cookies from Chrome and append to sessions.jsonl.

Run this inside the nitter-browser container after logging into x.com:
  python3 /scripts/extract_cookies.py

Or from host:
  docker compose exec nitter-browser python3 /scripts/extract_cookies.py
"""

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

SESSIONS_FILE = "/data/sessions.jsonl"


def find_chrome_cookies_db():
    """Find Chrome cookies database in common locations."""
    possible_paths = [
        # Kasm Chrome
        Path.home() / ".config/google-chrome/Default/Cookies",
        Path.home() / ".config/chromium/Default/Cookies",
        Path.home() / ".config/google-chrome/Profile 1/Cookies",
        # Standard Linux Chrome
        Path("/home/kasm-user/.config/google-chrome/Default/Cookies"),
        Path("/home/kasm-user/.config/chromium/Default/Cookies"),
    ]

    for path in possible_paths:
        if path.exists():
            return path

    # Search for it
    for root in [Path.home(), Path("/home")]:
        for cookies_file in root.rglob("**/Cookies"):
            if "chrome" in str(cookies_file).lower() or "chromium" in str(cookies_file).lower():
                return cookies_file

    return None


def extract_twitter_cookies(db_path: Path) -> dict:
    """Extract auth_token and ct0 from Chrome cookies database."""
    # Copy database to avoid locking issues
    temp_db = Path("/tmp/cookies_copy.db")
    shutil.copy(db_path, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Query for Twitter cookies
    cursor.execute("""
        SELECT name, value FROM cookies
        WHERE host_key LIKE '%twitter.com' OR host_key LIKE '%x.com'
    """)

    cookies = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    temp_db.unlink()

    return cookies


def main():
    print("[*] Looking for Chrome cookies database...")
    db_path = find_chrome_cookies_db()

    if not db_path:
        print("[!] Could not find Chrome cookies database.", file=sys.stderr)
        print("    Make sure you've opened Chrome and logged into x.com first.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Found cookies at: {db_path}")

    cookies = extract_twitter_cookies(db_path)

    if "auth_token" not in cookies or "ct0" not in cookies:
        print("[!] Missing required cookies (auth_token and/or ct0).", file=sys.stderr)
        print("    Make sure you're logged into x.com in the browser.", file=sys.stderr)
        print(f"    Found cookies: {list(cookies.keys())}", file=sys.stderr)
        sys.exit(1)

    # Build session object
    session = {
        "kind": "cookie",
        "auth_token": cookies["auth_token"],
        "ct0": cookies["ct0"],
    }

    # Add optional fields
    if "twid" in cookies:
        twid = cookies["twid"]
        if "u%3D" in twid:
            session["id"] = twid.split("u%3D")[1].split("&")[0].strip('"')
        elif "u=" in twid:
            session["id"] = twid.split("u=")[1].split("&")[0].strip('"')

    # Try to get username from environment or prompt
    username = os.environ.get("TWITTER_USERNAME", "")
    if username:
        session["username"] = username

    # Append to sessions file
    output = json.dumps(session)

    with open(SESSIONS_FILE, "a") as f:
        f.write(output + "\n")

    print(f"[+] Session appended to {SESSIONS_FILE}")
    print(f"[+] auth_token: {session['auth_token'][:10]}...")
    print(f"[+] ct0: {session['ct0'][:10]}...")
    print("\n[*] Now restart nitter to pick up the new session:")
    print("    docker compose -f docker-compose.prod.yml restart nitter")


if __name__ == "__main__":
    main()
