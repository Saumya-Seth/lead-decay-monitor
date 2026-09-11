"""Generates a short, specific re-engagement draft for a decaying lead.

The key design choice: the prompt is grounded in *why* this specific lead
is decaying (source, days overdue, engagement history) rather than asking
for a generic "just checking in" message. That's what made the real
version usable enough for reps to send with light or no editing, instead
of becoming another AI draft nobody trusts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .models import DecayResult

SYSTEM_PROMPT = """You write short, specific re-engagement emails for a B2B \
sales rep to send to a lead who has gone quiet. Rules:
- Under 80 words.
- Reference the lead's actual last action (why they were interested), never \
a generic "just checking in."
- One clear, low-friction next step (a specific question or a 2-line answer \
they can give), never "let me know if you're still interested."
- No exclamation points, no "circling back," no corporate throat-clearing.
- Write only the email body, no subject line, no signature."""


@dataclass
class AIFollowupClient:
    api_key: str
    model: str = "claude-sonnet-4-5"

    def draft(self, result: DecayResult) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        user_prompt = (
            f"Lead: {result.lead.name} at {result.lead.company}\n"
            f"Came in via: {result.lead.source.value}\n"
            f"Status: {result.status.value}, {result.days_since_touch} days "
            f"since last touch, {result.days_overdue} days overdue.\n"
            f"Context: {result.reason}\n\n"
            "Write the re-engagement email body."
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text.strip()

    @classmethod
    def from_env(cls) -> "AIFollowupClient":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set — copy .env.example to .env")
        return cls(api_key=key)
