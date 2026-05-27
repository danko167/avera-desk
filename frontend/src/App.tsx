import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchConversationTurns,
  getWebSocketUrl,
  isCalendarProposalActionable,
  isDraftActionable,
  type AgentStatus,
  type ConversationTurn,
  type Notification,
} from "./lib/api";
import { DEFAULT_AGENT_STATUS } from "./lib/startup";
import { getSeverityPalette } from "./lib/severity";
import { createLogger } from "./lib/logger";
import { useDraftManager } from "./hooks/useDraftManager";
import { useFollowUpDetails } from "./hooks/useFollowUpDetails";
import { useCalendarProposalManager } from "./hooks/useCalendarProposalManager";
import { useNotificationCenter } from "./hooks/useNotificationCenter";
import { useWindowManager } from "./hooks/useWindowManager";
import { useWebSocketConnection } from "./hooks/useWebSocketConnection";
import { useAppBootstrap } from "./hooks/useAppBootstrap";
import { useTranscriptState } from "./hooks/useTranscriptState";
import { useWsMessageHandler } from "./hooks/useWsMessageHandler";
import { useDesktopWindowActions } from "./hooks/useDesktopWindowActions";
import {
  getInitialWindowLabel,
  useAttentionEventBridge,
  useCurrentWindowLabel,
  useRendererDiagnostics,
} from "./hooks/useAppWindowRuntime";
import { AudioInput, type ListenPhase } from "./components/AudioInput";
import { TextCommandInput } from "./components/TextCommandInput";
import { AppWindowContent } from "./components/AppWindowContent";

const TRANSCRIPT_POST_PROCESSING_HOLD_MS = 1800;
const RECOGNIZED_ACTION_HOLD_MS = TRANSCRIPT_POST_PROCESSING_HOLD_MS;
const RECOGNIZED_ACTION_MAX_HOLD_MS = 6000;
const logger = createLogger("App");

