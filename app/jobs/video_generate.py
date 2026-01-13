"""
Video generation job for creating videos from existing issue data.

Run with: python -m app.jobs.video_generate
Options:
  --date DATE         Issue date (default: today)
  --count N           Number of videos to generate (default: from config, typically 3)
  --output-dir PATH   Output directory for videos (default: from config)
  --dry-run           Preview without generating videos

Examples:
  python -m app.jobs.video_generate
  python -m app.jobs.video_generate --date 2026-01-13
  python -m app.jobs.video_generate --output-dir /tmp/videos
"""

import argparse
import asyncio
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.models.cluster import Cluster, ClusterSummary
from app.schemas.common import Citation
from app.schemas.llm import ClusterDistillOutput
from app.video.orchestrator import generate_single_video, get_video_config

logger = get_logger(__name__)


def summary_to_distill_output(summary: ClusterSummary) -> ClusterDistillOutput:
    """Convert a ClusterSummary to ClusterDistillOutput for video generation."""
    citations = [
        Citation(url=c.get("url", ""), label=c.get("label", "Source"))
        for c in (summary.citations_json or [])
    ]
    # Ensure at least one citation
    if not citations:
        citations = [Citation(url="https://noyau.news", label="Noyau News")]

    bullets = summary.bullets_json or []
    # Ensure exactly 2 bullets
    if len(bullets) < 2:
        bullets = bullets + ["See full story for details."] * (2 - len(bullets))
    elif len(bullets) > 2:
        bullets = bullets[:2]

    return ClusterDistillOutput(
        headline=summary.headline,
        teaser=summary.teaser,
        takeaway=summary.takeaway,
        why_care=summary.why_care,
        bullets=bullets,
        citations=citations,
        confidence=summary.confidence.value,
    )


async def get_clusters_for_date(db: AsyncSession, issue_date: date) -> list[Cluster]:
    """Query clusters with summaries for the given date."""
    stmt = (
        select(Cluster)
        .options(selectinload(Cluster.summary))
        .where(Cluster.issue_date == issue_date)
        .order_by(Cluster.cluster_score.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def determine_topic(cluster: Cluster) -> str:
    """Determine video topic from cluster."""
    if cluster.dominant_topic:
        topic = cluster.dominant_topic.value
        # Video module uses specific topics
        if topic in ("security",):
            return "security"
        elif topic in ("oss",):
            return "oss"
        elif topic in ("macro", "deepdive"):
            return "ai"  # or cloud
    return "general"


async def main(
    issue_date: date | None = None,
    count: int | None = None,
    output_dir: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run the video generation job."""
    setup_logging()

    # Default to today
    if issue_date is None:
        issue_date = date.today()

    video_config = get_video_config()

    if not video_config.enabled:
        print("Video generation is disabled in config")
        return

    # Use config count if not specified
    if count is None:
        count = video_config.count

    # Use provided output_dir or fall back to config
    output_path = Path(output_dir) if output_dir else Path(video_config.output_dir)

    logger.bind(
        issue_date=str(issue_date),
        count=count,
        output_dir=str(output_path),
        dry_run=dry_run,
    ).info("video_generate_started")

    async with AsyncSessionLocal() as db:
        # Fetch clusters with summaries
        clusters = await get_clusters_for_date(db, issue_date)

        if not clusters:
            print(f"No clusters found for {issue_date}")
            logger.bind(issue_date=str(issue_date)).warning("no_clusters_found")
            return

        # Filter to clusters with summaries
        clusters_with_summaries = [c for c in clusters if c.summary]

        if not clusters_with_summaries:
            print(f"No cluster summaries found for {issue_date}")
            logger.bind(issue_date=str(issue_date)).warning("no_summaries_found")
            return

        print(f"Found {len(clusters_with_summaries)} clusters with summaries")
        print(f"Output directory: {output_path}")

        # Take top N for video generation
        top_clusters = clusters_with_summaries[:count]
        print(f"Generating videos for top {len(top_clusters)} stories")
        print("-" * 40)

        results = []

        for rank, cluster in enumerate(top_clusters, start=1):
            summary = cluster.summary
            print(f"\n[{rank}] {summary.headline[:60]}...")

            if dry_run:
                print("    (dry run - skipping generation)")
                continue

            # Convert to ClusterDistillOutput
            distill_output = summary_to_distill_output(summary)

            # Determine topic
            topic = determine_topic(cluster)

            # Generate video
            result = await generate_single_video(
                summary=distill_output,
                topic=topic,
                rank=rank,
                issue_date=issue_date,
                cluster_id=str(cluster.id),
                output_dir=output_path,
                config=video_config,
                db=db,
                dry_run=False,
            )

            if result:
                results.append(result)
                print(f"    ✓ Generated: {result.video_path}")
                if result.youtube_url:
                    print(f"    ✓ YouTube: {result.youtube_url}")
                if result.s3_url:
                    print(f"    ✓ S3: {result.s3_url}")
            else:
                print("    ✗ Generation failed")

        # Summary
        print("\n" + "=" * 40)
        if dry_run:
            print(f"Dry run complete. Would generate {len(top_clusters)} videos.")
        else:
            print(f"Generated {len(results)}/{len(top_clusters)} videos")

            if results:
                print("\nGenerated videos:")
                for r in results:
                    print(f"  - {r.video_path}")
                    if r.s3_url:
                        print(f"    S3: {r.s3_url}")

        logger.bind(
            issue_date=str(issue_date),
            total=len(top_clusters),
            successful=len(results),
        ).info("video_generate_completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate videos from existing issue data")
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Issue date (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of videos to generate. Default: from config",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for videos. Default: from config",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without generating videos",
    )
    args = parser.parse_args()

    asyncio.run(
        main(
            issue_date=args.date,
            count=args.count,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
    )
