"""iTunes-compatible RSS feed generation for podcasts."""

from datetime import date, datetime
from email.utils import format_datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from app.core.logging import get_logger

logger = get_logger(__name__)

# iTunes namespace
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"


def _format_duration(seconds: float) -> str:
    """Format duration as HH:MM:SS or MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_rfc2822(dt: datetime) -> str:
    """Format datetime as RFC 2822 for RSS pubDate."""
    return format_datetime(dt)


def generate_podcast_rss(
    episodes: list[dict],
    config: dict,
    output_path: Path | None = None,
) -> str:
    """
    Generate an iTunes-compatible podcast RSS feed.

    Args:
        episodes: List of episode dicts with keys:
            - issue_date: date
            - episode_number: int
            - audio_url: str (public S3 URL)
            - duration_seconds: float
            - title: str (optional, defaults to "Episode N: {date}")
            - description: str (optional)
            - published_at: datetime (optional, defaults to issue_date)
        config: Podcast config dict with keys:
            - title: str
            - description: str
            - author: str
            - email: str
            - website_url: str
            - feed_url: str
            - artwork_url: str
            - category: str
            - subcategory: str (optional)
            - language: str (default: en-us)
            - explicit: bool (default: False)
        output_path: Optional path to write the RSS file

    Returns:
        RSS XML as string
    """
    # Create root element with namespaces
    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:itunes": ITUNES_NS,
            "xmlns:atom": ATOM_NS,
        },
    )

    channel = SubElement(rss, "channel")

    # Required channel elements
    SubElement(channel, "title").text = config["title"]
    SubElement(channel, "link").text = config["website_url"]
    SubElement(channel, "description").text = config["description"]
    SubElement(channel, "language").text = config.get("language", "en-us")

    # Atom self-link (required for some podcast directories)
    SubElement(
        channel,
        f"{{{ATOM_NS}}}link",
        {
            "href": config["feed_url"],
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    # iTunes-specific channel elements
    SubElement(channel, f"{{{ITUNES_NS}}}author").text = config["author"]
    SubElement(channel, f"{{{ITUNES_NS}}}owner")
    owner = channel.find(f"{{{ITUNES_NS}}}owner")
    if owner is not None:
        SubElement(owner, f"{{{ITUNES_NS}}}name").text = config["author"]
        SubElement(owner, f"{{{ITUNES_NS}}}email").text = config.get("email", "hello@noyau.news")

    SubElement(
        channel,
        f"{{{ITUNES_NS}}}image",
        {
            "href": config["artwork_url"],
        },
    )

    # Category
    category = SubElement(
        channel,
        f"{{{ITUNES_NS}}}category",
        {
            "text": config.get("category", "Technology"),
        },
    )
    if config.get("subcategory"):
        SubElement(
            category,
            f"{{{ITUNES_NS}}}category",
            {
                "text": config["subcategory"],
            },
        )

    SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = (
        "true" if config.get("explicit", False) else "false"
    )
    SubElement(channel, f"{{{ITUNES_NS}}}type").text = "episodic"

    # Episodes (most recent first)
    sorted_episodes = sorted(episodes, key=lambda e: e["issue_date"], reverse=True)

    for ep in sorted_episodes:
        item = SubElement(channel, "item")

        # Episode title
        issue_date: date = ep["issue_date"]
        episode_num = ep.get("episode_number", 1)
        default_title = f"Episode {episode_num}: {issue_date.strftime('%B %d, %Y')}"
        SubElement(item, "title").text = ep.get("title", default_title)

        # Description
        default_desc = f"Your daily tech briefing for {issue_date.strftime('%B %d, %Y')}."
        SubElement(item, "description").text = ep.get("description", default_desc)

        # Enclosure (the actual audio file)
        audio_url = ep["audio_url"]
        # Estimate file size if not provided (5MB per 8 minutes is typical)
        file_size = ep.get("file_size", int(ep["duration_seconds"] * 10000))
        SubElement(
            item,
            "enclosure",
            {
                "url": audio_url,
                "length": str(file_size),
                "type": "audio/mpeg",
            },
        )

        # GUID (unique identifier)
        guid = f"{config['website_url']}/podcast/{issue_date.isoformat()}"
        SubElement(item, "guid", {"isPermaLink": "false"}).text = guid

        # Publication date
        published_at = ep.get("published_at")
        if not published_at:
            published_at = datetime.combine(issue_date, datetime.min.time())
        SubElement(item, "pubDate").text = _format_rfc2822(published_at)

        # iTunes-specific item elements
        SubElement(item, f"{{{ITUNES_NS}}}duration").text = _format_duration(ep["duration_seconds"])
        SubElement(item, f"{{{ITUNES_NS}}}episode").text = str(episode_num)
        SubElement(item, f"{{{ITUNES_NS}}}episodeType").text = "full"
        SubElement(item, f"{{{ITUNES_NS}}}explicit").text = "false"

        # Link to web page for this episode
        episode_link = f"{config['website_url']}/daily/{issue_date.isoformat()}"
        SubElement(item, "link").text = episode_link

    # Generate XML string
    xml_str = tostring(rss, encoding="unicode", method="xml")

    # Add XML declaration
    xml_output = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    # Write to file if path provided
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xml_output, encoding="utf-8")
        logger.bind(
            path=str(output_path),
            episode_count=len(episodes),
        ).info("podcast_rss_feed_generated")

    return xml_output


def get_default_feed_config() -> dict:
    """Get default podcast feed configuration."""
    return {
        "title": "Noyau Daily Tech Digest",
        "description": (
            "Your daily briefing on what matters in tech. "
            "Top 5 stories in under 10 minutes, from the perspective of an experienced software engineer."
        ),
        "author": "Noyau News",
        "email": "hello@noyau.news",
        "website_url": "https://noyau.news",
        "feed_url": "https://noyau.news/podcast/feed.xml",
        "artwork_url": "https://noyau.news/podcast-artwork.jpg",
        "category": "Technology",
        "subcategory": "Tech News",
        "language": "en-us",
        "explicit": False,
    }
