import logging
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_speech_config
from ...core.control_intent import classify_control_intent, normalize_control_utterance, trim_stt_noise_prefix
from ...db import db_session
from ...db.tables import NotificationRecord
from ...core.transcription_trace import (
    TranscriptionTrace,
    set_trace_enabled,
)
from ...integrations.email_provider import get_oauth_module, normalize_email_provider
from ..interaction import execute_service_interaction
from ..shared import conversation_turns, notifications, preferences, status
from ..speech import handle_speech_command_from_transcript
from ..speech.realtime import RealtimeTranscriber, RealtimeTranscriptionError


_live_transcribers: dict[int, RealtimeTranscriber] = {}
logger = logging.getLogger(__name__)
_MAX_AUDIO_CHUNK_BYTES = 256 * 1024
_MAX_AUDIO_B64_CHARS = 1_400_000
_MAX_SESSION_AUDIO_BYTES = 10 * 1024 * 1024
_UNMAPPED_ACTION_LABELS_LOGGED: set[str] = set()


def _safe_log_text(value: str) -> str:
    return value.encode("cp1252", errors="replace").decode("cp1252")


def _normalize_control_utterance(text: str) -> str:
    return normalize_control_utterance(text)


def _classify_control_intent(text: str) -> tuple[str, str]:
    return classify_control_intent(text)


def _format_recognized_action_label(action: str | None) -> str:
    if action is None:
        return "No action recognized"

    labels: dict[str, str] = {
        "new_email": "New email recognized",
        "reply": "Reply action recognized",
        "email_draft_ready": "Email draft action recognized",
        "email_reply_unavailable": "Reply action recognized (missing email context)",
        "email_and_calendar_ready": "Email and calendar actions recognized",
        "calendar_proposal_ready": "Calendar action recognized",
        "calendar_proposal_approved": "Calendar proposal approved",
        "calendar_proposal_canceled": "Calendar proposal canceled",
        "calendar_unavailable": "Calendar action recognized (unavailable)",
        "email_draft_canceled": "Cancel draft action recognized",
        "email_draft_recipient_updated": "Update recipient action recognized",
        "email_draft_sent": "Send draft action recognized",
        "email_draft_send_failed": "Send draft action recognized (failed)",
        "intent_clarification_needed": "Clarification needed",
        "dismiss": "Dismiss action recognized",
        "complete": "Complete action recognized",
        "snooze": "Snooze action recognized",
    }

    mapped = labels.get(action)
    if mapped is not None:
        return mapped

    if action not in _UNMAPPED_ACTION_LABELS_LOGGED:
        logger.warning("unmapped_recognized_action_label action=%s", action)
        _UNMAPPED_ACTION_LABELS_LOGGED.add(action)

    humanized = action.replace("_", " ").strip().capitalize()
    return f"{humanized} recognized"


