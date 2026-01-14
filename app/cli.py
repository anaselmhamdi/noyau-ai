"""
NoyauNews CLI - Command line interface for running jobs.

Usage:
    noyau --help              Show all commands
    noyau daily               Run daily digest job
    noyau daily --dry-run     Preview without saving
    noyau hourly              Run hourly ingest job
    noyau video               Generate test video
    noyau test-emails         Send test emails to DEV_EMAIL
"""

import asyncio
from datetime import date
from pathlib import Path

import typer

app = typer.Typer(
    name="noyau",
    help="NoyauNews CLI - Job runner for noyau.news",
    no_args_is_help=True,
)


# --- Step printer helpers ---


def _print_step(step_num: int, total: int, message: str) -> None:
    """Print a step progress message."""
    typer.echo(f"\n[{step_num}/{total}] {message}...")


def _print_success(message: str) -> None:
    """Print a success message."""
    typer.echo(f"  ✅ {message}")


def _print_warning(message: str) -> None:
    """Print a warning message."""
    typer.echo(f"  ⚠️ {message}")


def _print_skipped(message: str) -> None:
    """Print a skipped step message."""
    typer.echo(f"  ⏭️ {message}")


def _print_error(message: str) -> None:
    """Print an error message to stderr."""
    typer.echo(f"❌ {message}", err=True)


async def _upload_to_youtube(
    uploader_cls,
    video_path: Path,
    sample_summary,
    target_platform,
    topic: str,
    get_platform_hashtags,
    create_video_metadata,
) -> None:
    """Handle YouTube upload with proper configuration checks."""
    uploader = uploader_cls()
    if not uploader._is_configured():
        _print_skipped("YouTube not configured")
        return

    hashtags = get_platform_hashtags(target_platform, topic)
    metadata = create_video_metadata(
        headline=sample_summary.headline,
        teaser=sample_summary.teaser,
        topic=topic,
        rank=1,
        citations=[c.model_dump() for c in sample_summary.citations],
    )
    metadata.privacy_status = "unlisted"
    metadata.tags.extend(hashtags)

    upload_result = await uploader.upload_video(video_path, metadata)
    if upload_result:
        _, video_url = upload_result
        _print_success(f"YouTube: {video_url}")


@app.command()
def daily(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without saving to DB"),
):
    """Run the daily digest job (cluster, score, distill, email)."""
    from app.core.logging import setup_logging
    from app.jobs.daily import main

    setup_logging()
    asyncio.run(main(dry_run=dry_run))


@app.command()
def hourly():
    """Run the hourly ingest job (fetch content from all sources)."""
    from app.core.logging import setup_logging
    from app.jobs.hourly import main

    setup_logging()
    asyncio.run(main())


