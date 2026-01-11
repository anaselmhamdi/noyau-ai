import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.core.logging import get_logger

logger = get_logger(__name__)

# Tracking parameters to strip from URLs
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(url: str) -> str:
    """
    Canonicalize a URL for clustering purposes.

    - Normalize scheme to https
    - Lowercase hostname
    - Remove trailing slashes
    - Strip tracking parameters (utm_*, ref, fbclid, etc.)
    - Sort remaining query params
    """
    try:
        parsed = urlparse(url)

        # Validate that we have a proper URL with scheme and netloc
        if not parsed.netloc or parsed.scheme not in ("http", "https"):
            return url

        # Remove tracking params
        query = parse_qs(parsed.query)
        clean_query = {k: v for k, v in query.items() if k.lower() not in TRACKING_PARAMS}

        # Sort remaining params for consistency
        sorted_query = urlencode(sorted(clean_query.items()), doseq=True)

        # Rebuild URL
        canonical = urlunparse(
            (
                "https",  # Always use https
                parsed.netloc.lower(),  # Lowercase hostname
                parsed.path.rstrip("/") or "/",  # Remove trailing slash
                "",  # params
                sorted_query,  # query
                "",  # fragment (remove)
            )
        )
        return canonical
    except Exception as e:
        logger.debug("url_canonicalization_failed", url=url, error=str(e))
        return url


def extract_github_repo(url: str) -> str | None:
    """
    Extract owner/repo from GitHub URLs.

    Examples:
        https://github.com/owner/repo -> owner/repo
        https://github.com/owner/repo/releases/tag/v1.0 -> owner/repo
        https://github.com/owner/repo/issues/123 -> owner/repo
    """
    match = re.match(
        r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)",
        url,
        re.IGNORECASE,
    )
    if match:
        owner, repo = match.groups()
        # Clean up repo name (remove .git suffix, etc.)
        repo = repo.split(".git")[0].split("/")[0].split("?")[0].split("#")[0]
        return f"{owner}/{repo}"
    return None


def extract_cve(text: str) -> str | None:
    """
    Extract CVE ID from text.

    Pattern: CVE-YYYY-NNNNN (4-digit year, 4+ digit sequence)
    """
    match = re.search(r"CVE-\d{4}-\d{4,}", text, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return None


def extract_canonical_identity(url: str, text: str = "") -> str:
    """
    Extract canonical identity for clustering.

    Priority:
    1. GitHub repo (owner/repo)
    2. CVE ID
    3. Canonicalized URL
    """
    # Check for GitHub repo
    repo = extract_github_repo(url)
    if repo:
        return f"github:{repo}"

    # Check for CVE in text or URL
    combined_text = f"{url} {text}"
    cve = extract_cve(combined_text)
    if cve:
        return f"cve:{cve}"

    # Default to canonicalized URL
    return canonicalize_url(url)


def clean_html(html: str) -> str:
    """Remove HTML tags and decode entities."""
    import html as html_module

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode HTML entities
    text = html_module.unescape(text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_text(text: str, max_length: int = 2000) -> str:
    """Truncate text to max length, breaking at word boundary."""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    # Break at last word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]
    return truncated + "..."
