export const API_ENDPOINTS = {
  health: "/health",
  localAuthToken: "/api/local-auth/token",
  localAuthWsTicket: "/api/local-auth/ws-ticket",
  settings: "/api/settings",
  testAiConnection: "/api/settings/test-ai-connection",
  llmUsageSummary: "/api/settings/llm-usage-summary",
  clearAiSecrets: "/api/settings/clear-ai-secrets",
  conversationTurns: "/api/conversation-turns",
  oauthStatus: "/api/oauth/status",
  oauthLoginUrl: "/api/oauth/login-url",
  oauthLogout: "/api/oauth/logout",
  emailSync: "/api/emails/sync",
  emailSyncStatus: "/api/emails/sync-status",
  calendarUpcomingEvents: "/api/calendar/events/upcoming",
  calendarAvailability: "/api/calendar/availability",
  calendarProposalPlan: "/api/calendar-proposals/plan",
} as const;

export const WS_ENDPOINTS = {
  websocket: "/ws",
} as const;

export function buildConversationTurnsUrl(limit: number): string {
  return `${API_ENDPOINTS.conversationTurns}?limit=${limit}`;
}

export function buildFollowUpByIdUrl(followUpId: string): string {
  return `/api/followups/${encodeURIComponent(followUpId)}`;
}

export function buildEmailDraftByIdUrl(draftId: string): string {
  return `/api/email-drafts/${encodeURIComponent(draftId)}`;
}

export function buildEmailDraftSendUrl(draftId: string): string {
  return `${buildEmailDraftByIdUrl(draftId)}/send`;
}

export function buildEmailDraftCancelUrl(draftId: string): string {
  return `${buildEmailDraftByIdUrl(draftId)}/cancel`;
}

export function buildCalendarProposalByIdUrl(proposalId: string): string {
  return `/api/calendar-proposals/${encodeURIComponent(proposalId)}`;
}

export function buildCalendarProposalApproveUrl(proposalId: string): string {
  return `${buildCalendarProposalByIdUrl(proposalId)}/approve`;
}

export function buildCalendarProposalRejectUrl(proposalId: string): string {
  return `${buildCalendarProposalByIdUrl(proposalId)}/reject`;
}

export function buildCalendarProposalCancelUrl(proposalId: string): string {
  return `${buildCalendarProposalByIdUrl(proposalId)}/cancel`;
}

export function buildCalendarUpcomingEventsUrl(startAt: string, endAt: string, limit = 25): string {
  const params = new URLSearchParams({
    start_at: startAt,
    end_at: endAt,
    limit: String(limit),
  });
  return `${API_ENDPOINTS.calendarUpcomingEvents}?${params.toString()}`;
}
