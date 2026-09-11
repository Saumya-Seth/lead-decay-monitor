"""Thin wrapper around the HubSpot CRM v3 REST API.

Only the handful of endpoints this pipeline actually needs: pulling active
contacts with their engagement properties, creating a follow-up task, and
logging a note. Swap `HubspotClient` for `MockHubspotClient` (see
run_demo.py) to run the whole pipeline with zero network calls.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests

from .models import Lead, LeadSource

HUBSPOT_BASE_URL = "https://api.hubapi.com"


@dataclass
class HubspotClient:
    api_key: str
    base_url: str = HUBSPOT_BASE_URL

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def fetch_active_leads(self, list_id: str) -> list[Lead]:
        """Pull every contact in the given active-pipeline list, mapped to
        our Lead model. Assumes custom properties `lead_source`,
        `engagement_score`, `last_touch_date`, and `owner_rep_id` exist on
        the portal — see README for the property setup this expects.
        """
        url = f"{self.base_url}/crm/v3/lists/{list_id}/memberships"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        contact_ids = [m["recordId"] for m in resp.json().get("results", [])]
        return [self._fetch_contact_as_lead(cid) for cid in contact_ids]

    def _fetch_contact_as_lead(self, contact_id: str) -> Lead:
        url = f"{self.base_url}/crm/v3/objects/contacts/{contact_id}"
        params = {
            "properties": (
                "firstname,lastname,email,company,lead_source,"
                "engagement_score,last_touch_date,owner_rep_id"
            )
        }
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        props = resp.json()["properties"]
        return Lead(
            id=contact_id,
            name=f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
            email=props["email"],
            company=props.get("company", ""),
            source=LeadSource(props["lead_source"]),
            engagement_score=int(props.get("engagement_score", 0)),
            last_touch_date=datetime.fromisoformat(props["last_touch_date"]).date(),
            owner_rep_id=props.get("owner_rep_id", "unassigned"),
        )

    def create_followup_task(
        self, lead: Lead, draft: str, due_date: date, priority: str = "HIGH"
    ) -> dict[str, Any]:
        url = f"{self.base_url}/crm/v3/objects/tasks"
        payload = {
            "properties": {
                "hs_task_subject": f"Decay follow-up: {lead.name} ({lead.company})",
                "hs_task_body": draft,
                "hs_task_priority": priority,
                "hs_task_status": "NOT_STARTED",
                "hs_timestamp": due_date.isoformat(),
                "hubspot_owner_id": lead.owner_rep_id,
            },
            "associations": [
                {
                    "to": {"id": lead.id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 204,
                        }
                    ],
                }
            ],
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def from_env(cls) -> "HubspotClient":
        key = os.environ.get("HUBSPOT_API_KEY")
        if not key:
            raise RuntimeError("HUBSPOT_API_KEY not set — copy .env.example to .env")
        return cls(api_key=key)
