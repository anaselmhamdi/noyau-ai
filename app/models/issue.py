from datetime import date, datetime

from sqlalchemy import Date, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Issue(Base):
    """A daily digest issue containing top 10 clusters."""

    __tablename__ = "issues"

    issue_date: Mapped[date] = mapped_column(Date, primary_key=True)
    public_url: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    def __repr__(self) -> str:
        return f"<Issue {self.issue_date}>"
