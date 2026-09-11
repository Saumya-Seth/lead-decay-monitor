"""Decay scoring engine.

Pure functions, no network calls, fully unit-testable — this is the one
module a reviewer should be able to read end to end and trust.

The core idea: a lead's "days since last touch" means nothing on its own.
A demo-request lead going quiet for 5 days is a fire; a newsletter
subscriber going quiet for 5 days is Tuesday. So every source has its own
base decay curve (in days), and that curve is then stretched or compressed
by how engaged the lead has been historically.
"""

from __future__ import annotations

from datetime import date

from .models import DecayResult, DecayStatus, Lead, LeadSource

# Base thresholds in days: (warming_at, cooling_at, decaying_at, cold_at)
# Read as: "still HOT until `warming_at` days since last touch, then WARMING
# until `cooling_at`, then COOLING until `decaying_at`, then DECAYING until
# `cold_at`, then COLD."
SOURCE_BASE_WINDOWS: dict[LeadSource, tuple[int, int, int, int]] = {
    LeadSource.DEMO_REQUEST: (1, 2, 3, 5),
    LeadSource.PRICING_PAGE: (1, 3, 5, 8),
    LeadSource.WEBINAR_ATTENDEE: (2, 5, 9, 15),
    LeadSource.CONTENT_DOWNLOAD: (3, 7, 12, 20),
    LeadSource.NEWSLETTER_SIGNUP: (7, 14, 25, 40),
}


def engagement_multiplier(engagement_score: int) -> float:
    """Higher historical engagement buys a lead a bit more patience before
    it's flagged; lower engagement means act sooner. Ranges 0.7x-1.3x so a
    single low score can't collapse the window to nothing, and a single
    high score can't stretch it indefinitely.
    """
    return 0.7 + (engagement_score / 100) * 0.6


def expected_windows(source: LeadSource, engagement_score: int) -> tuple[int, int, int, int]:
    """The four day-thresholds for this specific lead, source curve
    adjusted by engagement.

    Each threshold is rounded independently, so at low engagement scores
    on a fast-decaying source (e.g. DEMO_REQUEST's base window of
    (1, 2, 3, 5)) two adjacent thresholds can round to the same day,
    making a status band mathematically unreachable — a lead would jump
    straight from HOT to COOLING with no WARMING day in between. This
    enforces each threshold is at least one day past the previous one,
    so every status band always has real width.
    """
    base = SOURCE_BASE_WINDOWS[source]
    mult = engagement_multiplier(engagement_score)
    windows: list[int] = []
    for days in base:
        threshold = round(days * mult)
        if windows and threshold <= windows[-1]:
            threshold = windows[-1] + 1
        windows.append(threshold)
    return tuple(windows)  # type: ignore[return-value]


def classify_decay(lead: Lead, as_of: date) -> DecayResult:
    days_since_touch = (as_of - lead.last_touch_date).days
    warming_at, cooling_at, decaying_at, cold_at = expected_windows(
        lead.source, lead.engagement_score
    )

    if days_since_touch < warming_at:
        status = DecayStatus.HOT
        days_overdue = 0
        reason = "Within expected touch window, no action needed."
    elif days_since_touch < cooling_at:
        status = DecayStatus.WARMING
        days_overdue = 0
        reason = f"Approaching the expected re-touch window for a {lead.source.value} lead."
    elif days_since_touch < decaying_at:
        status = DecayStatus.COOLING
        days_overdue = days_since_touch - cooling_at
        reason = (
            f"{days_since_touch} days since last touch, past the expected "
            f"window for a {lead.source.value} lead (engagement score "
            f"{lead.engagement_score})."
        )
    elif days_since_touch < cold_at:
        status = DecayStatus.DECAYING
        days_overdue = days_since_touch - decaying_at
        reason = (
            f"{days_since_touch} days since last touch, significantly "
            f"overdue for a {lead.source.value} lead — priority re-engagement."
        )
    else:
        status = DecayStatus.COLD
        days_overdue = days_since_touch - cold_at
        reason = (
            f"{days_since_touch} days since last touch, past the maximum "
            f"re-engagement window. Routing to long-term nurture."
        )

    return DecayResult(
        lead=lead,
        status=status,
        days_since_touch=days_since_touch,
        days_overdue=days_overdue,
        reason=reason,
    )


def needs_followup(result: DecayResult) -> bool:
    """COOLING and DECAYING are the two statuses worth an active
    re-engagement draft. HOT/WARMING need no action yet, COLD has already
    missed the window and goes to long-term nurture instead."""
    return result.status in (DecayStatus.COOLING, DecayStatus.DECAYING)