function App() {
  const [windowLabel, setWindowLabel] = useState<string>(() => getInitialWindowLabel());
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [activeNotificationId, setActiveNotificationId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [conversationTurns, setConversationTurns] = useState<ConversationTurn[]>([]);
  const [agentStatus, setAgentStatus] = useState<AgentStatus>(DEFAULT_AGENT_STATUS);
  const [isFeedbackProcessing, setIsFeedbackProcessing] = useState(false);
  const [recognizedActionLabel, setRecognizedActionLabel] = useState<string | null>(null);
  const [pendingDismissIds, setPendingDismissIds] = useState<string[]>([]);

  const unreadCountRef = useRef(0);
  const feedbackProcessingDepthRef = useRef(0);
  const feedbackProcessingPrevRef = useRef(false);
  const conversationRefreshTimerRef = useRef<number | null>(null);
  const conversationRefreshRequestIdRef = useRef(0);
  const closeWindowTimerRef = useRef<number | null>(null);
  const postProcessingTranscriptResetTimerRef = useRef<number | null>(null);
  const recognizedActionResetTimerRef = useRef<number | null>(null);
  const recognizedActionFailsafeTimerRef = useRef<number | null>(null);

  const {
    appSettings,
    oauthStatus,
    hasLoadedAppSettings,
    hasLoadedOAuthStatus,
    bootstrapError,
    isLocalAuthReady,
    localAuthReadyNonce,
    setOAuthStatus,
    handleAppSettingsChange,
  } = useAppBootstrap();

  const {
    logFrontendDiagnostic,
    raiseMainWindow,
    completeStartupSetupWindow,
    quitApplication,
    closeCurrentWindow,
    openSettingsWindow,
    openManualWindow,
    openStartupWindow,
    setMainWindowExpanded,
  } = useDesktopWindowActions();

  useRendererDiagnostics(windowLabel, logFrontendDiagnostic);
  useCurrentWindowLabel(setWindowLabel);

  const clearCloseWindowTimer = useCallback(() => {
    if (closeWindowTimerRef.current !== null) {
      window.clearTimeout(closeWindowTimerRef.current);
      closeWindowTimerRef.current = null;
    }
  }, []);

  const { isAlwaysOnTop, hideWindow, toggleAlwaysOnTop, startDragging } =
    useWindowManager();

  const buildWebSocketUrl = useCallback(
    () => getWebSocketUrl(appSettings, { refreshWsTicket: true }),
    [appSettings.app_api_base_url, appSettings.app_ws_url, localAuthReadyNonce]
  );

  const refreshConversationTurns = useCallback(async () => {
    const requestId = ++conversationRefreshRequestIdRef.current;
    try {
      const turns = await fetchConversationTurns(200);
      if (requestId !== conversationRefreshRequestIdRef.current) {
        return;
      }
      setConversationTurns(turns);
    } catch (error) {
      logger.error("Failed to load conversation turns.", error);
    }
  }, []);

  const scheduleConversationRefreshes = useCallback((options?: { immediate?: boolean }) => {
    if (conversationRefreshTimerRef.current !== null) {
      window.clearTimeout(conversationRefreshTimerRef.current);
    }

    const delayMs = options?.immediate ? 0 : 220;
    conversationRefreshTimerRef.current = window.setTimeout(() => {
      conversationRefreshTimerRef.current = null;
      void refreshConversationTurns();
    }, delayMs);
  }, [refreshConversationTurns]);

  const {
    liveTranscript,
    isRecording,
    isListeningPrompt,
    setLiveTranscript,
    handleAudioChunk,
    handleListenStateChange,
    handleCloudSessionChange,
    handleTypedCommandSubmit,
    applyTranscriptPartialFromWs,
    applyTranscriptFinalFromWs,
    clearTranscriptResetTimer,
  } = useTranscriptState({
    activeNotificationId,
    scheduleConversationRefreshes,
    raiseMainWindow,
  });

  const {
    unreadNotifications: unreadNotificationsWithTranscript,
    activeNotification: activeNotificationWithTranscript,
    activeNotificationTurns: activeNotificationTurnsWithTranscript,
    activeNotificationTranscript: activeNotificationTranscriptWithTranscript,
    parsedActiveFollowUp: parsedActiveFollowUpWithTranscript,
    parsedActiveDraft: parsedActiveDraftWithTranscript,
    parsedActiveCalendarProposal: parsedActiveCalendarProposalWithTranscript,
  } = useNotificationCenter({
    notifications,
    activeNotificationId,
    conversationTurns,
    liveTranscript,
    isListeningPrompt,
  });

  useEffect(() => {
    unreadCountRef.current = unreadNotificationsWithTranscript.length;
  }, [unreadNotificationsWithTranscript]);

  const { activeFollowUp } = useFollowUpDetails(parsedActiveFollowUpWithTranscript);

  const {
    activeDraft,
    draftRecipient,
    draftSubject,
    draftBody,
    isDraftSaving,
    draftSyncHint,
    draftActionError,
    refreshActiveDraft,
    handleDraftSave,
    handleDraftSend,
    handleDraftCancel,
    setDraftRecipientDirty,
    setDraftSubjectDirty,
    setDraftBodyDirty,
  } = useDraftManager({
    parsedActiveDraft: parsedActiveDraftWithTranscript,
  });

  const {
    activeCalendarProposal,
    isCalendarPlanning,
    isCalendarSaving,
    calendarError,
    proposalTitle,
    proposalStartAtInput,
    proposalEndAtInput,
    proposalAttendeesInput,
    proposalNotes,
    setProposalTitle,
    setProposalStartAtInput,
    setProposalEndAtInput,
    setProposalAttendeesInput,
    setProposalNotes,
    saveCalendarProposalEdits,
    approveActiveCalendarProposal,
    cancelActiveCalendarProposal,
  } = useCalendarProposalManager({
    parsedActiveCalendarProposal: parsedActiveCalendarProposalWithTranscript,
  });

  const handleWsMessage = useWsMessageHandler({
    activeNotificationId,
    parsedActiveDraft: parsedActiveDraftWithTranscript,
    unreadCountRef,
    feedbackProcessingDepthRef,
    closeWindowTimerRef,
    scheduleConversationRefreshes,
    clearCloseWindowTimer,
    hideWindow,
    raiseMainWindow,
    setMainWindowExpanded,
    refreshActiveDraft,
    setAgentStatus,
    setIsFeedbackProcessing,
    setNotifications,
    setPendingDismissIds,
    setActiveNotificationId,
    setConversationTurns,
    setRecognizedActionLabel,
    applyTranscriptPartialFromWs,
    applyTranscriptFinalFromWs,
  });

  const { sendWsMessage } = useWebSocketConnection(
    handleWsMessage,
    buildWebSocketUrl,
    isLocalAuthReady,
  );

  useAttentionEventBridge(windowLabel, sendWsMessage);

  useEffect(() => {
    const wasProcessing = feedbackProcessingPrevRef.current;
    feedbackProcessingPrevRef.current = isFeedbackProcessing;

    if (!wasProcessing || isFeedbackProcessing) {
      return;
    }

    clearTranscriptResetTimer();

    if (postProcessingTranscriptResetTimerRef.current !== null) {
      window.clearTimeout(postProcessingTranscriptResetTimerRef.current);
      postProcessingTranscriptResetTimerRef.current = null;
    }

    if (liveTranscript.trim().length > 0 && !isListeningPrompt(liveTranscript)) {
      postProcessingTranscriptResetTimerRef.current = window.setTimeout(() => {
        setLiveTranscript((current) => (isListeningPrompt(current) ? current : ""));
        postProcessingTranscriptResetTimerRef.current = null;
      }, TRANSCRIPT_POST_PROCESSING_HOLD_MS);
    } else {
      setLiveTranscript("");
    }

    if (activeNotificationWithTranscript !== null) {
      return;
    }

    clearCloseWindowTimer();
    closeWindowTimerRef.current = window.setTimeout(() => {
      void hideWindow();
      closeWindowTimerRef.current = null;
    }, 900);
  }, [
    activeNotificationWithTranscript,
    clearCloseWindowTimer,
    clearTranscriptResetTimer,
    hideWindow,
    isFeedbackProcessing,
    isListeningPrompt,
    liveTranscript,
    setLiveTranscript,
  ]);

  useEffect(() => {
    if (recognizedActionResetTimerRef.current !== null) {
      window.clearTimeout(recognizedActionResetTimerRef.current);
      recognizedActionResetTimerRef.current = null;
    }

    if (recognizedActionFailsafeTimerRef.current !== null) {
      window.clearTimeout(recognizedActionFailsafeTimerRef.current);
      recognizedActionFailsafeTimerRef.current = null;
    }

    if (!recognizedActionLabel) {
      return;
    }

    recognizedActionFailsafeTimerRef.current = window.setTimeout(() => {
      setRecognizedActionLabel((current) => (current === recognizedActionLabel ? null : current));
      recognizedActionFailsafeTimerRef.current = null;
    }, RECOGNIZED_ACTION_MAX_HOLD_MS);

    if (!recognizedActionLabel || isFeedbackProcessing) {
      return () => {
        if (recognizedActionFailsafeTimerRef.current !== null) {
          window.clearTimeout(recognizedActionFailsafeTimerRef.current);
          recognizedActionFailsafeTimerRef.current = null;
        }
      };
    }

    recognizedActionResetTimerRef.current = window.setTimeout(() => {
      setRecognizedActionLabel((current) => (current === recognizedActionLabel ? null : current));
      recognizedActionResetTimerRef.current = null;
    }, RECOGNIZED_ACTION_HOLD_MS);

    return () => {
      if (recognizedActionResetTimerRef.current !== null) {
        window.clearTimeout(recognizedActionResetTimerRef.current);
        recognizedActionResetTimerRef.current = null;
      }
      if (recognizedActionFailsafeTimerRef.current !== null) {
        window.clearTimeout(recognizedActionFailsafeTimerRef.current);
        recognizedActionFailsafeTimerRef.current = null;
      }
    };
  }, [isFeedbackProcessing, recognizedActionLabel]);

  useEffect(() => {
    scheduleConversationRefreshes({ immediate: true });
  }, [scheduleConversationRefreshes]);

  useEffect(() => {
    if (!activeNotificationId) {
      setIsFeedbackProcessing(false);
      return;
    }
    scheduleConversationRefreshes();
  }, [activeNotificationId, scheduleConversationRefreshes]);

  useEffect(() => {
    if (!isHistoryOpen) {
      return;
    }
    scheduleConversationRefreshes();
  }, [isHistoryOpen, scheduleConversationRefreshes]);

  useEffect(() => {
    return () => {
      if (conversationRefreshTimerRef.current !== null) {
        window.clearTimeout(conversationRefreshTimerRef.current);
      }
      if (closeWindowTimerRef.current !== null) {
        window.clearTimeout(closeWindowTimerRef.current);
      }
      if (postProcessingTranscriptResetTimerRef.current !== null) {
        window.clearTimeout(postProcessingTranscriptResetTimerRef.current);
      }
      if (recognizedActionResetTimerRef.current !== null) {
        window.clearTimeout(recognizedActionResetTimerRef.current);
      }
      if (recognizedActionFailsafeTimerRef.current !== null) {
        window.clearTimeout(recognizedActionFailsafeTimerRef.current);
      }
    };
  }, []);

  const handleAudioChunkFromInput = useCallback((chunk: { audioBase64: string; bytes: number }) => {
    handleAudioChunk(sendWsMessage, chunk);
  }, [handleAudioChunk, sendWsMessage]);

  const handleListenStateChangeFromInput = useCallback((active: boolean, phase: ListenPhase) => {
    if (phase === "starting") {
      setRecognizedActionLabel(null);
    }
    handleListenStateChange(active, phase);
  }, [handleListenStateChange]);

  const handleCloudSessionChangeFromInput = useCallback((active: boolean) => {
    handleCloudSessionChange(sendWsMessage, active);
  }, [handleCloudSessionChange, sendWsMessage]);

  const handleTypedCommandSubmitFromInput = useCallback((text: string) => {
    setRecognizedActionLabel(null);
    handleTypedCommandSubmit(sendWsMessage, text);
  }, [handleTypedCommandSubmit, sendWsMessage]);

  const dismissNotificationById = useCallback((notificationId: string | null) => {
    if (!notificationId) {
      return;
    }

    setPendingDismissIds((current) => {
      if (current.includes(notificationId)) {
        return current;
      }
      return [...current, notificationId];
    });
    sendWsMessage(
      { type: "dismiss_notification", id: notificationId },
      { queueIfDisconnected: true }
    );
  }, [sendWsMessage]);

  const dismissCurrentNotification = useCallback(() => {
    dismissNotificationById(activeNotificationWithTranscript?.id ?? null);
  }, [activeNotificationWithTranscript, dismissNotificationById]);

  const scheduleCloseAfterDraftAction = useCallback((dismissedNotificationId: string | null) => {
    if (!dismissedNotificationId) {
      return;
    }

    clearCloseWindowTimer();
    closeWindowTimerRef.current = window.setTimeout(() => {
      const remainingUnread = unreadNotificationsWithTranscript.filter(
        (notification) => notification.id !== dismissedNotificationId
      );
      if (remainingUnread.length === 0) {
        void hideWindow();
      }
      closeWindowTimerRef.current = null;
    }, 4000);
  }, [clearCloseWindowTimer, hideWindow, unreadNotificationsWithTranscript]);

  const handleDraftSendAndDismiss = useCallback(async () => {
    const dismissedNotificationId = activeNotificationWithTranscript?.id ?? null;
    const sent = await handleDraftSend();
    if (sent) {
      dismissNotificationById(dismissedNotificationId);
      scheduleCloseAfterDraftAction(dismissedNotificationId);
    }
  }, [activeNotificationWithTranscript, dismissNotificationById, handleDraftSend, scheduleCloseAfterDraftAction]);

  const handleDraftCancelAndDismiss = useCallback(async () => {
    const dismissedNotificationId = activeNotificationWithTranscript?.id ?? null;
    const canceled = await handleDraftCancel();
    if (canceled) {
      dismissNotificationById(dismissedNotificationId);
      scheduleCloseAfterDraftAction(dismissedNotificationId);
    }
  }, [activeNotificationWithTranscript, dismissNotificationById, handleDraftCancel, scheduleCloseAfterDraftAction]);

  const activePalette = activeNotificationWithTranscript
    ? getSeverityPalette(activeNotificationWithTranscript.type)
    : null;

  const isBootstrapReady = hasLoadedAppSettings && hasLoadedOAuthStatus;
  const isSetupRequired = oauthStatus.setup_required === true;
  const missingSettings = oauthStatus.missing_settings ?? [];
  const isStartupWindow = windowLabel === "startup";
  const isSettingsWindow = windowLabel === "settings";
  const isManualWindow = windowLabel === "manual";

  useEffect(() => {
    if (!isStartupWindow) {
      return;
    }

    if (!isBootstrapReady || bootstrapError !== null || isSetupRequired) {
      return;
    }

    void completeStartupSetupWindow();
  }, [bootstrapError, completeStartupSetupWindow, isBootstrapReady, isSetupRequired, isStartupWindow]);

  const areCommandControlsDisabled = isFeedbackProcessing || !oauthStatus.authenticated;
  const isDismissingNotification = activeNotificationWithTranscript
    ? pendingDismissIds.includes(activeNotificationWithTranscript.id)
    : false;

  const audioControls = appSettings.enable_text_input_mode
    ? <TextCommandInput onSubmit={handleTypedCommandSubmitFromInput} disabled={areCommandControlsDisabled} />
    : (
      <AudioInput
        onAudioChunk={handleAudioChunkFromInput}
        onListenStateChange={handleListenStateChangeFromInput}
        onCloudSessionChange={handleCloudSessionChangeFromInput}
        disabled={areCommandControlsDisabled}
      />
    );

  const hasActionableCalendarProposal =
    parsedActiveCalendarProposalWithTranscript !== null
    && (
      activeCalendarProposal === null
      || isCalendarProposalActionable(activeCalendarProposal)
    );

  const shouldExpandMainWindow =
    isDraftActionable(activeDraft) || hasActionableCalendarProposal;

  useEffect(() => {
    if (windowLabel !== "main") {
      return;
    }

    void setMainWindowExpanded(shouldExpandMainWindow);
  }, [setMainWindowExpanded, shouldExpandMainWindow, windowLabel]);

  return (
    <AppWindowContent
      isBootstrapReady={isBootstrapReady}
      bootstrapError={bootstrapError}
      isSetupRequired={isSetupRequired}
      missingSettings={missingSettings}
      isStartupWindow={isStartupWindow}
      isSettingsWindow={isSettingsWindow}
      isManualWindow={isManualWindow}
      appSettings={appSettings}
      oauthStatus={oauthStatus}
      agentStatus={agentStatus}
      isAlwaysOnTop={isAlwaysOnTop}
      isRecording={isRecording}
      activePalette={activePalette}
      unreadCount={unreadNotificationsWithTranscript.length}
      shouldExpandMainWindow={shouldExpandMainWindow}
      notifications={notifications}
      conversationTurns={conversationTurns}
      activeNotificationId={activeNotificationId}
      activeNotification={activeNotificationWithTranscript}
      activeNotificationTurns={activeNotificationTurnsWithTranscript}
      activeNotificationTranscript={activeNotificationTranscriptWithTranscript}
      activeFollowUp={activeFollowUp}
      activeDraft={activeDraft}
      draftRecipient={draftRecipient}
      draftSubject={draftSubject}
      draftBody={draftBody}
      draftSyncHint={draftSyncHint}
      draftActionError={draftActionError}
      isDraftSaving={isDraftSaving}
      activeCalendarProposal={activeCalendarProposal}
      calendarError={calendarError}
      isCalendarPlanning={isCalendarPlanning}
      isCalendarSaving={isCalendarSaving}
      proposalTitle={proposalTitle}
      proposalStartAtInput={proposalStartAtInput}
      proposalEndAtInput={proposalEndAtInput}
      proposalAttendeesInput={proposalAttendeesInput}
      proposalNotes={proposalNotes}
      isFeedbackProcessing={isFeedbackProcessing}
      isDismissingNotification={isDismissingNotification}
      liveTranscript={liveTranscript}
      recognizedActionLabel={recognizedActionLabel}
      isHistoryOpen={isHistoryOpen}
      parsedActiveFollowUp={parsedActiveFollowUpWithTranscript}
      parsedActiveDraft={parsedActiveDraftWithTranscript}
      parsedActiveCalendarProposal={parsedActiveCalendarProposalWithTranscript}
      audioControls={audioControls}
      onStartDragging={startDragging}
      onToggleAlwaysOnTop={toggleAlwaysOnTop}
      onHideWindow={hideWindow}
      onQuitApplication={quitApplication}
      onCloseCurrentWindow={closeCurrentWindow}
      onOpenSettingsWindow={openSettingsWindow}
      onOpenManualWindow={openManualWindow}
      onOpenStartupWindow={openStartupWindow}
      onAppSettingsChange={handleAppSettingsChange}
      onOAuthStatusChange={setOAuthStatus}
      onHistoryOpen={() => setIsHistoryOpen(true)}
      onHistoryClose={() => setIsHistoryOpen(false)}
      onSelectNotification={setActiveNotificationId}
      onDismissNotification={dismissCurrentNotification}
      onDraftRecipientChange={setDraftRecipientDirty}
      onDraftSubjectChange={setDraftSubjectDirty}
      onDraftBodyChange={setDraftBodyDirty}
      onDraftUseSuggestion={setDraftRecipientDirty}
      onDraftSave={() => {
        void handleDraftSave();
      }}
      onDraftSend={() => {
        void handleDraftSendAndDismiss();
      }}
      onDraftCancel={() => {
        void handleDraftCancelAndDismiss();
      }}
      onProposalTitleChange={setProposalTitle}
      onProposalStartAtChange={setProposalStartAtInput}
      onProposalEndAtChange={setProposalEndAtInput}
      onProposalAttendeesChange={setProposalAttendeesInput}
      onProposalNotesChange={setProposalNotes}
      onCalendarApprove={() => {
        void (async () => {
          const saved = await saveCalendarProposalEdits();
          if (!saved) {
            return;
          }
          await approveActiveCalendarProposal();
        })();
      }}
      onCalendarCancel={() => {
        void cancelActiveCalendarProposal();
      }}
    />
  );
}

export default App;
