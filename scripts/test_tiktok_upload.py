#!/usr/bin/env python3
"""Test TikTok upload with a specific S3 URL."""

import asyncio
import sys
from datetime import date

# Add app to path
sys.path.insert(0, "/app")

from app.services.tiktok_service import send_tiktok_videos


async def main():
    # Default to today's video URL - override with arg
    s3_url = sys.argv[1] if len(sys.argv) > 1 else None

    if not s3_url:
        print("Usage: python test_tiktok_upload.py <s3_url>")
        print(
            "Example: python test_tiktok_upload.py https://pub-xxx.r2.dev/videos/2026-01-14/rank_0/noyau_digest.mp4"
        )
        sys.exit(1)

    print(f"Testing TikTok upload with URL: {s3_url}")

    # Create mock video and item data
    videos = [{"s3_url": s3_url}]
    items = [
        {
            "headline": "Test Video Upload",
            "teaser": "Testing TikTok upload functionality",
        }
    ]

    result = await send_tiktok_videos(
        issue_date=date.today(),
        videos=videos,
        items=items,
    )

    print(f"\nResult: {result}")
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")

    for i, r in enumerate(result.results):
        print(f"  Video {i + 1}: success={r.success}, error={r.error}")


if __name__ == "__main__":
    asyncio.run(main())