@app.command()
def video(
    headline: str | None = typer.Option(
        None, "--headline", "-h", help="Custom headline for the video"
    ),
    topic: str = typer.Option(
        "dev",
        "--topic",
        "-t",
        help="Topic category for stock footage",
    ),
    platform: str = typer.Option(
        "youtube",
        "--platform",
        "-p",
        help="Target platform: youtube, tiktok, reels, or all",
    ),
    skip_upload: bool = typer.Option(False, "--skip-upload", help="Skip all uploads (local only)"),
    skip_s3: bool = typer.Option(False, "--skip-s3", help="Skip S3 upload"),
    tts_provider: str = typer.Option(
        "openai",
        "--tts",
        help="TTS provider: edge (free), openai (default), or elevenlabs (best quality)",
    ),
):
    """Generate a test video from a sample story."""
    from app.core.logging import setup_logging
    from app.schemas.common import Citation
    from app.schemas.llm import ClusterDistillOutput
    from app.services.storage_service import get_storage_service
    from app.video.background_music import fetch_background_music
    from app.video.compositor import compose_video
    from app.video.orchestrator import (
        VideoConfigLocal,
        VideoFormatConfig,
        VideoStyleConfig,
        YouTubeConfigLocal,
    )
    from app.video.platforms import Platform, get_platform_hashtags, get_platform_spec
    from app.video.script_generator import generate_script
    from app.video.stock_footage import fetch_clips_for_script
    from app.video.tts import generate_srt, synthesize_script
    from app.video.uploader import YouTubeUploader, create_video_metadata

    setup_logging()

    # Parse platform
    try:
        target_platform = Platform(platform)
    except ValueError:
        typer.echo(f"❌ Unknown platform: {platform}", err=True)
        typer.echo("   Valid options: youtube, tiktok, reels, all")
        raise typer.Exit(1)

    # Get platform spec
    spec = get_platform_spec(target_platform)

    # Sample story
    sample_summary = ClusterDistillOutput(
        headline=headline or "Python 3.13 Brings Free-Threading and JIT Compiler",
        teaser="The latest Python release introduces experimental support for running without the GIL and a new JIT compiler.",
        takeaway="Python 3.13 marks a major step toward better multi-core performance with free-threading mode.",
        why_care="If you run CPU-bound Python code, free-threading could significantly improve performance.",
        bullets=[
            "Enable free-threading with --disable-gil flag for true parallelism",
            "JIT compiler shows 2-9% speedups on benchmarks",
        ],
        citations=[
            Citation(url="https://docs.python.org/3.13/whatsnew/3.13.html", label="Python Docs"),
        ],
        confidence="high",
    )

    async def run():
        typer.echo(f"\n🎬 Generating video for {spec.name}")
        typer.echo(f"   Headline: {sample_summary.headline[:50]}...")
        typer.echo(f"   Format: {spec.width}x{spec.height} @ {spec.fps}fps")

        output_dir = Path("output/videos/test")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Generate script
        _print_step(1, 6, "Generating script")
        script_result = await generate_script(sample_summary, topic, rank=1)

        if not script_result:
            _print_error("Script generation failed. Check OPENAI_API_KEY.")
            raise typer.Exit(1)

        script = script_result.script
        _print_success(f"Script generated ({script_result.total_tokens} tokens)")

        # Step 2: Synthesize audio
        _print_step(2, 6, f"Synthesizing audio ({tts_provider})")
        audio_path = output_dir / "narration.mp3"
        tts_result = await synthesize_script(script, audio_path, provider=tts_provider)

        if not tts_result:
            _print_error("Audio synthesis failed.")
            raise typer.Exit(1)

        duration = tts_result.duration
        subtitles = tts_result.subtitles

        # Save SRT file
        srt_path = output_dir / "subtitles.srt"
        generate_srt(subtitles, srt_path)

        _print_success(f"Audio: {duration:.1f}s ({len(subtitles)} subtitle segments)")

        # Step 3: Fetch stock footage
        _print_step(3, 6, "Fetching stock footage")
        clips_dir = output_dir / "clips"
        clips = await fetch_clips_for_script(
            keywords=script.visual_keywords,
            duration_needed=duration,
            output_dir=clips_dir,
        )
        if clips:
            _print_success(f"{len(clips)} clips fetched")
        else:
            _print_warning("No clips (using solid bg)")

        # Step 3.5: Fetch background music
        typer.echo("\n[3.5/6] Fetching background music...")
        background_music = await fetch_background_music(
            topic=topic,
            duration_needed=duration,
            output_dir=output_dir,
        )
        if background_music:
            _print_success("Background music ready")
        else:
            _print_warning("No music (voice only)")

        # Step 4: Compose video
        _print_step(4, 6, "Composing video")
        video_path = output_dir / f"test_video_{platform}.mp4"

        config = VideoConfigLocal(
            enabled=True,
            format=VideoFormatConfig(
                width=spec.width,
                height=spec.height,
                fps=spec.fps,
                max_duration=spec.max_duration,
            ),
            style=VideoStyleConfig(),
            youtube=YouTubeConfigLocal(),
        )

        result = compose_video(
            script=script,
            audio_path=audio_path,
            clips=clips,
            output_path=video_path,
            config=config,  # type: ignore[arg-type]
            subtitles=subtitles,
            background_music_path=background_music,
        )

        if not result:
            _print_error("Video composition failed. Is FFmpeg installed?")
            raise typer.Exit(1)

        _print_success(f"Video: {result.duration_seconds:.1f}s")

        # Step 5: S3 upload
        _print_step(5, 6, "S3 upload")
        if skip_s3 or skip_upload:
            _print_skipped("S3 upload skipped")
        else:
            storage = get_storage_service()
            if not storage.is_configured():
                _print_skipped("S3 not configured")
            else:
                s3_url = await storage.upload_video(
                    video_path=video_path,
                    issue_date=date.today().isoformat(),
                    rank=1,
                    filename=f"test_video_{platform}.mp4",
                )
                if s3_url:
                    _print_success(f"S3: {s3_url}")

        # Step 6: Platform upload
        _print_step(6, 6, "Platform upload")
        if skip_upload:
            _print_skipped("Platform upload skipped")
        elif target_platform == Platform.YOUTUBE_SHORTS:
            await _upload_to_youtube(
                uploader_cls=YouTubeUploader,
                video_path=video_path,
                sample_summary=sample_summary,
                target_platform=target_platform,
                topic=topic,
                get_platform_hashtags=get_platform_hashtags,
                create_video_metadata=create_video_metadata,
            )
        elif target_platform == Platform.TIKTOK:
            _print_skipped("TikTok API not yet implemented")
            typer.echo("  📁 Video ready for manual upload")
        elif target_platform == Platform.INSTAGRAM_REELS:
            _print_skipped("Instagram API not yet implemented")
            typer.echo("  📁 Video ready for manual upload")
        else:
            _print_skipped("Platform upload skipped")

        typer.echo(f"\n{'=' * 50}")
        typer.echo(f"🎬 Done! Video saved to: {video_path}")
        typer.echo(f"{'=' * 50}\n")

    asyncio.run(run())


@app.command()
def test_emails():
    """Send test emails (magic link + daily digest) to DEV_EMAIL."""
    from app.core.logging import setup_logging
    from app.services.email_service import send_test_emails

    setup_logging()

    typer.echo("\n📧 Sending test emails...")

    results = asyncio.run(send_test_emails())

    if "error" in results:
        _print_error(str(results["error"]))
        raise typer.Exit(1)

    if results.get("magic_link"):
        _print_success("Magic link email sent")
    else:
        _print_error("Magic link email failed")

    if results.get("daily_digest"):
        _print_success("Daily digest email sent")
    else:
        _print_error("Daily digest email failed")

    typer.echo("")


@app.command()
def migrate():
    """Run database migrations (alembic upgrade head)."""
    import subprocess

    result = subprocess.run(["alembic", "upgrade", "head"], check=False)
    raise typer.Exit(result.returncode)


@app.command()
def serve(
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable hot reload"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to run on"),
):
    """Start the API server."""
    import subprocess

    cmd = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port)]
    if reload:
        cmd.append("--reload")

    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    app()
