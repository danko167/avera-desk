from typing import Literal

from pydantic import BaseModel, Field

NotificationType = Literal["info", "warning", "error", "success"]
AgentState = Literal["standby", "running", "error"]
OAuthPersistence = Literal["none", "session", "persistent"]
AiProvider = Literal["openai", "openrouter", "local"]
EmailProvider = Literal["m365", "gmail"]
FollowUpStatus = Literal["open", "snoozed", "dismissed", "done"]
EmailDraftStatus = Literal["pending", "sent", "canceled"]
EmailDraftMode = Literal["new_email", "reply"]
CalendarProposalProvider = Literal["m365", "gmail"]
CalendarProposalAction = Literal[
    "create_event",
    "reschedule_event",
    "suggest_alternatives",
    "draft_invite_reply",
]
CalendarProposalStatus = Literal[
    "proposed",
    "awaiting_user_decision",
    "approved",
    "rejected",
    "canceled",
]
class NotificationDetails(BaseModel):
    kind: str | None = None
    variant: str | None = None
    headline: str | None = None
    context_line: str | None = None
    instruction: str | None = None
    source_notification_id: str | None = None
    from_email: str | None = None
    subject: str | None = None
    body_preview: str | None = None
    original_email_text: str | None = None
    followup_id: str | None = None
    followup_summary: str | None = None


class Notification(BaseModel):
    id: str
    message: str
    type: NotificationType
    source_email_id: str | None = None
    details: NotificationDetails | None = None
    timestamp: str
    read: bool = False
    dismissed_at: str | None = None
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None

