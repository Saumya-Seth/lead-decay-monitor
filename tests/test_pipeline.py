"""Tests for run_pipeline() itself — previously this had zero coverage;
run_demo.py reimplemented the loop instead of calling it, so a bug here
could ship undetected. Uses the same kind of mock clients run_demo.py
uses, but defined locally so this test doesn't depend on run_demo.py."""

from __future__ import annotations

from datetime import date

from src.models import DecayResult, DecayStatus, Lead, LeadSource
from src.pipeline import run_pipeline

AS_OF = date(2026, 9, 11)


class StubAI:
    def __init__(self) -> None:
        self.calls: list[DecayResult] = []

    def draft(self, result: DecayResult) -> str:
        self.calls.append(result)
        return f"draft for {result.lead.name}"


class StubHubspot:
    def __init__(self) -> None:
        self.created_tasks: list[dict] = []

    def create_followup_task(self, lead: Lead, draft: str, due_date: date, priority: str = "HIGH") -> dict:
        task = {"lead_id": lead.id, "priority": priority, "draft": draft}
        self.created_tasks.append(task)
        return task


def make_lead(source: LeadSource, days_ago: int, **kwargs) -> Lead:
    defaults = dict(
        id=f"lead_{days_ago}",
        name="Test Lead",
        email="test@test.example",
        company="Test Co",
        engagement_score=50,
        owner_rep_id="rep_000",
    )
    defaults.update(kwargs)
    return Lead(
        source=source,
        last_touch_date=date.fromordinal(AS_OF.toordinal() - days_ago),
        **defaults,
    )


def test_run_pipeline_only_drafts_for_cooling_and_decaying():
    leads = [
        make_lead(LeadSource.DEMO_REQUEST, days_ago=0, id="hot"),      # HOT
        make_lead(LeadSource.DEMO_REQUEST, days_ago=2, id="cooling"),  # COOLING
        make_lead(LeadSource.DEMO_REQUEST, days_ago=10, id="cold"),    # COLD
    ]
    ai, hubspot = StubAI(), StubHubspot()

    results, drafted, report = run_pipeline(leads, ai=ai, hubspot=hubspot, as_of=AS_OF)

    assert len(results) == 3
    assert "cooling" in drafted
    assert "hot" not in drafted
    assert "cold" not in drafted
    assert len(ai.calls) == 1
    assert len(hubspot.created_tasks) == 1


def test_run_pipeline_report_reflects_status_counts():
    leads = [make_lead(LeadSource.DEMO_REQUEST, days_ago=0, id=f"hot_{i}") for i in range(3)]
    ai, hubspot = StubAI(), StubHubspot()

    _, _, report = run_pipeline(leads, ai=ai, hubspot=hubspot, as_of=AS_OF)

    assert "HOT" in report
    assert "3 leads" in report


def test_run_pipeline_decaying_gets_high_priority_task():
    leads = [make_lead(LeadSource.DEMO_REQUEST, days_ago=4, id="decaying")]  # DECAYING
    ai, hubspot = StubAI(), StubHubspot()

    run_pipeline(leads, ai=ai, hubspot=hubspot, as_of=AS_OF)

    assert hubspot.created_tasks[0]["priority"] == "HIGH"


def test_run_pipeline_cooling_gets_medium_priority_task():
    leads = [make_lead(LeadSource.DEMO_REQUEST, days_ago=2, id="cooling")]  # COOLING
    ai, hubspot = StubAI(), StubHubspot()

    run_pipeline(leads, ai=ai, hubspot=hubspot, as_of=AS_OF)

    assert hubspot.created_tasks[0]["priority"] == "MEDIUM"