async def _send_json_if_connected(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except WebSocketDisconnect:
        return False
    except RuntimeError as exc:
        if "WebSocket is not connected" in str(exc):
            return False
        raise


async def handle_ping(websocket: WebSocket) -> None:
    """Handle ping message."""
    await _send_json_if_connected(websocket, {"type": "pong"})


async def handle_set_status(message: dict) -> None:
    """Handle manual status update request."""
    requested_state = message.get("state", "standby")
    detail = message.get("detail", "Manual status update")

    if requested_state in {"standby", "running", "error"}:
        await status.set_status(requested_state, detail)


async def handle_mock_trigger(message: dict, db: AsyncSession) -> None:
    """Handle mock trigger for testing."""
    mock_message = message.get("message", "Dummy attention signal from backend")
    notification_type = message.get("notification_type", "info")

    if notification_type not in {"info", "warning", "error", "success"}:
        notification_type = "info"

    # Guard against duplicate events from transient multi-window/listener races.
    duplicate_cutoff = datetime.now(timezone.utc) - timedelta(seconds=2)
    existing = await db.execute(
        select(NotificationRecord)
        .where(NotificationRecord.message == mock_message)
        .where(NotificationRecord.timestamp >= duplicate_cutoff)
        .order_by(NotificationRecord.timestamp.desc())
        .limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return

    notification = await notifications.create_notification(db, mock_message, notification_type)
    await status.set_status("running", "Agent produced a new attention signal")
    await notifications.push_notification(notification)
    await status.set_status("standby", "No active agent jobs")


async def _is_mailbox_connected(db: AsyncSession) -> bool:
    settings = await preferences.get_settings(db)
    email_provider = normalize_email_provider(settings.get("email_provider"))
    oauth = get_oauth_module(email_provider)
    oauth_missing_settings = await oauth.get_missing_required_settings(db)
    return oauth.is_authenticated() and len(oauth_missing_settings) == 0


async def _reject_mailbox_interaction(
    websocket: WebSocket,
    db: AsyncSession,
    *,
    notification_id: str | None,
) -> None:
    message = "Mailbox is disconnected. Open Settings and reconnect before sending commands."

    await _send_json_if_connected(
        websocket,
        {
            "type": "recognized_action",
            "action": None,
            "recognized": False,
            "label": "Mailbox is disconnected",
        },
    )

    turn = await conversation_turns.create_conversation_turn(
        db,
        text=message,
        role="assistant",
        mode="system",
        session_id=None,
        source="mailbox_disconnected",
        notification_id=notification_id,
    )
    if turn is not None:
        turn_payload = turn.model_dump() if hasattr(turn, "model_dump") else turn.dict()
        await _send_json_if_connected(websocket, {"type": "conversation_turn", "turn": turn_payload})


async def _process_user_command(
    websocket: WebSocket,
    db: AsyncSession,
    *,
    text: str,
    notification_id: str | None,
    mode: str,
    source: str,
    session_id: str | None,
) -> None:
    if source == "realtime_transcript_final":
        cleaned_text = trim_stt_noise_prefix(text)
        if cleaned_text != text:
            logger.info(
                "process_user_command_trimmed_stt_noise original=%r cleaned=%r",
                _safe_log_text(text),
                _safe_log_text(cleaned_text),
            )
        text = cleaned_text

    correlation_id = f"ws-{id(websocket)}:cmd-{session_id or 'none'}"
    has_user_feedback = bool(text.strip())
    processing_started = has_user_feedback

    logger.info(
        "process_user_command text=%r notification_id=%s mode=%s source=%s has_user_feedback=%s",
        _safe_log_text(text),
        notification_id,
        mode,
        source,
        has_user_feedback,
    )
    control_kind, control_normalized = _classify_control_intent(text)
    logger.info(
        "process_user_command_control_intent kind=%s normalized=%r notification_id=%s",
        control_kind,
        _safe_log_text(control_normalized),
        notification_id,
    )

    turn = await conversation_turns.create_conversation_turn(
        db,
        text=text,
        role="user",
        mode=mode,
        session_id=session_id,
        source=source,
        notification_id=notification_id,
    )
    if turn is not None:
        turn_payload = turn.model_dump() if hasattr(turn, "model_dump") else turn.dict()
        if not await _send_json_if_connected(websocket, {"type": "conversation_turn", "turn": turn_payload}):
            logger.info("process_user_command_aborted_client_disconnected")
            return

    async def run_follow_up_command():
        logger.info("calling handle_speech_command_from_transcript text=%r", _safe_log_text(text))
        outcome = await handle_speech_command_from_transcript(
            db,
            notification_id=notification_id,
            transcript_text=text,
            correlation_id=correlation_id,
        )
        logger.info("handle_speech_command_from_transcript returned result=%s", outcome.result)
        return outcome

    outcome = await execute_service_interaction(
        websocket,
        db,
        show_processing=processing_started,
        operation=run_follow_up_command,
    )

    if not await _send_json_if_connected(
        websocket,
        {
            "type": "recognized_action",
            "action": outcome.result,
            "recognized": outcome.result is not None,
            "label": _format_recognized_action_label(outcome.result),
        },
    ):
        logger.info("process_user_command_result_dropped_client_disconnected")
        return

    if outcome.display_text:
        result_turn = await conversation_turns.create_conversation_turn(
            db,
            text=outcome.display_text,
            role="assistant",
            mode=mode,
            session_id=session_id,
            source="service_execution_result",
            notification_id=notification_id,
        )
        if result_turn is not None:
            result_turn_payload = result_turn.model_dump() if hasattr(result_turn, "model_dump") else result_turn.dict()
            await _send_json_if_connected(websocket, {"type": "conversation_turn", "turn": result_turn_payload})


async def handle_text_command(websocket: WebSocket, message: dict, db: AsyncSession) -> None:
    text = str(message.get("text", "")).strip()
    if not text:
        return

    notification_id = str(message.get("notification_id", "")).strip() or None
    if not await _is_mailbox_connected(db):
        await _reject_mailbox_interaction(
            websocket,
            db,
            notification_id=notification_id,
        )
        return

    await status.set_status("running", "Processing typed command")
    await _send_json_if_connected(websocket, {"type": "transcript_final", "text": text})

    try:
        await _process_user_command(
            websocket,
            db,
            text=text,
            notification_id=notification_id,
            mode="typed",
            source="typed_command",
            session_id=None,
        )
    finally:
        await status.set_status("standby", "No active agent jobs")


async def handle_audio_start(websocket: WebSocket, message: dict, db: AsyncSession) -> None:
    """Handle audio start event."""
    notification_context_id = str(message.get("notification_id", "")).strip() or None
    if not await _is_mailbox_connected(db):
        await _reject_mailbox_interaction(
            websocket,
            db,
            notification_id=notification_context_id,
        )
        await _send_json_if_connected(
            websocket,
            {
                "type": "transcript_partial",
                "text": "Mailbox is disconnected. Open Settings to reconnect.",
            }
        )
        return

    await status.set_status("running", "Listening for push-to-talk")
    config = await get_speech_config(db)
    app_settings = await preferences.get_settings(db)
    set_trace_enabled(app_settings.get("enable_transcription_trace", False))
    trace = TranscriptionTrace(
        mode="push-to-talk",
        wake_word_required=False,
        wake_word="",
        provider=config.provider,
        model=config.model,
    )
    trace.log_frontend_audio_start()

    async def persist_final_transcript(text: str, transcript_mode: str, session_id: str | None) -> None:
        try:
            # Realtime callbacks run in background tasks after this handler returns,
            # so they must use their own short-lived session instead of the caller's.
            async with db_session() as callback_db:
                await _process_user_command(
                    websocket,
                    callback_db,
                    text=text,
                    notification_id=notification_context_id,
                    mode=transcript_mode,
                    source="realtime_transcript_final",
                    session_id=session_id,
                )
        except Exception:
            logger.exception("persist_final_transcript_failed")

    transcriber = RealtimeTranscriber(
        client_ws=websocket,
        trace=trace,
        on_final_transcript=persist_final_transcript,
    )
    try:
        await transcriber.start(config)
    except RealtimeTranscriptionError as exc:
        logger.exception("Failed to start realtime transcription session")
        trace.log_error(source="startup", message=str(exc))
        trace.log_session_summary()
        await _send_json_if_connected(websocket, {"type": "transcript_partial", "text": str(exc)})
        await status.set_status("error", "Realtime transcription configuration error")
        return
    except Exception as exc:
        logger.exception("Unexpected failure while starting realtime transcription session")
        trace.log_error(source="startup", message=str(exc))
        trace.log_session_summary()
        await _send_json_if_connected(
            websocket,
            {
                "type": "transcript_partial",
                "text": f"Failed to start realtime transcription: {exc}",
            }
        )
        await status.set_status("error", "Realtime transcription startup failed")
        return

    _live_transcribers[id(websocket)] = transcriber
    logger.info("realtime_transcription_started")
    await _send_json_if_connected(websocket, {"type": "transcript_partial", "text": "Listening..."})


async def handle_audio_blob(
    websocket: WebSocket, message: dict, session_audio_bytes: int
) -> int:
    """Handle audio chunk. Returns updated session_audio_bytes."""
    audio_b64 = str(message.get("audio_base64", "")).strip()
    if not audio_b64:
        return session_audio_bytes

    if len(audio_b64) > _MAX_AUDIO_B64_CHARS:
        await _send_json_if_connected(
            websocket,
            {
                "type": "protocol_error",
                "detail": "Audio chunk payload is too large.",
                "message_type": "audio_blob",
            }
        )
        return session_audio_bytes

    transcriber = _live_transcribers.get(id(websocket))
    if transcriber is None:
        await _send_json_if_connected(
            websocket,
            {
                "type": "transcript_partial",
                "text": "Realtime session is not active. Start listening again.",
            }
        )
        return session_audio_bytes

    try:
        chunk_bytes = int(message.get("bytes", 0) or 0)
    except (TypeError, ValueError):
        await _send_json_if_connected(
            websocket,
            {
                "type": "protocol_error",
                "detail": "Audio chunk byte size must be an integer.",
                "message_type": "audio_blob",
            }
        )
        return session_audio_bytes

    if chunk_bytes <= 0 or chunk_bytes > _MAX_AUDIO_CHUNK_BYTES:
        await _send_json_if_connected(
            websocket,
            {
                "type": "protocol_error",
                "detail": "Audio chunk byte size is invalid.",
                "message_type": "audio_blob",
            }
        )
        return session_audio_bytes

    if session_audio_bytes + chunk_bytes > _MAX_SESSION_AUDIO_BYTES:
        await _send_json_if_connected(
            websocket,
            {
                "type": "protocol_error",
                "detail": "Audio session byte limit exceeded. Stop and start listening again.",
                "message_type": "audio_blob",
            }
        )
        return session_audio_bytes

    if transcriber.trace is not None:
        transcriber.trace.log_frontend_audio_chunk(byte_count=chunk_bytes)
    await transcriber.append_audio(audio_b64, chunk_bytes)
    await transcriber.maybe_commit_live()
    session_audio_bytes += chunk_bytes
    logger.debug("realtime_chunk_forwarded bytes=%s", chunk_bytes)
    return session_audio_bytes


async def handle_audio_stop(websocket: WebSocket) -> None:
    """Handle audio stop event."""
    transcriber = _live_transcribers.pop(id(websocket), None)
    if transcriber is not None:
        if transcriber.trace is not None:
            transcriber.trace.log_frontend_audio_stop()
        logger.info("realtime_stop_requested")
        await transcriber.commit()
        await transcriber.persist_fallback_transcript_if_needed()
        await transcriber.flush_pending_final_dispatch()
        logger.info("realtime_commit_completed_closing_upstream")
        await transcriber.close()
        logger.debug("realtime_upstream_closed")

    await status.set_status("standby", "No active agent jobs")


async def handle_dismiss_notification(message: dict, db: AsyncSession) -> None:
    """Handle dismiss request and broadcast updated notification record."""
    notification_id = str(message.get("id", "")).strip()
    if not notification_id:
        return

    updated = await notifications.dismiss_notification(db, notification_id)
    if updated is None:
        return

    await notifications.push_notification(updated)


async def handle_ws_disconnect(websocket: WebSocket) -> None:
    transcriber = _live_transcribers.pop(id(websocket), None)
    if transcriber is not None:
        if transcriber.trace is not None:
            transcriber.trace.log_error(source="websocket", message="Frontend websocket disconnected")
        await transcriber.close()
    await status.set_status("standby", "No active agent jobs")
