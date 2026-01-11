from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Citation


class ClusterDistillOutput(BaseModel):
    """
    Structured output schema for LLM cluster distillation.

    Used with OpenAI's response_format for guaranteed schema compliance.
    """

    headline: str = Field(
        description="Concise headline, max 90 characters",
        max_length=200,
    )
    teaser: str = Field(
        description="One line public teaser",
        max_length=500,
    )
    takeaway: str = Field(
        description="1-2 line key takeaway for subscribers",
    )
    why_care: str | None = Field(
        default=None,
        description="Optional 1 line explaining relevance",
    )
    bullets: list[str] = Field(
        description="Exactly 2 actionable bullet points",
        min_length=2,
        max_length=2,
    )
    citations: list[Citation] = Field(
        description="1-3 source citations with URLs",
        min_length=1,
        max_length=3,
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description="Confidence level in the summary accuracy",
    )


class ClusterItemInput(BaseModel):
    """Input item for cluster distillation."""

    title: str
    url: str
    text_excerpt: str | None = None
    published_at: str
    metrics_summary: str


class ClusterDistillInput(BaseModel):
    """Input payload for LLM cluster distillation."""

    dominant_topic: str
    canonical_identity: str
    items: list[ClusterItemInput]


class DistillResult(BaseModel):
    """Result of distillation including token usage."""

    output: ClusterDistillOutput
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
