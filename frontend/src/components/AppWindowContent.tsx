import { lazy, Suspense, type MouseEvent, type ReactNode } from "react";
import { Text } from "@mantine/core";
import {
  type AgentStatus,
  type AppSettings,
  type CalendarProposal,
  type ConversationTurn,
  type EmailDraft,
  type FollowUpItem,
  type Notification,
  type OAuthStatus,
  type ParsedCalendarProposalNotification,
  type ParsedDraftNotification,
  type ParsedFollowUpNotification,
} from "../lib/api";
import type { SeverityPalette } from "../lib/severity";
import type { BootstrapErrorInfo } from "../lib/startup";
import { MainWindowShell } from "./shells/MainWindowShell";
import {
  SettingsLoadingFallback,
  SettingsWindowShell,
} from "./shells/SettingsWindowShell";
import { ManualWindowShell } from "./shells/ManualWindowShell";
import { ManualGuideContent } from "./manual/ManualGuideContent";
import { SetupRequiredShell } from "./shells/SetupRequiredShell";

const NotificationHistory = lazy(async () => {
  const module = await import("./NotificationHistory");
  return { default: module.NotificationHistory };
});

const StartupGate = lazy(async () => {
  const module = await import("./startup/StartupGate");
  return { default: module.StartupGate };
});

const SettingsPanel = lazy(async () => {
  const module = await import("./SettingsPanel");
  return { default: module.SettingsPanel };
});

type AppWindowContentProps = {
  isBootstrapReady: boolean;
  bootstrapError: BootstrapErrorInfo | null;
  isSetupRequired: boolean;
  missingSettings: string[];
  isStartupWindow: boolean;
  isSettingsWindow: boolean;
  isManualWindow: boolean;
  appSettings: AppSettings;
  oauthStatus: OAuthStatus;
  agentStatus: AgentStatus;
  isAlwaysOnTop: boolean;
  isRecording: boolean;
  activePalette: SeverityPalette | null;
  unreadCount: number;
  shouldExpandMainWindow: boolean;
  notifications: Notification[];
  conversationTurns: ConversationTurn[];
  activeNotificationId: string | null;
  activeNotification: Notification | null;
  activeNotificationTurns: ConversationTurn[];
  activeNotificationTranscript: string;
  activeFollowUp: FollowUpItem | null;
  activeDraft: EmailDraft | null;
  draftRecipient: string;
  draftSubject: string;
  draftBody: string;
  draftSyncHint: string | null;
  draftActionError: string | null;
  isDraftSaving: boolean;
  activeCalendarProposal: CalendarProposal | null;
  calendarError: string | null;
  isCalendarPlanning: boolean;
  isCalendarSaving: boolean;
  proposalTitle: string;
  proposalStartAtInput: string;
  proposalEndAtInput: string;
  proposalAttendeesInput: string;
  proposalNotes: string;
  isFeedbackProcessing: boolean;
  isDismissingNotification: boolean;
  liveTranscript: string;
  recognizedActionLabel: string | null;
  isHistoryOpen: boolean;
  parsedActiveFollowUp: ParsedFollowUpNotification | null;
  parsedActiveDraft: ParsedDraftNotification | null;
  parsedActiveCalendarProposal: ParsedCalendarProposalNotification | null;
  audioControls: ReactNode;
  onStartDragging: (event: MouseEvent<HTMLElement>) => void;
  onToggleAlwaysOnTop: () => void;
  onHideWindow: () => Promise<void>;
  onQuitApplication: () => Promise<void>;
  onCloseCurrentWindow: () => Promise<void>;
  onOpenSettingsWindow: () => Promise<void>;
  onOpenManualWindow: () => Promise<void>;
  onOpenStartupWindow: () => Promise<void>;
  onAppSettingsChange: (next: AppSettings) => void;
  onOAuthStatusChange: (status: OAuthStatus) => void;
  onHistoryOpen: () => void;
  onHistoryClose: () => void;
  onSelectNotification: (id: string) => void;
  onDismissNotification: () => void;
  onDraftRecipientChange: (value: string) => void;
  onDraftSubjectChange: (value: string) => void;
  onDraftBodyChange: (value: string) => void;
  onDraftUseSuggestion: (value: string) => void;
  onDraftSave: () => void;
  onDraftSend: () => void;
  onDraftCancel: () => void;
  onProposalTitleChange: (value: string) => void;
  onProposalStartAtChange: (value: string) => void;
  onProposalEndAtChange: (value: string) => void;
  onProposalAttendeesChange: (value: string) => void;
  onProposalNotesChange: (value: string) => void;
  onCalendarApprove: () => void;
  onCalendarCancel: () => void;
};

