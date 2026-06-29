"""Typed data structures the agent passes between stages.

Keeping these explicit makes the pipeline easy to read: each stage takes a
typed input and returns a typed output.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import List, Optional, Dict, Any


@dataclass
class Partner:
    """One partner record as ingested from the data store."""
    id: str
    name: str
    owner: str
    region: str
    segment: str
    monthly_volume_inr: int
    last_contact_date: str  # ISO date string
    followups_sent: int
    awaiting_response: bool
    open_issue: Optional[str]
    notes: str

    def days_since_contact(self, reference: date) -> int:
        last = datetime.strptime(self.last_contact_date, "%Y-%m-%d").date()
        return (reference - last).days


@dataclass
class Classification:
    """The agent's *understanding* of a partner (LLM or rule-based)."""
    status: str
    severity: str            # low | medium | high
    sentiment: str           # positive | neutral | negative
    confidence: float        # 0.0 - 1.0
    summary: str
    pending_actions: List[str] = field(default_factory=list)
    source: str = "rules"    # "llm" or "rules" — for transparency

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    """The agent's *decision* — what to do, and why."""
    action: str              # NO_ACTION | SEND_REMINDER | ESCALATE
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
