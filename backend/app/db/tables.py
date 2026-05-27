import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class NotificationRecord(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="info")
    source_email_id: Mapped[str | None] = mapped_column(String, nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    # NULL = active/visible; set to mark as dismissed (moved to history)
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ConversationTurnRecord(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    mode: Mapped[str] = mapped_column(String, nullable=False, default="push-to-talk")
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    notification_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("notifications.id"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Setting(Base):
    """Key/value store for user preferences and app configuration."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class EmailItem(Base):
    """Inbox email items synced from Microsoft Graph."""

    __tablename__ = "email_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Graph message ID
    subject: Mapped[str] = mapped_column(String, nullable=False)
    from_address: Mapped[str] = mapped_column(String, nullable=False)
    from_name: Mapped[str | None] = mapped_column(String, nullable=True)
    body_preview: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    delta_token: Mapped[str | None] = mapped_column(String, nullable=True)  # sync cursor
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FollowUpItem(Base):
    """Tracked obligation extracted from an email."""

    __tablename__ = "follow_up_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("email_items.id"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    requested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    extracted_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_reminder_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class FollowUpActionRecord(Base):
    """Audit history for follow-up actions and reminders."""

    __tablename__ = "follow_up_actions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    follow_up_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("follow_up_items.id"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SpeechReminderRecord(Base):
    """Persisted reminder created from speech command parsing."""

    __tablename__ = "speech_reminders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    source_notification_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("notifications.id"),
        nullable=True,
    )
    source_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("notifications.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class LlmUsageRecord(Base):
    __tablename__ = "llm_usage_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    interaction_kind: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    source_email_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notification_id: Mapped[str | None] = mapped_column(String, nullable=True)
    conversation_turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EmailDraftRecord(Base):
    """Pending outbound emails that require explicit user confirmation."""

    __tablename__ = "email_drafts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="new_email")
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    recipient_email: Mapped[str | None] = mapped_column(String, nullable=True)
    subject: Mapped[str] = mapped_column(String, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_email_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_notification_id: Mapped[str | None] = mapped_column(String, nullable=True)
    send_notification_id: Mapped[str | None] = mapped_column(String, nullable=True)
    suggestions_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarProposalRecord(Base):
    """Pending calendar action proposals that require explicit user approval."""

    __tablename__ = "calendar_proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String, nullable=False, default="m365")
    action: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="awaiting_user_decision",
    )
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String, nullable=False, default="UTC")
    attendees_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    target_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_email_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_followup_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_notification_id: Mapped[str | None] = mapped_column(String, nullable=True)
    conflicts_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    options_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
