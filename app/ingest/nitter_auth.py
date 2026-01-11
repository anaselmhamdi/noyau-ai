"""
Twitter/Nitter session token management.

Handles:
- Checking if tokens are valid
- Refreshing expired tokens using Twitter authentication
- Managing the sessions.jsonl file
"""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SESSIONS_FILE = Path("nitter/sessions.jsonl")
NITTER_SCRIPTS_DIR = Path("nitter/scripts")
TOKEN_CHECK_CACHE_FILE = Path("nitter/.token_check_cache")


class NitterTokenManager:
    """Manages Twitter session tokens for Nitter."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.sessions_file = SESSIONS_FILE

    def get_sessions(self) -> list[dict]:
        """Load current sessions from file."""
        if not self.sessions_file.exists():
            return []

        sessions = []
        with open(self.sessions_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        sessions.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in sessions file: {line[:50]}...")
        return sessions

    def save_session(self, session: dict) -> None:
        """Append a new session to the file."""
        self.sessions_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sessions_file, "a") as f:
            f.write(json.dumps(session) + "\n")
        logger.info("nitter_session_saved", username=session.get("username"))

    def clear_sessions(self) -> None:
        """Clear all sessions."""
        if self.sessions_file.exists():
            self.sessions_file.unlink()
        logger.info("nitter_sessions_cleared")

    async def check_token_health(self, nitter_url: str = "http://localhost:8080") -> bool:
        """
        Check if the current tokens are working by testing the Nitter instance.

        Returns True if tokens are healthy, False if refresh is needed.
        """
        # Check cache first (avoid hammering Nitter)
        if self._is_check_cached():
            return True

        test_username = "elonmusk"  # Use a popular account for testing
        test_url = f"{nitter_url}/{test_username}/rss"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(test_url)

                if response.status_code == 200:
                    content = response.text
                    # Check if we got actual RSS content (not an error page)
                    if "<rss" in content or "<feed" in content:
                        self._cache_check_result()
                        logger.debug("nitter_tokens_healthy")
                        return True

                logger.warning(
                    "nitter_tokens_unhealthy",
                    status=response.status_code,
                    content_preview=response.text[:200],
                )
                return False

        except httpx.RequestError as e:
            logger.warning("nitter_health_check_failed", error=str(e))
            return False

    def _is_check_cached(self, max_age_minutes: int = 30) -> bool:
        """Check if we have a recent successful health check."""
        if not TOKEN_CHECK_CACHE_FILE.exists():
            return False

        try:
            mtime = datetime.fromtimestamp(TOKEN_CHECK_CACHE_FILE.stat().st_mtime, tz=UTC)
            age = datetime.now(UTC) - mtime
            return age < timedelta(minutes=max_age_minutes)
        except Exception:
            return False

    def _cache_check_result(self) -> None:
        """Cache a successful health check."""
        TOKEN_CHECK_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CHECK_CACHE_FILE.touch()

    def refresh_token(self) -> bool:
        """
        Refresh the Twitter session token using stored credentials.

        Uses the Nitter authentication scripts if available,
        otherwise falls back to direct HTTP authentication.

        Returns True if refresh was successful.
        """
        username = self.settings.twitter_username
        password = self.settings.twitter_password
        totp_secret = self.settings.twitter_totp_secret

        if not username or not password:
            logger.error("nitter_refresh_failed: No Twitter credentials configured")
            return False

        logger.info("nitter_token_refresh_starting", username=username)

        # Try using Nitter's auth scripts first (most reliable)
        if self._refresh_via_nitter_scripts(username, password, totp_secret):
            return True

        # Fall back to direct HTTP auth
        return self._refresh_via_http(username, password, totp_secret)

    def _refresh_via_nitter_scripts(
        self, username: str, password: str, totp_secret: str | None
    ) -> bool:
        """Refresh token using Nitter's Python scripts."""
        # Try curl script first (works headless), fall back to browser
        for script_name in ["create_session_curl.py", "create_session_browser.py"]:
            script_path = NITTER_SCRIPTS_DIR / script_name
            if script_path.exists():
                break
        else:
            logger.debug("nitter_scripts_not_found", path=str(NITTER_SCRIPTS_DIR))
            return False

        cmd = [
            sys.executable,
            str(script_path),
            username,
            password,
        ]
        if totp_secret:
            cmd.append(totp_secret)
        cmd.extend(["--append", str(self.sessions_file)])
        # Add headless flag for browser script (required for VM deployment)
        if "browser" in script_path.name:
            cmd.append("--headless")

        try:
            logger.info("nitter_script_running", script=script_path.name, username=username)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # Browser script takes longer
            )
            if result.returncode == 0:
                logger.info("nitter_token_refreshed_via_script", username=username)
                self._invalidate_check_cache()
                return True
            else:
                logger.warning(
                    "nitter_script_failed",
                    script=script_path.name,
                    returncode=result.returncode,
                    stdout=result.stdout[:500] if result.stdout else None,
                    stderr=result.stderr[:500] if result.stderr else None,
                )
                return False
        except subprocess.TimeoutExpired:
            logger.error("nitter_script_timeout", script=script_path.name)
            return False
        except Exception as e:
            logger.error("nitter_script_error", script=script_path.name, error=str(e))
            return False

    def _refresh_via_http(self, username: str, password: str, totp_secret: str | None) -> bool:
        """
        Refresh token via direct HTTP authentication.

        Note: This is less reliable than the Nitter scripts because Twitter
        actively blocks non-browser clients. Only use as fallback.
        """
        # Twitter's auth flow is complex and changes frequently.
        # For now, log a warning and suggest using the scripts.
        logger.warning(
            "nitter_http_auth_not_implemented",
            hint="Download Nitter scripts to nitter/scripts/ for token refresh",
        )
        return False

    def _invalidate_check_cache(self) -> None:
        """Invalidate the health check cache after token refresh."""
        if TOKEN_CHECK_CACHE_FILE.exists():
            TOKEN_CHECK_CACHE_FILE.unlink()


async def ensure_valid_tokens(nitter_url: str = "http://localhost:8080") -> bool:
    """
    Ensure we have valid Nitter tokens, refreshing if necessary.

    Returns True if tokens are valid (or were successfully refreshed).
    """
    manager = NitterTokenManager()

    # Check if tokens exist
    sessions = manager.get_sessions()
    if not sessions:
        logger.info("nitter_no_sessions_found, attempting refresh")
        return manager.refresh_token()

    # Check if tokens are healthy
    if await manager.check_token_health(nitter_url):
        return True

    # Tokens are stale, try to refresh
    logger.info("nitter_tokens_stale, attempting refresh")
    return manager.refresh_token()
