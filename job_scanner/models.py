"""Data models for job scanner."""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    source: str
    external_id: str
    company: str
    title: str
    location: str = ""
    salary: Optional[str] = None
    description: str = ""
    application_link: str = ""
    posted_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def generate_id(cls, source: str, external_id: str) -> str:
        return f"{source}_{external_id}"
