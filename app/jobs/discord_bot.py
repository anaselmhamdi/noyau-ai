"""
Discord bot runner.

Run with: python -m app.jobs.discord_bot

This starts the Discord bot that handles:
- /subscribe [email] - Subscribe to daily digest DMs
- /unsubscribe - Stop receiving digest DMs
- /status - Check subscription status
"""

import asyncio

from app.core.logging import setup_logging
from app.services.discord_bot import run_bot

if __name__ == "__main__":
    setup_logging()
    asyncio.run(run_bot())
