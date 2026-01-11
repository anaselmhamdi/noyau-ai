"""
Individual ingestion source CLI for debugging.

Run with: python -m app.jobs.ingest <command> [options]

Examples:
    python -m app.jobs.ingest fetch nitter --dry-run --verbose
    python -m app.jobs.ingest fetch rss --limit 5
    python -m app.jobs.ingest refresh-tokens
    python -m app.jobs.ingest token-status
"""

import argparse
import asyncio
from collections.abc import Callable

from app.config import AppConfig, get_config
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.ingest.base import BaseFetcher
from app.ingest.devto import create_devto_fetcher
from app.ingest.nitter import create_nitter_fetcher
from app.ingest.nitter_auth import NitterTokenManager
from app.ingest.orchestrator import create_metrics_snapshot, upsert_content_item
from app.ingest.reddit import create_reddit_fetcher
from app.ingest.rss import create_rss_fetchers
from app.ingest.youtube import create_youtube_fetcher

logger = get_logger(__name__)

# Map source names to their factory functions
FETCHER_FACTORIES: dict[str, Callable[[AppConfig], BaseFetcher | list[BaseFetcher] | None]] = {
    "nitter": create_nitter_fetcher,
    "rss": create_rss_fetchers,
    "reddit": create_reddit_fetcher,
    "devto": create_devto_fetcher,
    "youtube": create_youtube_fetcher,
}


def get_fetchers(source: str, config: AppConfig) -> list[BaseFetcher]:
    """Get fetcher(s) for the specified source."""
    factory = FETCHER_FACTORIES.get(source)
    if not factory:
        raise ValueError(f"Unknown source: {source}")

    result = factory(config)
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [result]


async def run_fetcher(
    source: str,
    dry_run: bool = False,
    verbose: bool = False,
    limit: int = 0,
) -> dict:
    """
    Run a specific fetcher and optionally persist results.

    Args:
        source: Name of the source to fetch (nitter, rss, reddit, devto, youtube)
        dry_run: If True, don't write to database
        verbose: If True, print each item fetched
        limit: Maximum number of items to fetch (0 = unlimited)

    Returns:
        Stats dict with counts
    """
    config = get_config()
    fetchers = get_fetchers(source, config)

    if not fetchers:
        print(f"No fetcher configured for source: {source}")
        return {"items": 0, "errors": 0}

    stats = {
        "items": 0,
        "new_items": 0,
        "existing_items": 0,
        "errors": 0,
    }

    print(f"Running {source} fetcher(s)... (dry_run={dry_run})")
    print("-" * 60)

    db_session = None
    if not dry_run:
        db_session = AsyncSessionLocal()

    try:
        for fetcher in fetchers:
            print(f"\nFetcher: {fetcher.source_name}")

            try:
                async for item in fetcher.fetch():
                    stats["items"] += 1

                    if verbose:
                        print(f"\n[{stats['items']}] {item.title[:80]}")
                        print(f"    URL: {item.url}")
                        print(f"    Author: {item.author}")
                        print(f"    Published: {item.published_at}")
                        if item.metrics:
                            print(f"    Metrics: {item.metrics}")

                    if not dry_run and db_session:
                        try:
                            content_item = await upsert_content_item(db_session, item)
                            await create_metrics_snapshot(db_session, content_item.id, item.metrics)
                            # Check if new (created in last minute)
                            from app.core.datetime_utils import utc_now

                            if (
                                content_item.fetched_at
                                and (utc_now() - content_item.fetched_at).seconds < 60
                            ):
                                stats["new_items"] += 1
                            else:
                                stats["existing_items"] += 1
                        except Exception as e:
                            print(f"    ERROR persisting: {e}")
                            stats["errors"] += 1

                    if limit > 0 and stats["items"] >= limit:
                        print(f"\nReached limit of {limit} items")
                        break

            except Exception as e:
                print(f"ERROR in fetcher {fetcher.source_name}: {e}")
                import traceback

                traceback.print_exc()
                stats["errors"] += 1

            if limit > 0 and stats["items"] >= limit:
                break

        if not dry_run and db_session:
            await db_session.commit()

    finally:
        if db_session:
            await db_session.close()

    print("\n" + "-" * 60)
    print(f"Results: {stats['items']} items fetched, {stats['errors']} errors")
    if not dry_run:
        print(f"  New: {stats['new_items']}, Existing: {stats['existing_items']}")

    return stats


def refresh_tokens() -> bool:
    """Refresh Nitter/Twitter session tokens."""
    print("Refreshing Twitter session tokens...")
    print("-" * 60)

    manager = NitterTokenManager()

    # Show current status
    sessions = manager.get_sessions()
    print(f"Current sessions: {len(sessions)}")

    # Attempt refresh
    success = manager.refresh_token()

    if success:
        new_sessions = manager.get_sessions()
        print(f"\nSuccess! Sessions: {len(new_sessions)}")
        return True
    else:
        print("\nFailed to refresh tokens.")
        print("Make sure TWITTER_USERNAME and TWITTER_PASSWORD are set in .env")
        print("For 2FA accounts, also set TWITTER_TOTP_SECRET")
        return False


async def check_token_status() -> None:
    """Check the status of Nitter tokens."""
    print("Checking Nitter token status...")
    print("-" * 60)

    manager = NitterTokenManager()

    # Show sessions
    sessions = manager.get_sessions()
    print(f"Sessions in file: {len(sessions)}")

    for i, session in enumerate(sessions):
        username = session.get("username", "unknown")
        print(f"  [{i + 1}] @{username}")

    if not sessions:
        print("  (none)")
        print("\nRun 'python -m app.jobs.ingest refresh-tokens' to create tokens")
        return

    # Check health
    config = get_config()
    nitter_url = None
    for instance in config.nitter.instances:
        if any(p in instance for p in ("localhost", "127.0.0.1", "nitter:")):
            nitter_url = f"http://{instance}"
            break

    if nitter_url:
        print(f"\nChecking health against {nitter_url}...")
        is_healthy = await manager.check_token_health(nitter_url)
        if is_healthy:
            print("Status: HEALTHY")
        else:
            print("Status: UNHEALTHY (tokens may be expired)")
            print("Run 'python -m app.jobs.ingest refresh-tokens' to refresh")
    else:
        print("\nNo self-hosted Nitter instance configured for health check")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ingestion debugging and token management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Fetch command
    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch from a specific source",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m app.jobs.ingest fetch nitter --dry-run --verbose
    python -m app.jobs.ingest fetch rss --limit 5
        """,
    )
    fetch_parser.add_argument(
        "source",
        choices=list(FETCHER_FACTORIES.keys()),
        help="Source to fetch from",
    )
    fetch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and display without writing to database",
    )
    fetch_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print details for each fetched item",
    )
    fetch_parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=0,
        help="Maximum number of items to fetch (0 = unlimited)",
    )

    # Token commands
    subparsers.add_parser(
        "refresh-tokens",
        help="Refresh Twitter session tokens for Nitter",
    )
    subparsers.add_parser(
        "token-status",
        help="Check the status of Nitter tokens",
    )

    args = parser.parse_args()

    setup_logging()

    if args.command == "fetch":
        asyncio.run(run_fetcher(args.source, args.dry_run, args.verbose, args.limit))
    elif args.command == "refresh-tokens":
        refresh_tokens()
    elif args.command == "token-status":
        asyncio.run(check_token_status())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
