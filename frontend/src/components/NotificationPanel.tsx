import { Stack } from "@mantine/core";
import { isEmailNotification, shouldShowCalendarReview } from "../lib/api";
import {
  CalendarPlanningSection,
  DraftConfirmationSection,
  type NotificationPanelProps,
  NotificationActionsRow,
  NotificationContextSection,
  NotificationHeader,
} from "./notification-panel";

export function NotificationPanel({
  notification,
  linkedTurns,
  palette,
  liveTranscript,
  audioControls,
  mailboxConnected,
  onOpenSettings,
  followUpDetails,
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
}: NotificationPanelProps) {
  const emailNotification = isEmailNotification(notification);
  const hasCalendarTag = /\[cal:[a-zA-Z0-9\-]+\]/.test(notification.message);
  const showCalendarPanel = shouldShowCalendarReview(activeCalendarProposal, hasCalendarTag);
  const interactionsBlocked = !mailboxConnected;
  const controlsDisabled = interactionsBlocked || isFeedbackProcessing;

  return (
    <Stack justify="flex-start" style={{ height: "100%" }} gap={6}>
      <NotificationHeader
        notification={notification}
        palette={palette}
        hasCalendarTag={hasCalendarTag}
        isEmailNotification={emailNotification}
      />

      <Stack gap={6}>
        <NotificationContextSection
          interactionsBlocked={interactionsBlocked}
          onOpenSettings={onOpenSettings}
          audioControls={audioControls}
          isFeedbackProcessing={isFeedbackProcessing}
          liveTranscript={liveTranscript}
          linkedTurns={linkedTurns}
          followUpDetails={followUpDetails}
        />

        <DraftConfirmationSection
          activeDraft={activeDraft}
          controlsDisabled={controlsDisabled}
          isDraftSaving={isDraftSaving}
          draftRecipient={draftRecipient}
          draftSubject={draftSubject}
          draftBody={draftBody}
          draftSyncHint={draftSyncHint}
          draftActionError={draftActionError}
          onDraftRecipientChange={onDraftRecipientChange}
          onDraftSubjectChange={onDraftSubjectChange}
          onDraftBodyChange={onDraftBodyChange}
          onDraftUseSuggestion={onDraftUseSuggestion}
          onDraftCancel={onDraftCancel}
          onDraftSend={onDraftSend}
        />

        <CalendarPlanningSection
          showCalendarPanel={showCalendarPanel}
          controlsDisabled={controlsDisabled}
          isCalendarPlanning={isCalendarPlanning}
          isCalendarSaving={isCalendarSaving}
          proposalTitle={proposalTitle}
          proposalStartAtInput={proposalStartAtInput}
          proposalEndAtInput={proposalEndAtInput}
          proposalAttendeesInput={proposalAttendeesInput}
          proposalNotes={proposalNotes}
          calendarError={calendarError}
          activeCalendarProposal={activeCalendarProposal}
          onProposalTitleChange={onProposalTitleChange}
          onProposalStartAtChange={onProposalStartAtChange}
          onProposalEndAtChange={onProposalEndAtChange}
          onProposalAttendeesChange={onProposalAttendeesChange}
          onProposalNotesChange={onProposalNotesChange}
          onCalendarApprove={onCalendarApprove}
          onCalendarCancel={onCalendarCancel}
        />

        <NotificationActionsRow
          badgeColor={palette.badge}
          onDismiss={onDismiss}
          isDismissingNotification={isDismissingNotification}
        />
      </Stack>
    </Stack>
  );
}
