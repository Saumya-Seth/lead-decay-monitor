"""Core data model for the lead-decay monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class LeadSource(str, Enum):
    """The intent tier is keyed off source, not just a raw lead score.

    A demo request and a newsletter signup should decay on very different
    clocks even if their generic "engagement score" looks similar.
    """

    DEMO_REQUEST = "demo_request"
    PRICING_PAGE = "pricing_page"
    CONTENT_DOWNLOAD = "content_download"
    WEBINAR_ATTENDEE = "webinar_attendee"
    NEWSLETTER_SIGNUP = "newsletter_signup"


class DecayStatus(str, Enum):
    HOT = "HOT"
    WARMING = "WARMING"
    COOLING = "COOLING"
    DECAYING = "DECAYING"
    COLD = "COLD"


@dataclass
class Lead:
    id: str
    name: str
    email: str
    company: str
    source: LeadSource
    engagement_score: int  # 0-100, from form fills / page views / email opens etc.
    last_touch_date: date
    owner_rep_id: str

    def __post_init__(self) -> None:
        if not 0 <= self.engagement_score <= 100:
            raise ValueError(
                f"engagement_score must be 0-100, got {self.engagement_score}"
            )


@dataclass
class DecayResult:
    lead: Lead
    status: DecayStatus
    days_since_touch: int
    days_overdue: int  # 0 if not past the "cooling" threshold yet
    reason: str  # human-readable, fed straight into the AI follow-up prompt
