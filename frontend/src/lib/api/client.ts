import {
  API_ENDPOINTS,
  buildCalendarProposalApproveUrl,
  buildCalendarProposalByIdUrl,
  buildCalendarProposalCancelUrl,
  buildCalendarProposalRejectUrl,
  buildEmailDraftByIdUrl,
  buildEmailDraftCancelUrl,
  buildEmailDraftSendUrl,
  buildConversationTurnsUrl,
  buildFollowUpByIdUrl,
} from "../endpoints";
import { apiFetch, requestJson } from "./runtime";
import type {
  AiConnectionTestRequest,
  AiConnectionTestResult,
  AppSettings,
  CalendarPlanningRequest,
  CalendarPlanningResult,
  CalendarProposal,
  ConversationTurn,
  EmailDraft,
  EmailSyncResponse,
  EmailSyncStatusResponse,
  FollowUpItem,
  LlmUsageSummary,
  OAuthStatus,
  UpdateAppSettings,
  UpdateCalendarProposalPayload,
} from "./types";

export async function fetchAppSettings(): Promise<AppSettings> {
  return requestJson<AppSettings>(API_ENDPOINTS.settings, "App settings", {
    method: "GET",
    timeoutMs: 5000,
  });
}

export async function updateAppSettings(payload: UpdateAppSettings): Promise<AppSettings> {
  const response = await apiFetch(API_ENDPOINTS.settings, "Update settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Failed to update settings (${response.status})`);
  }

  return response.json();
}

export async function testAiConnection(payload: AiConnectionTestRequest): Promise<AiConnectionTestResult> {
  return requestJson<AiConnectionTestResult>(API_ENDPOINTS.testAiConnection, "AI connection test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function clearAiSecrets(): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.clearAiSecrets, "Clear AI secrets", {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Failed to clear AI secrets (${response.status})`);
  }
}

export async function fetchLlmUsageSummary(): Promise<LlmUsageSummary> {
  return requestJson<LlmUsageSummary>(API_ENDPOINTS.llmUsageSummary, "LLM usage summary", {
    method: "GET",
    timeoutMs: 5000,
  });
}

export async function fetchConversationTurns(limit = 200): Promise<ConversationTurn[]> {
  const response = await apiFetch(buildConversationTurnsUrl(limit), "Conversation turns", {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch conversation turns (${response.status})`);
  }

  return response.json();
}

export async function fetchOAuthStatus(resolveMailbox = false): Promise<OAuthStatus> {
  const url = resolveMailbox
    ? `${API_ENDPOINTS.oauthStatus}?resolve_mailbox=true`
    : API_ENDPOINTS.oauthStatus;
  return requestJson<OAuthStatus>(url, "OAuth status", {
    method: "GET",
    timeoutMs: 5000,
  });
}

export async function fetchOAuthLoginUrl(): Promise<string> {
  const response = await apiFetch(API_ENDPOINTS.oauthLoginUrl, "OAuth login URL", {
    method: "GET",
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `OAuth login URL failed (${response.status}): ${body.slice(0, 180)}`
    );
  }

  const data = await response.json();
  if (!data?.login_url) {
    throw new Error("OAuth login URL is missing from backend response");
  }

  return data.login_url;
}

export async function logoutOAuth(): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.oauthLogout, "OAuth logout", {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`OAuth logout failed (${response.status})`);
  }
}

export async function syncEmailsNow(): Promise<EmailSyncResponse> {
  const response = await apiFetch(API_ENDPOINTS.emailSync, "Manual sync", {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Manual sync failed (${response.status})`);
  }

  return response.json();
}

export async function fetchEmailSyncStatus(): Promise<EmailSyncStatusResponse> {
  const response = await apiFetch(API_ENDPOINTS.emailSyncStatus, "Sync status", {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Sync status failed (${response.status})`);
  }

  return response.json();
}

export async function fetchFollowUpById(followUpId: string): Promise<FollowUpItem> {
  const response = await apiFetch(buildFollowUpByIdUrl(followUpId), "Follow-up fetch", {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Follow-up fetch failed (${response.status})`);
  }

  return response.json();
}

export async function fetchEmailDraftById(draftId: string): Promise<EmailDraft> {
  const response = await apiFetch(buildEmailDraftByIdUrl(draftId), "Email draft fetch", {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Email draft fetch failed (${response.status})`);
  }

  return response.json();
}

export async function updateEmailDraft(
  draftId: string,
  payload: { recipient_email?: string | null; subject?: string | null; body?: string | null }
): Promise<EmailDraft> {
  const response = await apiFetch(buildEmailDraftByIdUrl(draftId), "Email draft update", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Email draft update failed (${response.status})`);
  }

  return response.json();
}

export async function sendEmailDraft(draftId: string): Promise<EmailDraft> {
  const response = await apiFetch(buildEmailDraftSendUrl(draftId), "Email draft send", {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Email draft send failed (${response.status})`);
  }

  return response.json();
}

export async function cancelEmailDraft(draftId: string): Promise<EmailDraft> {
  const response = await apiFetch(buildEmailDraftCancelUrl(draftId), "Email draft cancel", {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Email draft cancel failed (${response.status})`);
  }

  return response.json();
}

export async function planCalendarProposal(payload: CalendarPlanningRequest): Promise<CalendarPlanningResult> {
  return requestJson<CalendarPlanningResult>(API_ENDPOINTS.calendarProposalPlan, "Calendar planning", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCalendarProposalById(proposalId: string): Promise<CalendarProposal> {
  return requestJson<CalendarProposal>(buildCalendarProposalByIdUrl(proposalId), "Calendar proposal", {
    method: "GET",
  });
}

export async function updateCalendarProposal(
  proposalId: string,
  payload: UpdateCalendarProposalPayload
): Promise<CalendarProposal> {
  return requestJson<CalendarProposal>(buildCalendarProposalByIdUrl(proposalId), "Calendar proposal update", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function approveCalendarProposal(proposalId: string): Promise<CalendarProposal> {
  return requestJson<CalendarProposal>(buildCalendarProposalApproveUrl(proposalId), "Calendar proposal approve", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function rejectCalendarProposal(
  proposalId: string,
  reason?: string | null
): Promise<CalendarProposal> {
  return requestJson<CalendarProposal>(buildCalendarProposalRejectUrl(proposalId), "Calendar proposal reject", {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export async function cancelCalendarProposal(proposalId: string): Promise<CalendarProposal> {
  return requestJson<CalendarProposal>(buildCalendarProposalCancelUrl(proposalId), "Calendar proposal cancel", {
    method: "POST",
    body: JSON.stringify({}),
  });
}
