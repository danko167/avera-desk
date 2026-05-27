export type NotificationDetails = {
  kind?: "email_message" | "email_draft" | "follow_up_reminder" | "calendar_proposal" | null;
  variant?: string | null;
  headline?: string | null;
  context_line?: string | null;
  instruction?: string | null;
  source_notification_id?: string | null;
  from_email?: string | null;
  subject?: string | null;
  body_preview?: string | null;
  original_email_text?: string | null;
  followup_id?: string | null;
  followup_summary?: string | null;
};

export type Notification = {
  id: string;
  message: string;
  type: "info" | "warning" | "error" | "success";
  source_email_id?: string | null;
  details?: NotificationDetails | null;
  timestamp: string;
  read: boolean;
  dismissed_at?: string | null;
  llm_prompt_tokens?: number | null;
  llm_completion_tokens?: number | null;
  llm_total_tokens?: number | null;
};

export type AgentStatus = {
  state: "standby" | "running" | "error";
  detail: string;
  updated_at: string;
};

export type AppSettings = {
  enable_transcription_trace: boolean;
  enable_text_input_mode: boolean;
  email_sync_interval_minutes: number;
  app_api_base_url: string;
  app_ws_url: string;
  email_provider: "m365" | "gmail";
  m365_client_id: string;
  m365_tenant_id: string;
  m365_redirect_url: string;
  gmail_client_id: string;
  gmail_client_secret_configured: boolean;
  gmail_redirect_url: string;
  speech_provider: "openai" | "openrouter" | "local";
  speech_model: string;
  speech_base_url: string;
  speech_api_key_configured: boolean;
  llm_provider: "openai" | "openrouter" | "local";
  llm_model: string;
  llm_base_url: string;
  llm_api_key_configured: boolean;
};

export type AiConnectionTestRequest = {
  provider: AppSettings["llm_provider"];
  model: string;
  base_url: string;
  api_key?: string | null;
};

export type AiConnectionTestResult = {
  ok: boolean;
  provider: AppSettings["llm_provider"];
  model: string;
  base_url: string;
  endpoint: string;
  detail: string;
};

export type LlmUsageSummary = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  record_count: number;
};

export type OAuthStatus = {
  authenticated: boolean;
  connected_mailbox?: string | null;
  persistence: "none" | "session" | "persistent";
  setup_required?: boolean;
  missing_settings?: string[];
};

export type ConversationTurn = {
  id: string;
  text: string;
  role: string;
  mode: string;
  session_id?: string | null;
  source?: string | null;
  notification_id?: string | null;
  timestamp: string;
};

export type WsClientMessage =
  | { type: "ping" }
  | { type: "text_command"; text: string; notification_id?: string }
  | {
    type: "audio_start";
    notification_id?: string;
  }
  | { type: "audio_stop" }
  | { type: "audio_blob"; bytes: number; audio_base64: string; audio_format: "pcm16" }
  | { type: "dismiss_notification"; id: string }
  | { type: "mock_trigger"; message?: string; notification_type?: Notification["type"] }
  | { type: "set_status"; state: AgentStatus["state"]; detail?: string };

export type WsServerMessage =
  | { type: "snapshot"; status: AgentStatus; notifications: Notification[] }
  | { type: "status"; status: AgentStatus }
  | { type: "notification"; notification: Notification }
  | { type: "conversation_turn"; turn: ConversationTurn }
  | { type: "close_window_after"; delay_ms?: number; only_if_last_unread?: boolean }
  | { type: "feedback_processing"; active: boolean }
  | { type: "recognized_action"; action: string | null; recognized: boolean; label: string }
  | { type: "transcript_partial"; text: string }
  | { type: "transcript_final"; text: string }
  | { type: "protocol_error"; detail: string; message_type?: string | null }
  | { type: "pong" };

export type ConnectionSettings = Pick<AppSettings, "app_api_base_url" | "app_ws_url">;

export type EmailSyncResponse = {
  status?: string;
  provider?: string;
  count: number;
  new_emails: Array<{
    id: string;
    subject: string;
    from: string;
    body_preview: string;
  }>;
};

export type EmailSyncStatusResponse = {
  authenticated: boolean;
  sync_interval_minutes: number;
  next_sync_at: string | null;
  last_sync_started_at: string | null;
  last_sync_finished_at: string | null;
  seconds_until_next_sync: number | null;
};

export type FollowUpItem = {
  id: string;
  email_id: string;
  status: "open" | "snoozed" | "dismissed" | "done";
  summary: string;
  requested_action?: string | null;
  confidence: number;
  next_reminder_at: string;
  extracted_due_at?: string | null;
  snoozed_until?: string | null;
  reminder_count: number;
  created_at: string;
  updated_at: string;
};

export type ParsedFollowUpNotification = {
  followUpId: string;
  message: string;
};

