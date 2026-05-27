import { Box, Drawer, Paper, ScrollArea, Text } from "@mantine/core";
import type { AgentStatus, CalendarProposal, ConversationTurn, EmailDraft, FollowUpItem, Notification, OAuthStatus } from "../../lib/api";
import type { SeverityPalette } from "../../lib/severity";
import { NoNotifications } from "../NoNotifications";
import { NotificationPanel } from "../NotificationPanel";
import { PushToTalkHint } from "../PushToTalkHint.tsx";
import { TitleBar } from "../TitleBar";

type MainWindowShellProps = {
  activePalette: SeverityPalette | null;
  isExpandedReview: boolean;
  isAlwaysOnTop: boolean;
  isRecording: boolean;
  unreadCount: number;
  agentStatus: AgentStatus;
  oauthStatus: OAuthStatus;
  onStartDragging: (event: React.MouseEvent<HTMLElement>) => void;
  onOpenHistory: () => void;
  onOpenSettings: () => void;
  onOpenManual: () => void;
  onToggleAlwaysOnTop: () => void;
  onClose: () => void | Promise<void>;
  activeNotification: Notification | null;
  activeNotificationTurns: ConversationTurn[];
  notificationMessageOverride: string | null;
  activeNotificationTranscript: string;
  audioControls: React.ReactNode;
  activeFollowUp: FollowUpItem | null;
  activeDraft: EmailDraft | null;
  draftRecipient: string;
  draftSubject: string;
  draftBody: string;
  draftSyncHint: string | null;
  draftActionError: string | null;
  isDraftSaving: boolean;
  onDraftRecipientChange: (value: string) => void;
  onDraftSubjectChange: (value: string) => void;
  onDraftBodyChange: (value: string) => void;
  onDraftUseSuggestion: (value: string) => void;
  onDraftSave: () => void;
  onDraftSend: () => void;
  onDraftCancel: () => void;
  activeCalendarProposal: CalendarProposal | null;
  calendarError: string | null;
  isCalendarPlanning: boolean;
  isCalendarSaving: boolean;
  proposalTitle: string;
  proposalStartAtInput: string;
  proposalEndAtInput: string;
  proposalAttendeesInput: string;
  proposalNotes: string;
  onProposalTitleChange: (value: string) => void;
  onProposalStartAtChange: (value: string) => void;
  onProposalEndAtChange: (value: string) => void;
  onProposalAttendeesChange: (value: string) => void;
  onProposalNotesChange: (value: string) => void;
  onCalendarApprove: () => void;
  onCalendarCancel: () => void;
  isFeedbackProcessing: boolean;
  onDismiss: () => void;
  isDismissingNotification: boolean;
  liveTranscript: string;
  recognizedActionLabel: string | null;
  isHistoryOpen: boolean;
  onHistoryClose: () => void;
  historyContent: React.ReactNode;
};

