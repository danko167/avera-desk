from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ..ai.usage_store import record_llm_usage
from ..calendar import proposals as calendar_proposals
from ..calendar.commands import handle_calendar_command_from_transcript
from ..email.commands import handle_email_command_from_transcript
from ..email.draft_commands import handle_email_draft_command_from_transcript
from ..followups.commands import handle_follow_up_command_from_transcript
from ..speech.intent_router import route_speech_intent
from ..shared.outcome import ServiceExecutionOutcome
from .engine import (
    EngineHandlers,
    build_plan,
    evaluate_plan,
    execute_plan,
    load_world_state,
    parse_goal,
)

async def handle_speech_command_from_transcript(
    db: AsyncSession,
    *,
    notification_id: str | None,
    transcript_text: str,
    correlation_id: str | None = None,
) -> ServiceExecutionOutcome:
    world_state = await load_world_state(db, notification_id=notification_id)
    goal = await parse_goal(
        db,
        utterance=transcript_text,
        notification_id=notification_id,
        has_active_draft=bool(world_state.draft_id),
        route_intent=route_speech_intent,
    )

    if getattr(goal, "usage", None) is not None:
        llm_config = await get_llm_config(db)
        await record_llm_usage(
            db,
            interaction_kind="speech_intent_route",
            provider=llm_config.provider,
            model=llm_config.model or "gpt-5.4-mini",
            usage=goal.usage,
            notification_id=notification_id,
            metadata_json={
                "correlation_id": correlation_id,
                "domain": goal.domain,
                "action": goal.action,
                "slots": goal.slots,
                "confidence": goal.confidence,
                "reasoning": goal.reasoning,
                "missing_slots": goal.missing_slots,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    plan = build_plan(goal=goal, state=world_state)
    policy_decision = evaluate_plan(plan)
    if not policy_decision.allowed:
        return ServiceExecutionOutcome(
            result="intent_clarification_needed",
            display_text=policy_decision.reason or "This action is blocked by policy.",
        )

    handlers = EngineHandlers(
        handle_calendar_command=handle_calendar_command_from_transcript,
        handle_email_command=handle_email_command_from_transcript,
        handle_email_draft_command=handle_email_draft_command_from_transcript,
        handle_followup_command=handle_follow_up_command_from_transcript,
        approve_calendar_proposal=calendar_proposals.approve_proposal,
        cancel_calendar_proposal=calendar_proposals.cancel_proposal,
    )

    return await execute_plan(
        db,
        goal=goal,
        state=world_state,
        plan=plan,
        correlation_id=correlation_id,
        handlers=handlers,
    )