class LlmUsageSummary(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    record_count: int = 0


class AgentStatus(BaseModel):
    state: AgentState
    detail: str
    updated_at: str


class AppSettings(BaseModel):
    enable_transcription_trace: bool = False
    enable_text_input_mode: bool = False
    email_sync_interval_minutes: int = 5
    app_api_base_url: str
    app_ws_url: str
    email_provider: EmailProvider = "m365"
    m365_client_id: str = ""
    m365_tenant_id: str = ""
    m365_redirect_url: str = "http://localhost:8000/api/oauth/callback"
    gmail_client_id: str = ""
    gmail_client_secret_configured: bool = False
    gmail_redirect_url: str = "http://localhost:8000/api/oauth/google/callback"
    speech_provider: AiProvider = "openai"
    speech_model: str = "whisper-1"
    speech_base_url: str = "https://api.openai.com/v1"
    speech_api_key_configured: bool = False
    llm_provider: AiProvider = "openai"
    llm_model: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key_configured: bool = False


class UpdateAppSettings(BaseModel):
    enable_transcription_trace: bool
    enable_text_input_mode: bool
    email_sync_interval_minutes: int = Field(ge=1, le=60)
    app_api_base_url: str
    app_ws_url: str
    email_provider: EmailProvider
    m365_client_id: str
    m365_tenant_id: str
    m365_redirect_url: str
    gmail_client_id: str
    gmail_client_secret: str | None = None
    gmail_redirect_url: str
    speech_provider: AiProvider
    speech_model: str
    speech_base_url: str
    speech_api_key: str | None = None
    llm_provider: AiProvider
    llm_model: str
    llm_base_url: str
    llm_api_key: str | None = None


class TestAiConnectionRequest(BaseModel):
    provider: AiProvider
    model: str
    base_url: str
    api_key: str | None = None


class TestAiConnectionResult(BaseModel):
    ok: bool
    provider: AiProvider
    model: str
    base_url: str
    endpoint: str
    detail: str


class ConversationTurn(BaseModel):
    id: str
    text: str
    role: str
    mode: str
    session_id: str | None = None
    source: str | None = None
    notification_id: str | None = None
    timestamp: str


class OAuthStatus(BaseModel):
    authenticated: bool
    connected_mailbox: str | None = None
    persistence: OAuthPersistence = "none"
    setup_required: bool = False
    missing_settings: list[str] = Field(default_factory=list)


class FollowUpItemDto(BaseModel):
    id: str
    email_id: str
    status: FollowUpStatus
    summary: str
    requested_action: str | None = None
    confidence: float
    next_reminder_at: str
    extracted_due_at: str | None = None
    snoozed_until: str | None = None
    reminder_count: int
    created_at: str
    updated_at: str


class EmailDraftSuggestionDto(BaseModel):
    email: str
    label: str | None = None
    confidence: float


class EmailDraftDto(BaseModel):
    id: str
    mode: EmailDraftMode
    status: EmailDraftStatus
    recipient_email: str | None = None
    subject: str
    body: str
    source_email_id: str | None = None
    source_notification_id: str | None = None
    send_notification_id: str | None = None
    suggestions: list[EmailDraftSuggestionDto] = Field(default_factory=list)
    created_at: str
    updated_at: str
    sent_at: str | None = None


class UpdateEmailDraftRequest(BaseModel):
    recipient_email: str | None = None
    subject: str | None = None
    body: str | None = None


class CalendarProposalConflictDto(BaseModel):
    event_id: str | None = None
    title: str
    start_at: str
    end_at: str
    reason: str | None = None


class CalendarProposalOptionDto(BaseModel):
    start_at: str
    end_at: str
    reason: str | None = None
    confidence: float = 0.0


class CalendarAttendeeSuggestionDto(BaseModel):
    email: str
    label: str | None = None
    confidence: float
    source: str | None = None


class CalendarProposalDto(BaseModel):
    id: str
    provider: CalendarProposalProvider
    action: CalendarProposalAction
    status: CalendarProposalStatus
    title: str
    start_at: str
    end_at: str
    timezone_name: str
    attendees: list[str] = Field(default_factory=list)
    target_event_id: str | None = None
    source_email_id: str | None = None
    source_followup_id: str | None = None
    source_notification_id: str | None = None
    conflicts: list[CalendarProposalConflictDto] = Field(default_factory=list)
    options: list[CalendarProposalOptionDto] = Field(default_factory=list)
    attendee_suggestions: list[CalendarAttendeeSuggestionDto] = Field(default_factory=list)
    notes: str | None = None
    created_at: str
    updated_at: str
    approved_at: str | None = None
    rejected_at: str | None = None


class CreateCalendarProposalRequest(BaseModel):
    provider: CalendarProposalProvider = "m365"
    action: CalendarProposalAction
    title: str = ""
    start_at: str
    end_at: str
    timezone_name: str = "UTC"
    attendees: list[str] = Field(default_factory=list)
    target_event_id: str | None = None
    source_email_id: str | None = None
    source_followup_id: str | None = None
    source_notification_id: str | None = None
    conflicts: list[CalendarProposalConflictDto] = Field(default_factory=list)
    options: list[CalendarProposalOptionDto] = Field(default_factory=list)
    notes: str | None = None


class UpdateCalendarProposalRequest(BaseModel):
    title: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    timezone_name: str | None = None
    attendees: list[str] | None = None
    target_event_id: str | None = None
    conflicts: list[CalendarProposalConflictDto] | None = None
    options: list[CalendarProposalOptionDto] | None = None
    notes: str | None = None


class RejectCalendarProposalRequest(BaseModel):
    reason: str | None = None


class CalendarAttendeeAvailabilityDto(BaseModel):
    status: str | None = None
    subject: str | None = None
    is_private: bool = False
    start_at: str | None = None
    end_at: str | None = None
    location: str | None = None


class CalendarAvailabilityDto(BaseModel):
    email: str
    availability_view: str
    items: list[CalendarAttendeeAvailabilityDto] = Field(default_factory=list)


class CalendarEventAttendeeDto(BaseModel):
    email: str | None = None
    name: str | None = None
    type: str | None = None
    status: str | None = None


class CalendarEventDto(BaseModel):
    id: str | None = None
    subject: str
    start_at: str | None = None
    end_at: str | None = None
    timezone: str = "UTC"
    is_all_day: bool = False
    show_as: str | None = None
    organizer_email: str | None = None
    organizer_name: str | None = None
    location: str | None = None
    attendees: list[CalendarEventAttendeeDto] = Field(default_factory=list)
    web_link: str | None = None
    online_meeting_url: str | None = None


class CalendarAvailabilityRequest(BaseModel):
    attendees: list[str] = Field(default_factory=list)
    start_at: str
    end_at: str
    interval_minutes: int = Field(default=30, ge=5, le=60)


class CalendarPlanningRequest(BaseModel):
    action: CalendarProposalAction
    title: str = ""
    desired_start_at: str
    desired_end_at: str | None = None
    duration_minutes: int = Field(default=30, ge=15, le=480)
    timezone_name: str = "UTC"
    attendees: list[str] = Field(default_factory=list)
    interval_minutes: int = Field(default=30, ge=5, le=60)
    search_window_hours: int = Field(default=24, ge=1, le=168)
    target_event_id: str | None = None
    source_email_id: str | None = None
    source_followup_id: str | None = None
    source_notification_id: str | None = None
    notes: str | None = None
    auto_shift_conflict_free_for_flexible_time: bool = False


class CalendarPlanningResultDto(BaseModel):
    proposal: CalendarProposalDto
    conflicts: list[CalendarProposalConflictDto] = Field(default_factory=list)
    options: list[CalendarProposalOptionDto] = Field(default_factory=list)
    reasoning: str