export function MainWindowShell({
  activePalette,
  isExpandedReview,
  isAlwaysOnTop,
  isRecording,
  unreadCount,
  agentStatus,
  oauthStatus,
  onStartDragging,
  onOpenHistory,
  onOpenSettings,
  onOpenManual,
  onToggleAlwaysOnTop,
  onClose,
  activeNotification,
  activeNotificationTurns,
  notificationMessageOverride,
  activeNotificationTranscript,
  audioControls,
  activeFollowUp,
  activeDraft,
  draftRecipient,
  draftSubject,
  draftBody,
  draftSyncHint,
  draftActionError,
  isDraftSaving,
  onDraftRecipientChange,
  onDraftSubjectChange,
  onDraftBodyChange,
  onDraftUseSuggestion,
  onDraftSave,
  onDraftSend,
  onDraftCancel,
  activeCalendarProposal,
  calendarError,
  isCalendarPlanning,
  isCalendarSaving,
  proposalTitle,
  proposalStartAtInput,
  proposalEndAtInput,
  proposalAttendeesInput,
  proposalNotes,
  onProposalTitleChange,
  onProposalStartAtChange,
  onProposalEndAtChange,
  onProposalAttendeesChange,
  onProposalNotesChange,
  onCalendarApprove,
  onCalendarCancel,
  isFeedbackProcessing,
  onDismiss,
  isDismissingNotification,
  liveTranscript,
  recognizedActionLabel,
  isHistoryOpen,
  onHistoryClose,
  historyContent,
}: MainWindowShellProps) {
  return (
    <Box
      component="main"
      w="100%"
      h="100vh"
      style={{
        overflow: "hidden",
        border: activePalette
          ? `1px solid ${activePalette.panelBorder}`
          : "1px solid rgba(234, 88, 12, 0.16)",
        background:
          activePalette?.panelBg ??
          "linear-gradient(to bottom left, rgba(255, 148, 25, 0.7) 0%, rgba(255, 137, 64, 0.6) 30%, rgba(255, 213, 192, 0.48) 40%, #fff3e8 65%, #ffffff 100%)",
        backdropFilter: "blur(18px)",
        display: "flex",
        flexDirection: "column",
        transition: "background 220ms ease, border-color 220ms ease",
      }}
    >
      <TitleBar
        onStartDragging={onStartDragging}
        onOpenHistory={onOpenHistory}
        onOpenSettings={onOpenSettings}
        onOpenManual={onOpenManual}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onClose}
        notificationCount={unreadCount}
        isAlwaysOnTop={isAlwaysOnTop}
        isRecording={isRecording}
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
      />

      <ScrollArea
        type="auto"
        offsetScrollbars="present"
        scrollbarSize={10}
        style={{
          flex: 1,
          minHeight: 0,
        }}
        styles={{
          viewport: {
            padding: 8,
          },
          scrollbar: {
            background: "transparent",
          },
          thumb: {
            backgroundColor: "rgba(234, 88, 12, 0.33)",
            border: "2px solid rgba(255, 243, 232, 0.9)",
          },
        }}
      >
        <Paper
          withBorder
          radius="md"
          p="xs"
          bg="rgba(255, 255, 255, 0.55)"
          style={{
            borderColor: activePalette?.panelBorder ?? "rgba(234, 88, 12, 0.16)",
            border: `1px solid ${activePalette?.panelBorder ?? "rgba(234, 88, 12, 0.16)"}`,
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-start",
            borderRadius: 8,
            paddingTop: 20,
          }}
        >
          <Box
            style={{
              flex: 1,
              minHeight: 0,
              opacity: isExpandedReview ? 1 : 0.98,
              transform: isExpandedReview ? "translateY(0)" : "translateY(3px)",
              transition: "opacity 180ms ease, transform 180ms ease",
              willChange: "opacity, transform",
            }}
          >
            {activeNotification && activePalette ? (
              <NotificationPanel
                notification={{
                  ...activeNotification,
                  message: notificationMessageOverride ?? activeNotification.message,
                }}
                linkedTurns={activeNotificationTurns}
                palette={activePalette}
                liveTranscript={activeNotificationTranscript}
                audioControls={audioControls}
                mailboxConnected={oauthStatus.authenticated}
                onOpenSettings={onOpenSettings}
                followUpDetails={activeFollowUp}
                activeDraft={activeDraft}
                draftRecipient={draftRecipient}
                draftSubject={draftSubject}
                draftBody={draftBody}
                isDraftSaving={isDraftSaving}
                draftActionError={draftActionError}
                onDraftRecipientChange={onDraftRecipientChange}
                onDraftSubjectChange={onDraftSubjectChange}
                onDraftBodyChange={onDraftBodyChange}
                onDraftUseSuggestion={onDraftUseSuggestion}
                draftSyncHint={draftSyncHint}
                onDraftSave={onDraftSave}
                onDraftSend={onDraftSend}
                onDraftCancel={onDraftCancel}
                activeCalendarProposal={activeCalendarProposal}
                calendarError={calendarError}
                isCalendarPlanning={isCalendarPlanning}
                isCalendarSaving={isCalendarSaving}
                proposalTitle={proposalTitle}
                proposalStartAtInput={proposalStartAtInput}
                proposalEndAtInput={proposalEndAtInput}
                proposalAttendeesInput={proposalAttendeesInput}
                proposalNotes={proposalNotes}
                onProposalTitleChange={onProposalTitleChange}
                onProposalStartAtChange={onProposalStartAtChange}
                onProposalEndAtChange={onProposalEndAtChange}
                onProposalAttendeesChange={onProposalAttendeesChange}
                onProposalNotesChange={onProposalNotesChange}
                onCalendarApprove={onCalendarApprove}
                onCalendarCancel={onCalendarCancel}
                isFeedbackProcessing={isFeedbackProcessing}
                onOpenHistory={onOpenHistory}
                onDismiss={onDismiss}
                isDismissingNotification={isDismissingNotification}
              />
            ) : (
              <NoNotifications
                liveTranscript={liveTranscript}
                audioControls={audioControls}
                isFeedbackProcessing={isFeedbackProcessing}
                recognizedActionLabel={recognizedActionLabel}
                mailboxConnected={oauthStatus.authenticated}
                onOpenSettings={onOpenSettings}
              />
            )}
          </Box>
        </Paper>
      </ScrollArea>

      <PushToTalkHint />

      <Drawer
        opened={isHistoryOpen}
        onClose={onHistoryClose}
        title="History"
        position="right"
        size="sm"
        padding="xs"
        styles={{
          content: {
            display: "flex",
            flexDirection: "column",
          },
          header: {
            paddingTop: 6,
            paddingBottom: 6,
            minHeight: "auto",
            flexShrink: 0,
          },
          body: {
            flex: 1,
            minHeight: 0,
            overflow: "hidden",
            paddingTop: 0,
          },
          title: {
            fontSize: 14,
            fontWeight: 500,
          },
        }}
      >
        {historyContent ?? (
          <Text size="xs" c="dimmed" p="sm">
            Loading history...
          </Text>
        )}
      </Drawer>
    </Box>
  );
}
