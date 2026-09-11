"""Rolls a batch of DecayResults up into the agent-level summary a sales
manager actually wants: who has decaying leads, and how bad is the oldest
one, not just a flat count of statuses.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import DecayResult, DecayStatus


@dataclass
class RepSummary:
    rep_id: str
    needs_followup_count: int  # COOLING + DECAYING leads owned by this rep
    oldest_overdue_days: int
    worst_lead_name: str


def status_counts(results: list[DecayResult]) -> dict[DecayStatus, int]:
    counts: dict[DecayStatus, int] = defaultdict(int)
    for r in results:
        counts[r.status] += 1
    return dict(counts)


def rep_summaries(results: list[DecayResult]) -> list[RepSummary]:
    by_rep: dict[str, list[DecayResult]] = defaultdict(list)
    for r in results:
        if r.status in (DecayStatus.COOLING, DecayStatus.DECAYING):
            by_rep[r.lead.owner_rep_id].append(r)

    summaries = []
    for rep_id, rep_results in by_rep.items():
        worst = max(rep_results, key=lambda r: r.days_overdue)
        summaries.append(
            RepSummary(
                rep_id=rep_id,
                needs_followup_count=len(rep_results),
                oldest_overdue_days=worst.days_overdue,
                worst_lead_name=worst.lead.name,
            )
        )
    return sorted(summaries, key=lambda s: s.oldest_overdue_days, reverse=True)


def render_report(results: list[DecayResult], drafted: dict[str, str]) -> str:
    counts = status_counts(results)
    reps = rep_summaries(results)
    priority = [r for r in results if r.status == DecayStatus.DECAYING]

    lines = [
        "LEAD DECAY REPORT",
        "─" * 44,
    ]
    for status in DecayStatus:
        n = counts.get(status, 0)
        note = {
            DecayStatus.HOT: "(no action)",
            DecayStatus.WARMING: "(flagged)",
            DecayStatus.COOLING: "(follow-up queued)",
            DecayStatus.DECAYING: "(priority — task created)",
            DecayStatus.COLD: "(routed to nurture)",
        }[status]
        lines.append(f"{status.value:<10} {n:>3} leads   {note}")

    lines.append("")
    lines.append(f"Priority follow-ups this run: {len(priority)}")
    for r in sorted(priority, key=lambda r: -r.days_overdue)[:5]:
        lines.append(
            f"  → {r.lead.name} ({r.lead.source.value}, "
            f"{r.days_overdue}d overdue) — task assigned to {r.lead.owner_rep_id}"
        )

    if reps:
        lines.append("")
        lines.append("Rep summary (cooling + decaying leads owned):")
        for s in reps:
            lines.append(
                f"  {s.rep_id}: {s.needs_followup_count} leads needing follow-up, "
                f"oldest {s.oldest_overdue_days} days overdue "
                f"({s.worst_lead_name})"
            )

    return "\n".join(lines)
