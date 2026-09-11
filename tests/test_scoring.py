from datetime import date

import pytest

from src.models import DecayStatus, Lead, LeadSource
from src.scoring import classify_decay, engagement_multiplier, expected_windows, needs_followup

AS_OF = date(2026, 9, 11)


def make_lead(source: LeadSource, days_ago: int, engagement_score: int = 50, **kwargs) -> Lead:
    defaults = dict(
        id="test_lead",
        name="Test Lead",
        email="test@example.example",
        company="Test Co",
        owner_rep_id="rep_000",
    )
    defaults.update(kwargs)
    return Lead(
        source=source,
        engagement_score=engagement_score,
        last_touch_date=date.fromordinal(AS_OF.toordinal() - days_ago),
        **defaults,
    )


def test_engagement_multiplier_bounds():
    assert engagement_multiplier(0) == pytest.approx(0.7)
    assert engagement_multiplier(100) == pytest.approx(1.3)
    assert engagement_multiplier(50) == pytest.approx(1.0)


def test_demo_request_same_day_is_hot():
    lead = make_lead(LeadSource.DEMO_REQUEST, days_ago=0)
    result = classify_decay(lead, AS_OF)
    assert result.status == DecayStatus.HOT
    assert result.days_overdue == 0


def test_demo_request_decays_fast():
    """A demo-request lead should already be DECAYING by day 4, while a
    newsletter lead at day 4 is still comfortably HOT — this is the whole
    point of the source-calibrated curve."""
    demo_lead = make_lead(LeadSource.DEMO_REQUEST, days_ago=4)
    newsletter_lead = make_lead(LeadSource.NEWSLETTER_SIGNUP, days_ago=4)

    demo_result = classify_decay(demo_lead, AS_OF)
    newsletter_result = classify_decay(newsletter_lead, AS_OF)

    assert demo_result.status == DecayStatus.DECAYING
    assert newsletter_result.status == DecayStatus.HOT


def test_cold_status_past_max_window():
    lead = make_lead(LeadSource.DEMO_REQUEST, days_ago=10)
    result = classify_decay(lead, AS_OF)
    assert result.status == DecayStatus.COLD


def test_higher_engagement_buys_more_patience():
    """Same source, same days-ago, but a highly engaged lead should not be
    further along in decay than a low-engagement one."""
    low = make_lead(LeadSource.CONTENT_DOWNLOAD, days_ago=8, engagement_score=10)
    high = make_lead(LeadSource.CONTENT_DOWNLOAD, days_ago=8, engagement_score=95)

    low_result = classify_decay(low, AS_OF)
    high_result = classify_decay(high, AS_OF)

    statuses_in_order = list(DecayStatus)
    assert statuses_in_order.index(high_result.status) <= statuses_in_order.index(
        low_result.status
    )


@pytest.mark.parametrize("source", list(LeadSource))
def test_expected_windows_always_strictly_increasing(source):
    """Regression test: at low engagement scores on fast-decaying sources,
    naive independent rounding of each threshold could make two adjacent
    thresholds collide (e.g. both round to day 1), making a status band
    unreachable. Every threshold must be strictly greater than the last
    across the full 0-100 engagement range."""
    for score in range(0, 101):
        windows = expected_windows(source, score)
        assert windows[0] < windows[1] < windows[2] < windows[3], (
            f"{source} at engagement_score={score} produced non-increasing "
            f"windows {windows}"
        )


def test_warming_status_is_reachable_at_low_engagement():
    """The specific bug the regression test above guards against: with the
    old naive rounding, a DEMO_REQUEST lead at low engagement would skip
    WARMING entirely and jump straight from HOT to COOLING."""
    lead = make_lead(LeadSource.DEMO_REQUEST, days_ago=0, engagement_score=5)
    warming_at, cooling_at, _, _ = expected_windows(LeadSource.DEMO_REQUEST, 5)
    assert warming_at < cooling_at  # there must be at least one day where WARMING applies


def test_expected_windows_scale_with_source():
    demo_windows = expected_windows(LeadSource.DEMO_REQUEST, 50)
    newsletter_windows = expected_windows(LeadSource.NEWSLETTER_SIGNUP, 50)
    assert demo_windows < newsletter_windows


@pytest.mark.parametrize(
    "status,expected",
    [
        (DecayStatus.HOT, False),
        (DecayStatus.WARMING, False),
        (DecayStatus.COOLING, True),
        (DecayStatus.DECAYING, True),
        (DecayStatus.COLD, False),
    ],
)
def test_needs_followup_only_for_cooling_and_decaying(status, expected):
    lead = make_lead(LeadSource.DEMO_REQUEST, days_ago=0)
    from src.models import DecayResult

    result = DecayResult(lead=lead, status=status, days_since_touch=0, days_overdue=0, reason="")
    assert needs_followup(result) is expected
