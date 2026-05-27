import {
  isCalendarProposalActionable,
  isDraftActionable,
  parseCalendarProposalNotification,
  parseDraftNotification,
  parseFollowUpNotification,
  shouldExpandWindowForNotification,
  type Notification,
} from "../../lib/api";

describe("notification parsing", () => {
  it("parses follow-up notification tags", () => {
    const parsed = parseFollowUpNotification("Follow-up reminder [fu:fu-123] Send status update");

    expect(parsed).toEqual({
      followUpId: "fu-123",
      message: "Follow-up reminder Send status update",
    });
  });

  it("parses draft notification tags", () => {
    const parsed = parseDraftNotification("Draft ready [draft:draft-456] Check before sending");

    expect(parsed).toEqual({
      draftId: "draft-456",
      message: "Draft ready Check before sending",
    });
  });

  it("parses calendar proposal tags", () => {
    const parsed = parseCalendarProposalNotification("Calendar proposal [cal:cal-789] Needs your review");

    expect(parsed).toEqual({
      proposalId: "cal-789",
      message: "Calendar proposal Needs your review",
    });
  });

  it("returns null when message has no known tag", () => {
    expect(parseFollowUpNotification("No structured tag here")).toBeNull();
    expect(parseDraftNotification("No structured tag here")).toBeNull();
    expect(parseCalendarProposalNotification("No structured tag here")).toBeNull();
  });
});

describe("notification actionability", () => {
  it("evaluates draft actionability", () => {
    expect(isDraftActionable({ status: "pending" } as never)).toBe(true);
    expect(isDraftActionable({ status: "sent" } as never)).toBe(false);
    expect(isDraftActionable(null)).toBe(false);
  });

  it("evaluates calendar proposal actionability", () => {
    expect(isCalendarProposalActionable({ status: "proposed" } as never)).toBe(true);
    expect(isCalendarProposalActionable({ status: "awaiting_user_decision" } as never)).toBe(true);
    expect(isCalendarProposalActionable({ status: "approved" } as never)).toBe(false);
  });
});

describe("notification window expansion", () => {
  const makeNotification = (details: Notification["details"]): Notification => ({
    id: "n1",
    message: "Sample",
    type: "info",
    details,
    timestamp: new Date().toISOString(),
    read: false,
  });

  it("always expands for draft notifications", () => {
    const notification = makeNotification({ kind: "email_draft", variant: null });
    expect(shouldExpandWindowForNotification(notification)).toBe(true);
  });

  it("expands for ready calendar proposals", () => {
    const ready = makeNotification({ kind: "calendar_proposal", variant: "ready" });
    const readyWithConflicts = makeNotification({
      kind: "calendar_proposal",
      variant: "ready_with_conflicts",
    });

    expect(shouldExpandWindowForNotification(ready)).toBe(true);
    expect(shouldExpandWindowForNotification(readyWithConflicts)).toBe(true);
  });

  it("does not expand for non-ready calendar variants", () => {
    const notification = makeNotification({ kind: "calendar_proposal", variant: "planning" });
    expect(shouldExpandWindowForNotification(notification)).toBe(false);
  });
});