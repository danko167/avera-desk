import type {
  ParsedCalendarProposalNotification,
  ParsedDraftNotification,
  ParsedFollowUpNotification,
} from "./types";

function parseTaggedNotificationMessage(
  message: string,
  tag: "fu" | "draft" | "cal",
  defaultPrefix: string,
): { id: string; message: string } | null {
  const escapedTag = tag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = message.match(new RegExp(`^(.+?)\\s+\\[${escapedTag}:([a-zA-Z0-9\\-]+)\\]\\s*(.*)$`));
  if (!match) {
    return null;
  }

  const prefix = match[1]?.trim() ?? defaultPrefix;
  const id = match[2]?.trim();
  const suffix = match[3]?.trim() ?? "";

  if (!id) {
    return null;
  }

  return {
    id,
    message: suffix ? `${prefix} ${suffix}` : prefix,
  };
}

export function parseFollowUpNotification(message: string): ParsedFollowUpNotification | null {
  const parsed = parseTaggedNotificationMessage(message, "fu", "Follow-up");
  if (!parsed) {
    return null;
  }

  return {
    followUpId: parsed.id,
    message: parsed.message,
  };
}

export function parseDraftNotification(message: string): ParsedDraftNotification | null {
  const parsed = parseTaggedNotificationMessage(message, "draft", "Draft");
  if (!parsed) {
    return null;
  }

  return {
    draftId: parsed.id,
    message: parsed.message,
  };
}

export function parseCalendarProposalNotification(message: string): ParsedCalendarProposalNotification | null {
  const parsed = parseTaggedNotificationMessage(message, "cal", "Calendar proposal");
  if (!parsed) {
    return null;
  }

  return {
    proposalId: parsed.id,
    message: parsed.message,
  };
}