export function AppWindowContent(props: AppWindowContentProps) {
  const {
    isBootstrapReady,
    bootstrapError,
    isSetupRequired,
    missingSettings,
    isStartupWindow,
    isSettingsWindow,
    isManualWindow,
    appSettings,
    oauthStatus,
    agentStatus,
    isAlwaysOnTop,
    isRecording,
    activePalette,
    unreadCount,
    shouldExpandMainWindow,
    notifications,
    conversationTurns,
    activeNotificationId,
    activeNotification,
    activeNotificationTurns,
    activeNotificationTranscript,
    activeFollowUp,
    activeDraft,
    draftRecipient,
    draftSubject,
    draftBody,
    draftSyncHint,
    draftActionError,
    isDraftSaving,
    activeCalendarProposal,
    calendarError,
    isCalendarPlanning,
    isCalendarSaving,
    proposalTitle,
    proposalStartAtInput,
    proposalEndAtInput,
    proposalAttendeesInput,
    proposalNotes,
    isFeedbackProcessing,
    isDismissingNotification,
    liveTranscript,
    recognizedActionLabel,
    isHistoryOpen,
    parsedActiveFollowUp,
    parsedActiveDraft,
    parsedActiveCalendarProposal,
    audioControls,
    onStartDragging,
    onToggleAlwaysOnTop,
    onHideWindow,
    onQuitApplication,
    onCloseCurrentWindow,
    onOpenSettingsWindow,
    onOpenManualWindow,
    onOpenStartupWindow,
    onAppSettingsChange,
    onOAuthStatusChange,
    onHistoryOpen,
    onHistoryClose,
    onSelectNotification,
    onDismissNotification,
    onDraftRecipientChange,
    onDraftSubjectChange,
    onDraftBodyChange,
    onDraftUseSuggestion,
    onDraftSave,
    onDraftSend,
    onDraftCancel,
    onProposalTitleChange,
    onProposalStartAtChange,
    onProposalEndAtChange,
    onProposalAttendeesChange,
    onProposalNotesChange,
    onCalendarApprove,
    onCalendarCancel,
  } = props;

  if (!isBootstrapReady && bootstrapError === null) {
    return (
      <Suspense fallback={null}>
        <StartupGate
          mode="loading"
          agentStatus={agentStatus}
          oauthStatus={oauthStatus}
          isAlwaysOnTop={isAlwaysOnTop}
          onStartDragging={onStartDragging}
          onToggleAlwaysOnTop={onToggleAlwaysOnTop}
          onClose={isStartupWindow ? onQuitApplication : onHideWindow}
        />
      </Suspense>
    );
  }

  if (bootstrapError !== null) {
    return (
      <Suspense fallback={null}>
        <StartupGate
          mode="error"
          agentStatus={agentStatus}
          oauthStatus={oauthStatus}
          isAlwaysOnTop={isAlwaysOnTop}
          onStartDragging={onStartDragging}
          onToggleAlwaysOnTop={onToggleAlwaysOnTop}
          onClose={isStartupWindow ? onQuitApplication : onHideWindow}
          bootstrapError={bootstrapError}
        />
      </Suspense>
    );
  }

  if (isStartupWindow && isSetupRequired) {
    return (
      <Suspense fallback={null}>
        <StartupGate
          mode="setup"
          agentStatus={agentStatus}
          oauthStatus={oauthStatus}
          isAlwaysOnTop={isAlwaysOnTop}
          onStartDragging={onStartDragging}
          onToggleAlwaysOnTop={onToggleAlwaysOnTop}
          onClose={isStartupWindow ? onQuitApplication : onHideWindow}
          settings={appSettings}
          missingSettings={missingSettings}
          onSettingsChange={onAppSettingsChange}
          onOAuthStatusChange={onOAuthStatusChange}
        />
      </Suspense>
    );
  }

  if (isManualWindow) {
    return (
      <ManualWindowShell
        isAlwaysOnTop={isAlwaysOnTop}
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
        onStartDragging={onStartDragging}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onCloseCurrentWindow}
      >
        <ManualGuideContent
          isSetupRequired={isSetupRequired}
          onOpenSetup={() => {
            void onOpenStartupWindow();
          }}
        />
      </ManualWindowShell>
    );
  }

  if (isSetupRequired) {
    return (
      <SetupRequiredShell
        isSettingsWindow={isSettingsWindow}
        isAlwaysOnTop={isAlwaysOnTop}
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
        onStartDragging={onStartDragging}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={isSettingsWindow ? onCloseCurrentWindow : onHideWindow}
        onOpenSetup={async () => {
          await onOpenStartupWindow();
          await onHideWindow();
        }}
      />
    );
  }

  if (isSettingsWindow) {
    return (
      <SettingsWindowShell
        isAlwaysOnTop={isAlwaysOnTop}
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
        onStartDragging={onStartDragging}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onCloseCurrentWindow}
      >
        <Suspense fallback={<SettingsLoadingFallback />}>
          <SettingsPanel
            settings={appSettings}
            onChange={onAppSettingsChange}
            oauthStatus={oauthStatus}
            onOAuthStatusChange={onOAuthStatusChange}
          />
        </Suspense>
      </SettingsWindowShell>
    );
  }

  const historyContent = (
    <Suspense fallback={<Text size="xs" c="dimmed" p="sm">Loading history...</Text>}>
      <NotificationHistory
        notifications={notifications}
        turns={conversationTurns}
        activeNotificationId={activeNotificationId}
        onSelectNotification={(id) => {
          onSelectNotification(id);
          onHistoryClose();
        }}
      />
    </Suspense>
  );

  const notificationMessageOverride =
    parsedActiveFollowUp?.message
    ?? parsedActiveDraft?.message
    ?? parsedActiveCalendarProposal?.message
    ?? null;

  return (
    <MainWindowShell
      activePalette={activePalette}
      isExpandedReview={shouldExpandMainWindow}
      isAlwaysOnTop={isAlwaysOnTop}
      isRecording={isRecording}
      unreadCount={unreadCount}
      agentStatus={agentStatus}
      oauthStatus={oauthStatus}
      onStartDragging={onStartDragging}
      onOpenHistory={onHistoryOpen}
      onOpenSettings={() => {
        void onOpenSettingsWindow();
      }}
      onOpenManual={() => {
        void onOpenManualWindow();
      }}
      onToggleAlwaysOnTop={onToggleAlwaysOnTop}
      onClose={onHideWindow}
      activeNotification={activeNotification}
      activeNotificationTurns={activeNotificationTurns}
      notificationMessageOverride={notificationMessageOverride}
      activeNotificationTranscript={activeNotificationTranscript}
      audioControls={audioControls}
      activeFollowUp={activeFollowUp}
      activeDraft={activeDraft}
      draftRecipient={draftRecipient}
      draftSubject={draftSubject}
      draftBody={draftBody}
      draftSyncHint={draftSyncHint}
      draftActionError={draftActionError}
      isDraftSaving={isDraftSaving}
      onDraftRecipientChange={onDraftRecipientChange}
      onDraftSubjectChange={onDraftSubjectChange}
      onDraftBodyChange={onDraftBodyChange}
      onDraftUseSuggestion={onDraftUseSuggestion}
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
      onDismiss={onDismissNotification}
      isDismissingNotification={isDismissingNotification}
      liveTranscript={liveTranscript}
      recognizedActionLabel={recognizedActionLabel}
      isHistoryOpen={isHistoryOpen}
      onHistoryClose={onHistoryClose}
      historyContent={historyContent}
    />
  );
}
