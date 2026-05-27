from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..interaction.client_feedback import ClientInteractionOutcome


def _default_interaction() -> "ClientInteractionOutcome":
    # Lazy import prevents circular import at module load time.
    from ..interaction.client_feedback import ClientInteractionOutcome

    return ClientInteractionOutcome()


@dataclass(slots=True)
class ServiceExecutionOutcome:
    result: str | None = None
    display_text: str | None = None
    interaction: "ClientInteractionOutcome" = field(default_factory=_default_interaction)