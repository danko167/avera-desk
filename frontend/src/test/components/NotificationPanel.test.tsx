import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import type { NotificationPanelProps } from "../../components/notification-panel";
import { NotificationPanel } from "../../components/NotificationPanel";
import { getSeverityPalette } from "../../lib/severity";
import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";

vi.mock("@danko167/narrative-loader", () => ({
  NarrativeLoader: () => <div data-testid="narrative-loader" />,
}));

vi.mock("react-textarea-autosize", () => ({
  __esModule: true,
  default: forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
    function MockTextareaAutosize(props, ref) {
      return <textarea {...props} ref={ref} />;
    }
  ),
}));

function createDefaultProps(overrides: Partial<NotificationPanelProps> = {}): NotificationPanelProps {
  return {
    notification: {
      id: "notif-1",
      message: "Please prepare a draft reply.",
      type: "warning",
      timestamp: "2026-05-25T10:00:00Z",
      read: false,
      details: null,
      dismissed_at: null,
      source_email_id: null,
      llm_prompt_tokens: null,
      llm_completion_tokens: null,
      llm_total_tokens: null,
    },
    linkedTurns: [],
    palette: getSeverityPalette("warning"),
    liveTranscript: "",
    audioControls: <div data-testid="audio-controls">Audio controls</div>,
    mailboxConnected: true,
    onOpenSettings: vi.fn(),
    followUpDetails: null,
    activeDraft: null,
    draftRecipient: "",
    draftSubject: "",
    draftBody: "",
    draftSyncHint: null,
    draftActionError: null,
    isDraftSaving: false,
    onDraftRecipientChange: vi.fn(),
    onDraftSubjectChange: vi.fn(),
    onDraftBodyChange: vi.fn(),
    onDraftUseSuggestion: vi.fn(),
    onDraftSave: vi.fn(),
    onDraftSend: vi.fn(),
    onDraftCancel: vi.fn(),
    activeCalendarProposal: null,
    calendarError: null,
    isCalendarPlanning: false,
    isCalendarSaving: false,
    proposalTitle: "",
    proposalStartAtInput: "",
    proposalEndAtInput: "",
    proposalAttendeesInput: "",
    proposalNotes: "",
    onProposalTitleChange: vi.fn(),
    onProposalStartAtChange: vi.fn(),
    onProposalEndAtChange: vi.fn(),
    onProposalAttendeesChange: vi.fn(),
    onProposalNotesChange: vi.fn(),
    onCalendarApprove: vi.fn(),
    onCalendarCancel: vi.fn(),
    isFeedbackProcessing: false,
    onOpenHistory: vi.fn(),
    onDismiss: vi.fn(),
    isDismissingNotification: false,
    ...overrides,
  };
}

function renderNotificationPanel(overrides: Partial<NotificationPanelProps> = {}) {
  const props = createDefaultProps(overrides);
  return render(
    <MantineProvider>
      <NotificationPanel {...props} />
    </MantineProvider>
  );
}

describe("NotificationPanel", () => {
  it("shows disconnected mailbox card when mailbox is not connected", () => {
    renderNotificationPanel({ mailboxConnected: false });

    expect(screen.getByText("Mailbox is disconnected")).toBeInTheDocument();
    expect(screen.queryByTestId("audio-controls")).not.toBeInTheDocument();
  });

  it("renders audio controls when mailbox is connected", () => {
    renderNotificationPanel({ mailboxConnected: true });

    expect(screen.getByTestId("audio-controls")).toBeInTheDocument();
  });

  it("shows draft confirmation for pending drafts", () => {
    renderNotificationPanel({
      activeDraft: {
        id: "draft-1",
        mode: "reply",
        status: "pending",
        recipient_email: "alex@example.com",
        subject: "Re: Meeting",
        body: "Thanks, I can do tomorrow.",
        source_email_id: null,
        source_notification_id: null,
        send_notification_id: null,
        suggestions: [],
        created_at: "2026-05-25T09:00:00Z",
        updated_at: "2026-05-25T09:10:00Z",
        sent_at: null,
      },
      draftRecipient: "alex@example.com",
      draftSubject: "Re: Meeting",
      draftBody: "Thanks, I can do tomorrow.",
    });

    expect(screen.getByText("Email draft confirmation")).toBeInTheDocument();
    expect(screen.getByText("Send now")).toBeInTheDocument();
  });

  it("shows calendar planning when notification includes a calendar tag", () => {
    renderNotificationPanel({
      notification: {
        ...createDefaultProps().notification,
        message: "[cal:abc-123] Plan a meeting",
      },
    });

    expect(screen.getByText("Calendar planning")).toBeInTheDocument();
    expect(screen.getByLabelText("Notes (optional)")).toBeInTheDocument();
  });
});
