from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SemanticGoal:
    utterance: str
    domain: str
    action: str
    slots: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    missing_slots: list[str] = field(default_factory=list)
    clarification_question: str | None = None
    reasoning: str = ""
    usage: Any | None = None


@dataclass(slots=True)
class WorldState:
    notification_id: str | None
    has_notification_context: bool
    draft_id: str | None = None
    calendar_proposal_id: str | None = None
    follow_up_id: str | None = None


@dataclass(slots=True)
class PlanStep:
    capability: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionPlan:
    goal: SemanticGoal
    steps: list[PlanStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
