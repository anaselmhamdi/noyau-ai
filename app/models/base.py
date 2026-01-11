from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    type_annotation_map: dict[type, Any] = {}


class TimestampMixin:
    """Mixin that adds created_at timestamp to models."""

    created_at: Mapped[datetime] = mapped_column(default=func.now())
