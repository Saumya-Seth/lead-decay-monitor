"""Orchestrates a full run: pull leads → score → classify → draft →
write back → report.

Clients are injected (`hubspot`, `ai`) rather than constructed inline, so
the exact same pipeline function runs identically in --live mode (real
API clients) and in the demo (mock clients, see run_demo.py). This is
also what makes the pipeline trivially testable without hitting a network.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from typing import Protocol

from dotenv import load_dotenv

from .ai_followup import AIFollowupClient
from .dashboard import render_report
from .hubspot_client import HubspotClient
from .loader import load_leads_from_csv
from .models import DecayResult, Lead
from .scoring import classify_decay, needs_followup


class FollowupDrafter(Protocol):
    def draft(self, result: DecayResult) -> str: ...


class TaskWriter(Protocol):
    def create_followup_task(
        self, lead: Lead, draft: str, due_date: date, priority: str = "HIGH"
    ) -> dict: ...


def run_pipeline(
    leads: list[Lead],
    ai: FollowupDrafter,
    hubspot: TaskWriter,
    as_of: date | None = None,
) -> tuple[list[DecayResult], dict[str, str], str]:
    as_of = as_of or date.today()

    results = [classify_decay(lead, as_of) for lead in leads]
    drafted: dict[str, str] = {}

    for result in results:
        if needs_followup(result):
            draft = ai.draft(result)
            drafted[result.lead.id] = draft
            hubspot.create_followup_task(
                lead=result.lead,
                draft=draft,
                due_date=as_of,
                priority="HIGH" if result.status.value == "DECAYING" else "MEDIUM",
            )

    report = render_report(results, drafted)
    return results, drafted, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lead decay pipeline")
    parser.add_argument("--live", action="store_true", help="Hit real HubSpot/Anthropic APIs")
    parser.add_argument("--csv", default="data/sample_leads.csv", help="CSV source for leads")
    parser.add_argument("--list-id", default=None, help="HubSpot active-pipeline list ID (--live only)")
    args = parser.parse_args()

    if args.live:
        load_dotenv()
        hubspot = HubspotClient.from_env()
        ai = AIFollowupClient.from_env()
        list_id = args.list_id or os.environ.get("HUBSPOT_ACTIVE_LIST_ID")
        if not list_id:
            raise SystemExit("Pass --list-id or set HUBSPOT_ACTIVE_LIST_ID for --live mode")
        leads = hubspot.fetch_active_leads(list_id)
    else:
        raise SystemExit("Non-live mode needs mock clients — use run_demo.py instead")

    _, _, report = run_pipeline(leads, ai=ai, hubspot=hubspot)
    print(report)


if __name__ == "__main__":
    main()
