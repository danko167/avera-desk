from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability:
    key: str
    description: str


CAPABILITIES: dict[str, Capability] = {
    "calendar.approve_proposal": Capability(
        key="calendar.approve_proposal",
        description="Approve a pending calendar proposal and create/send event",
    ),
    "calendar.cancel_proposal": Capability(
        key="calendar.cancel_proposal",
        description="Cancel a pending calendar proposal",
    ),
    "calendar.handle_command": Capability(
        key="calendar.handle_command",
        description="Handle natural-language calendar scheduling command",
    ),
    "email.handle_command": Capability(
        key="email.handle_command",
        description="Handle natural-language email command",
    ),
    "email.handle_draft_command": Capability(
        key="email.handle_draft_command",
        description="Handle natural-language draft action command",
    ),
    "followup.handle_command": Capability(
        key="followup.handle_command",
        description="Handle follow-up action commands",
    ),
    "notification.dismiss": Capability(
        key="notification.dismiss",
        description="Dismiss the currently focused notification",
    ),
    "clarify": Capability(
        key="clarify",
        description="Ask the user for missing required detail",
    ),
}
