#!/usr/bin/env python3
"""Runs the full lead-decay pipeline against the sample data with mocked
HubSpot and Claude clients — no API keys, no network calls. This calls
the exact same src.pipeline.run_pipeline() that --live mode uses; only
the injected clients differ, so nothing about the actual pipeline logic
is reimplemented here.

For the real thing: `python -m src.pipeline --live` with .env configured.
"""

from __future__ import annotations

from datetime import date

from src.loader import load_leads_from_csv
from src.models import DecayResult, Lead
from src.pipeline import run_pipeline

# Fixed so the demo output is reproducible regardless of when you run it —
# it matches the dates baked into data/sample_leads.csv.
AS_OF = date(2026, 9, 11)


class MockAIFollowupClient:
    """Stands in for src.ai_followup.AIFollowupClient. Returns a
    templated draft instead of calling the Anthropic API, so the demo
    needs no key — but it's grounded in the same fields the real prompt
    uses, so the shape of the output is representative."""

    def draft(self, result: DecayResult) -> str:
        lead = result.lead
        return (
            f"Hi {lead.name.split()[0]}, following up on your "
            f"{lead.source.value.replace('_', ' ')} — you looked into this "
            f"{result.days_since_touch} days ago. Still relevant for "
            f"{lead.company}? Happy to pick up wherever it's most useful."
        )


class MockHubspotClient:
    """Stands in for src.hubspot_client.HubspotClient. Records tasks in
    memory instead of hitting the HubSpot API."""

    def __init__(self) -> None:
        self.created_tasks: list[dict] = []

    def create_followup_task(self, lead: Lead, draft: str, due_date: date, priority: str = "HIGH") -> dict:
        task = {
            "lead_id": lead.id,
            "lead_name": lead.name,
            "priority": priority,
            "due_date": due_date.isoformat(),
            "draft": draft,
        }
        self.created_tasks.append(task)
        return task


def main() -> None:
    leads = load_leads_from_csv("data/sample_leads.csv")
    ai = MockAIFollowupClient()
    hubspot = MockHubspotClient()

    results, drafted, report = run_pipeline(leads, ai=ai, hubspot=hubspot, as_of=AS_OF)

    print(report)

    print("\nSample AI-generated follow-up drafts:")
    print("─" * 44)
    for result in results:
        if result.status.value == "DECAYING" and result.lead.id in drafted:
            print(f"\n{result.lead.name} ({result.lead.company}):")
            print(f"  {drafted[result.lead.id]}")

    print(f"\n{len(hubspot.created_tasks)} follow-up tasks written back to CRM (mocked).")


if __name__ == "__main__":
    main()
