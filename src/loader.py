"""CSV loader — used by the demo runner, and useful on its own for a
one-off batch run against an exported list instead of a live HubSpot pull.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .models import Lead, LeadSource


def load_leads_from_csv(path: str | Path) -> list[Lead]:
    leads: list[Lead] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            leads.append(
                Lead(
                    id=row["id"],
                    name=row["name"],
                    email=row["email"],
                    company=row["company"],
                    source=LeadSource(row["source"]),
                    engagement_score=int(row["engagement_score"]),
                    last_touch_date=date.fromisoformat(row["last_touch_date"]),
                    owner_rep_id=row["owner_rep_id"],
                )
            )
    return leads
