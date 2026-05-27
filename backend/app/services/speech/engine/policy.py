from __future__ import annotations

from dataclasses import dataclass

from .capabilities import CAPABILITIES
from .models import ExecutionPlan


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None


ALLOWED_CAPABILITY_PREFIXES = {
    "calendar.",
    "email.",
    "followup.",
    "notification.",
    "clarify",
}


def evaluate_plan(plan: ExecutionPlan) -> PolicyDecision:
    for step in plan.steps:
        capability = CAPABILITIES.get(step.capability)
        if capability is None:
            return PolicyDecision(False, f"Unsupported capability: {step.capability}")

        if not any(
            step.capability == prefix or step.capability.startswith(prefix)
            for prefix in ALLOWED_CAPABILITY_PREFIXES
        ):
            return PolicyDecision(False, f"Capability blocked by policy: {step.capability}")

    return PolicyDecision(True)
