#!/usr/bin/env python3
"""
Manually add a Twitter session from cookies.

Usage:
  python3 add_session.py AUTH_TOKEN CT0 [--username NAME]

Example:
  python3 add_session.py "abc123..." "def456..." --username NoyauNews
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Add Twitter session from cookies")
    parser.add_argument("auth_token", help="auth_token cookie value")
    parser.add_argument("ct0", help="ct0 cookie value")
    parser.add_argument("--username", "-u", help="Twitter username", default="")
    parser.add_argument(
        "--output",
        "-o",
        help="Output file",
        default=str(Path(__file__).parent.parent / "sessions.jsonl"),
    )
    args = parser.parse_args()

    session = {
        "kind": "cookie",
        "auth_token": args.auth_token,
        "ct0": args.ct0,
    }

    if args.username:
        session["username"] = args.username

    output = json.dumps(session)

    with open(args.output, "a") as f:
        f.write(output + "\n")

    print(f"Session added to {args.output}")
    print(f"auth_token: {args.auth_token[:15]}...")
    print(f"ct0: {args.ct0[:15]}...")


if __name__ == "__main__":
    main()