export type EmailDraftSuggestion = {
  email: string;
  label?: string | null;
  confidence: number;
};

export type EmailDraft = {
  id: string;
  mode: "new_email" | "reply";
  status: "pending" | "sent" | "canceled";
  recipient_email?: string | null;
  subject: string;
  body: string;
  source_email_id?: string | null;
  source_notification_id?: string | null;
  send_notification_id?: string | null;
  suggestions: EmailDraftSuggestion[];
  created_at: string;
  updated_at: string;
  sent_at?: string | null;
};

export type ParsedDraftNotification = {
  draftId: string;
  message: string;
};

export type ParsedCalendarProposalNotification = {
  proposalId: string;
  message: string;
};

export type CalendarProposalAction =
  | "create_event"
  | "reschedule_event"
  | "suggest_alternatives"
  | "draft_invite_reply";

export type CalendarProposalConflict = {
  event_id?: string | null;
  title: string;
  start_at: string;
  end_at: string;
  reason?: string | null;
};

export type CalendarProposalOption = {
  start_at: string;
  end_at: string;
  reason?: string | null;
  confidence: number;
};

export type CalendarAttendeeSuggestion = {
  email: string;
  label?: string | null;
  confidence: number;
  source?: string | null;
};

export type CalendarProposal = {
  id: string;
  provider: "m365" | "gmail";
  action: CalendarProposalAction;
  status: "proposed" | "awaiting_user_decision" | "approved" | "rejected" | "canceled";
  title: string;
  start_at: string;
  end_at: string;
  timezone_name: string;
  attendees: string[];
  target_event_id?: string | null;
  source_email_id?: string | null;
  source_followup_id?: string | null;
  source_notification_id?: string | null;
  conflicts: CalendarProposalConflict[];
  options: CalendarProposalOption[];
  attendee_suggestions: CalendarAttendeeSuggestion[];
  notes?: string | null;
  created_at: string;
  updated_at: string;
  approved_at?: string | null;
  rejected_at?: string | null;
};

export type UpdateCalendarProposalPayload = {
  title?: string;
  start_at?: string;
  end_at?: string;
  timezone_name?: string;
  attendees?: string[];
  target_event_id?: string | null;
  conflicts?: CalendarProposalConflict[];
  options?: CalendarProposalOption[];
  notes?: string | null;
};

export type CalendarPlanningRequest = {
  action: CalendarProposalAction;
  title?: string;
  desired_start_at: string;
  desired_end_at?: string;
  duration_minutes?: number;
  timezone_name?: string;
  attendees?: string[];
  interval_minutes?: number;
  search_window_hours?: number;
  target_event_id?: string | null;
  source_email_id?: string | null;
  source_followup_id?: string | null;
  source_notification_id?: string | null;
  notes?: string | null;
};

export type CalendarPlanningResult = {
  proposal: CalendarProposal;
  conflicts: CalendarProposalConflict[];
  options: CalendarProposalOption[];
  reasoning: string;
};

export type UpdateAppSettings = AppSettings & {
  gmail_client_secret?: string | null;
  speech_api_key?: string | null;
  llm_api_key?: string | null;
};

export function isDraftActionable(draft: EmailDraft | null | undefined): boolean {
  return draft?.status === "pending";
}

export function isCalendarProposalActionable(proposal: CalendarProposal | null | undefined): boolean {
  return proposal?.status === "proposed" || proposal?.status === "awaiting_user_decision";
}

export function shouldShowCalendarReview(
  proposal: CalendarProposal | null | undefined,
  hasCalendarNotification: boolean,
): boolean {
  return (hasCalendarNotification && proposal == null) || isCalendarProposalActionable(proposal);
}

export function shouldExpandWindowForNotification(notification: Notification): boolean {
  const kind = notification.details?.kind;
  const variant = notification.details?.variant;

  if (kind === "email_draft") {
    return true;
  }

  if (kind === "calendar_proposal") {
    return variant === "ready" || variant === "ready_with_conflicts";
  }

  return false;
}

export function isEmailNotification(notification: Notification): boolean {
  const details = notification.details;
  if (!details) {
    return false;
  }

  if (details.kind === "email_message") {
    return true;
  }

  return Boolean((details.from_email ?? "").trim() || (details.subject ?? "").trim());
}

export function getNotificationHeadline(notification: Notification): string {
  const headline = notification.details?.headline?.trim();
  return headline && headline.length > 0 ? headline : notification.message;
}

export function getNotificationInstruction(notification: Notification): string | null {
  const instruction = notification.details?.instruction?.trim();
  return instruction && instruction.length > 0 ? instruction : null;
}

export function getNotificationContextLine(notification: Notification): string | null {
  const contextLine = notification.details?.context_line?.trim();
  return contextLine && contextLine.length > 0 ? contextLine : null;
}
