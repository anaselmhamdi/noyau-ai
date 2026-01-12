#!/usr/bin/env python3
"""
Requirements:
  pip install nodriver pyotp

Usage:
  python3 create_session_browser.py <username> <password> [totp_seed] [--append sessions.jsonl] [--headless]

Examples:
  python3 create_session_browser.py myusername mypassword TOTP_SECRET --append sessions.jsonl
"""

import asyncio
import json
import os
import sys

import nodriver as uc
import pyotp


async def login_and_get_cookies(username, password, totp_seed=None, headless=False):
    """Authenticate with X.com and extract session cookies"""
    browser = await uc.start(headless=headless)
    tab = await browser.get("https://x.com/i/flow/login")

    try:
        # Wait for page to load
        await asyncio.sleep(3)

        # Enter username
        print("[*] Entering username...", file=sys.stderr)
        username_input = await tab.find('input[autocomplete="username"]', timeout=15)
        await username_input.send_keys(username)
        await asyncio.sleep(0.5)
        await username_input.send_keys("\n")
        await asyncio.sleep(3)

        # Check for intermediate verification (email/phone confirmation)
        page_content = await tab.get_content()

        # Twitter sometimes asks to verify email or phone
        if (
            "Enter your phone number or email" in page_content
            or "phone number or username" in page_content.lower()
        ):
            print("[*] Email/phone verification required, entering username...", file=sys.stderr)
            verify_input = await tab.find('input[data-testid="ocfEnterTextTextInput"]', timeout=10)
            if verify_input:
                await verify_input.send_keys(username + "\n")
                await asyncio.sleep(2)

        # Look for password field with multiple selectors
        print("[*] Looking for password field...", file=sys.stderr)
        password_input = None

        selectors = [
            'input[autocomplete="current-password"]',
            'input[name="password"]',
            'input[type="password"]',
        ]

        for selector in selectors:
            try:
                password_input = await tab.find(selector, timeout=5)
                if password_input:
                    print(f"[*] Found password field with: {selector}", file=sys.stderr)
                    break
            except Exception:
                continue

        if not password_input:
            # Debug: print what's on the page
            print("[!] Could not find password field. Page content:", file=sys.stderr)
            # Get text content for debugging
            try:
                title = await tab.find("h1", timeout=2)
                if title:
                    print(
                        f"    Page title: {await title.get_property('textContent')}",
                        file=sys.stderr,
                    )
            except Exception:
                pass
            raise Exception("Password field not found - Twitter may be showing a challenge")

        print("[*] Entering password...", file=sys.stderr)
        await password_input.send_keys(password)
        await asyncio.sleep(0.5)
        await password_input.send_keys("\n")
        await asyncio.sleep(3)

        # Handle 2FA if needed
        page_content = await tab.get_content()
        if (
            "verification code" in page_content.lower()
            or "enter code" in page_content.lower()
            or "authentication code" in page_content.lower()
        ):
            if not totp_seed:
                raise Exception("2FA required but no TOTP seed provided")

            print("[*] 2FA detected, entering code...", file=sys.stderr)
            totp_code = pyotp.TOTP(totp_seed).now()

            code_input = None
            code_selectors = [
                'input[data-testid="ocfEnterTextTextInput"]',
                'input[autocomplete="one-time-code"]',
                'input[type="text"]',
            ]

            for selector in code_selectors:
                try:
                    code_input = await tab.find(selector, timeout=5)
                    if code_input:
                        break
                except Exception:
                    continue

            if code_input:
                await code_input.send_keys(totp_code + "\n")
                await asyncio.sleep(3)
            else:
                raise Exception("Could not find 2FA input field")

        # Get cookies
        print("[*] Retrieving cookies...", file=sys.stderr)
        for attempt in range(30):  # 30 second timeout
            cookies = await browser.cookies.get_all()
            cookies_dict = {cookie.name: cookie.value for cookie in cookies}

            if "auth_token" in cookies_dict and "ct0" in cookies_dict:
                print("[*] Found auth cookies!", file=sys.stderr)

                # Extract ID from twid cookie
                user_id = None
                if "twid" in cookies_dict:
                    twid = cookies_dict["twid"]
                    if "u%3D" in twid:
                        user_id = twid.split("u%3D")[1].split("&")[0].strip('"')
                    elif "u=" in twid:
                        user_id = twid.split("u=")[1].split("&")[0].strip('"')

                cookies_dict["username"] = username
                if user_id:
                    cookies_dict["id"] = user_id

                return cookies_dict

            if attempt % 5 == 0:
                print(f"[*] Waiting for cookies... ({attempt}/30)", file=sys.stderr)
            await asyncio.sleep(1)

        raise Exception("Timeout waiting for auth cookies")

    finally:
        browser.stop()


async def main():
    if len(sys.argv) < 3:
        print(
            "Usage: python3 create_session_browser.py username password [totp_seed] [--append file.jsonl] [--headless]"
        )
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    totp_seed = None
    append_file = None
    headless = False

    # Parse optional arguments
    i = 3
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--append":
            if i + 1 < len(sys.argv):
                append_file = sys.argv[i + 1]
                i += 2
            else:
                print("[!] Error: --append requires a filename", file=sys.stderr)
                sys.exit(1)
        elif arg == "--headless":
            headless = True
            i += 1
        elif not arg.startswith("--"):
            if totp_seed is None:
                totp_seed = arg
            i += 1
        else:
            print(f"[!] Warning: Unknown argument: {arg}", file=sys.stderr)
            i += 1

    try:
        cookies = await login_and_get_cookies(username, password, totp_seed, headless)
        session = {
            "kind": "cookie",
            "username": cookies["username"],
            "id": cookies.get("id"),
            "auth_token": cookies["auth_token"],
            "ct0": cookies["ct0"],
        }
        output = json.dumps(session)

        if append_file:
            with open(append_file, "a") as f:
                f.write(output + "\n")
            print(f"✓ Session appended to {append_file}", file=sys.stderr)
        else:
            print(output)

        os._exit(0)

    except Exception as error:
        print(f"[!] Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
