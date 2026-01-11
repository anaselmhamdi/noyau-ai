from pydantic import BaseModel


class Citation(BaseModel):
    """Citation reference with URL and label."""

    url: str
    label: str
