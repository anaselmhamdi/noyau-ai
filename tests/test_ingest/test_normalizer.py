"""Tests for URL normalization and canonical identity extraction."""

from app.ingest.normalizer import (
    canonicalize_url,
    clean_html,
    extract_canonical_identity,
    extract_cve,
    extract_github_repo,
    truncate_text,
)


class TestCanonicalizeUrl:
    """Tests for URL canonicalization."""

    def test_strips_utm_params(self):
        """Should remove UTM tracking parameters."""
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&foo=bar"
        assert canonicalize_url(url) == "https://example.com/article?foo=bar"

    def test_normalizes_scheme(self):
        """Should convert http to https."""
        url = "http://example.com/article"
        assert canonicalize_url(url) == "https://example.com/article"

    def test_lowercases_hostname(self):
        """Should lowercase the hostname."""
        url = "https://EXAMPLE.COM/Article"
        assert canonicalize_url(url) == "https://example.com/Article"

    def test_removes_trailing_slash(self):
        """Should remove trailing slashes from path."""
        url = "https://example.com/article/"
        assert canonicalize_url(url) == "https://example.com/article"

    def test_preserves_root_path(self):
        """Should keep root path as /."""
        url = "https://example.com/"
        result = canonicalize_url(url)
        assert result == "https://example.com/"

    def test_removes_fragment(self):
        """Should remove URL fragments."""
        url = "https://example.com/article#section-1"
        assert canonicalize_url(url) == "https://example.com/article"

    def test_sorts_query_params(self):
        """Should sort remaining query parameters."""
        url = "https://example.com/search?z=1&a=2"
        assert canonicalize_url(url) == "https://example.com/search?a=2&z=1"

    def test_handles_malformed_url(self):
        """Should return original URL if malformed."""
        url = "not-a-valid-url"
        assert canonicalize_url(url) == url


class TestExtractGithubRepo:
    """Tests for GitHub repository extraction."""

    def test_extracts_basic_repo(self):
        """Should extract owner/repo from basic URL."""
        url = "https://github.com/kubernetes/kubernetes"
        assert extract_github_repo(url) == "kubernetes/kubernetes"

    def test_extracts_from_release_url(self):
        """Should extract from release URLs."""
        url = "https://github.com/python/cpython/releases/tag/v3.13.0"
        assert extract_github_repo(url) == "python/cpython"

    def test_extracts_from_issue_url(self):
        """Should extract from issue URLs."""
        url = "https://github.com/fastapi/fastapi/issues/1234"
        assert extract_github_repo(url) == "fastapi/fastapi"

    def test_extracts_from_pr_url(self):
        """Should extract from pull request URLs."""
        url = "https://github.com/owner/repo/pull/567"
        assert extract_github_repo(url) == "owner/repo"

    def test_handles_www_prefix(self):
        """Should handle www.github.com."""
        url = "https://www.github.com/owner/repo"
        assert extract_github_repo(url) == "owner/repo"

    def test_returns_none_for_non_github(self):
        """Should return None for non-GitHub URLs."""
        url = "https://gitlab.com/owner/repo"
        assert extract_github_repo(url) is None

    def test_returns_none_for_github_user_page(self):
        """Should return None for user profile pages."""
        url = "https://github.com/username"
        assert extract_github_repo(url) is None


class TestExtractCve:
    """Tests for CVE ID extraction."""

    def test_extracts_cve_from_text(self):
        """Should extract CVE ID from text."""
        text = "Critical vulnerability CVE-2024-12345 discovered"
        assert extract_cve(text) == "CVE-2024-12345"

    def test_extracts_lowercase_cve(self):
        """Should handle lowercase CVE."""
        text = "Fix for cve-2024-9999"
        assert extract_cve(text) == "CVE-2024-9999"

    def test_extracts_first_cve(self):
        """Should extract first CVE when multiple present."""
        text = "CVE-2024-1111 and CVE-2024-2222 patched"
        assert extract_cve(text) == "CVE-2024-1111"

    def test_handles_five_digit_sequence(self):
        """Should handle CVE IDs with 5+ digit sequence."""
        text = "CVE-2024-123456 is severe"
        assert extract_cve(text) == "CVE-2024-123456"

    def test_returns_none_when_no_cve(self):
        """Should return None when no CVE present."""
        text = "This is a normal article about Python"
        assert extract_cve(text) is None


class TestExtractCanonicalIdentity:
    """Tests for canonical identity extraction."""

    def test_github_takes_priority(self):
        """Should use GitHub repo as identity when present."""
        url = "https://github.com/owner/repo/releases"
        assert extract_canonical_identity(url, "") == "github:owner/repo"

    def test_cve_takes_priority_over_url(self):
        """Should use CVE as identity when present in text."""
        url = "https://blog.example.com/security-update"
        text = "Fix for CVE-2024-5678"
        assert extract_canonical_identity(url, text) == "cve:CVE-2024-5678"

    def test_falls_back_to_canonical_url(self):
        """Should use canonical URL as fallback."""
        url = "https://example.com/article?utm_source=test"
        assert extract_canonical_identity(url, "") == "https://example.com/article"


class TestCleanHtml:
    """Tests for HTML cleaning."""

    def test_removes_html_tags(self):
        """Should remove HTML tags."""
        html = "<p>Hello <strong>world</strong></p>"
        assert clean_html(html) == "Hello world"

    def test_decodes_entities(self):
        """Should decode HTML entities."""
        html = "&amp; &lt; &gt; &quot;"
        assert clean_html(html) == '& < > "'

    def test_normalizes_whitespace(self):
        """Should normalize multiple spaces."""
        html = "Hello    world\n\n\ntest"
        assert clean_html(html) == "Hello world test"


class TestTruncateText:
    """Tests for text truncation."""

    def test_no_truncation_needed(self):
        """Should not truncate short text."""
        text = "Short text"
        assert truncate_text(text, 100) == text

    def test_truncates_at_word_boundary(self):
        """Should truncate at word boundary."""
        text = "This is a long text that needs truncation"
        result = truncate_text(text, 25)
        assert result.endswith("...")
        assert len(result) <= 28  # 25 + "..."

    def test_handles_exact_length(self):
        """Should not truncate text at exact max length."""
        text = "Exactly twenty chars"
        assert truncate_text(text, 20) == text
