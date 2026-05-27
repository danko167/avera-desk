import { useCallback } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  shouldExpandWindowForNotification,
  type AgentStatus,
  type ConversationTurn,
  type Notification,
  type WsServerMessage,
} from "../lib/api";
import { createLogger } from "../lib/logger";
import { timestampToMs } from "../lib/time";

const logger = createLogger("useWsMessageHandler");

type UseWsMessageHandlerParams = {
  activeNotificationId: string | null;
  parsedActiveDraft: { draftId: string } | null;
  unreadCountRef: RefObject<number>;
  feedbackProcessingDepthRef: RefObject<number>;
  closeWindowTimerRef: RefObject<number | null>;
  scheduleConversationRefreshes: (options?: { immediate?: boolean }) => void;
  clearCloseWindowTimer: () => void;
  hideWindow: () => Promise<void>;
  raiseMainWindow: () => Promise<void>;
  setMainWindowExpanded: (expanded: boolean) => Promise<void>;
  refreshActiveDraft: (draftId: string) => Promise<void>;
  setAgentStatus: Dispatch<SetStateAction<AgentStatus>>;
  setIsFeedbackProcessing: Dispatch<SetStateAction<boolean>>;
  setNotifications: Dispatch<SetStateAction<Notification[]>>;
  setPendingDismissIds: Dispatch<SetStateAction<string[]>>;
  setActiveNotificationId: Dispatch<SetStateAction<string | null>>;
  setConversationTurns: Dispatch<SetStateAction<ConversationTurn[]>>;
  setRecognizedActionLabel: Dispatch<SetStateAction<string | null>>;
  applyTranscriptPartialFromWs: (text: string) => void;
  applyTranscriptFinalFromWs: (text: string) => void;
};

export function useWsMessageHandler({
  activeNotificationId,
  parsedActiveDraft,
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
}: UseWsMessageHandlerParams) {
  return useCallback((payload: WsServerMessage) => {
    if (payload.type === "snapshot") {
      const sortedNotifications = [...payload.notifications].sort(
        (a, b) => timestampToMs(b.timestamp) - timestampToMs(a.timestamp)
      );
      const unread = sortedNotifications.filter((notification) => !notification.read);

      setAgentStatus(payload.status);
      feedbackProcessingDepthRef.current = 0;
      setIsFeedbackProcessing(false);
      setNotifications(sortedNotifications);
      setPendingDismissIds((current) => current.filter((id) => unread.some((notification) => notification.id === id)));
      scheduleConversationRefreshes({ immediate: true });
      setActiveNotificationId((currentId) => {
        if (
          currentId &&
          unread.some((notification) => notification.id === currentId)
        ) {
          return currentId;
        }
        return unread[0]?.id ?? null;
      });
      return;
    }

    if (payload.type === "status") {
      setAgentStatus(payload.status);
      return;
    }

    if (payload.type === "notification") {
      setPendingDismissIds((current) => {
        if (!payload.notification.read) {
          return current;
        }
        return current.filter((id) => id !== payload.notification.id);
      });
      setNotifications((current) => {
        const deduped = current.filter(
          (notification) => notification.id !== payload.notification.id
        );
        return [payload.notification, ...deduped];
      });
      scheduleConversationRefreshes();
      setActiveNotificationId((currentId) => {
        if (currentId === payload.notification.id) {
          return payload.notification.read ? null : currentId;
        }
        if (currentId) {
          return currentId;
        }
        return payload.notification.read ? null : payload.notification.id;
      });

      if (!payload.notification.read) {
        clearCloseWindowTimer();
        void (async () => {
          await setMainWindowExpanded(shouldExpandWindowForNotification(payload.notification));
          await raiseMainWindow();
        })();
      }
      return;
    }

    if (payload.type === "close_window_after") {
      clearCloseWindowTimer();
      const onlyIfLastUnread = payload.only_if_last_unread ?? false;
      const delayMs = Math.max(0, Number(payload.delay_ms ?? 5000));

      closeWindowTimerRef.current = window.setTimeout(() => {
        if (onlyIfLastUnread && unreadCountRef.current > 0) {
          closeWindowTimerRef.current = null;
          return;
        }
        void hideWindow();
        closeWindowTimerRef.current = null;
      }, delayMs);
      return;
    }

    if (payload.type === "conversation_turn") {
      setConversationTurns((current) => {
        const deduped = current.filter((turn) => turn.id !== payload.turn.id);
        return [payload.turn, ...deduped];
      });

      if (
        parsedActiveDraft &&
        payload.turn.notification_id === activeNotificationId
      ) {
        void refreshActiveDraft(parsedActiveDraft.draftId);
      }
      return;
    }

    if (payload.type === "feedback_processing") {
      if (payload.active === true) {
        feedbackProcessingDepthRef.current = feedbackProcessingDepthRef.current + 1;
      } else {
        feedbackProcessingDepthRef.current = Math.max(0, feedbackProcessingDepthRef.current - 1);
      }
      setIsFeedbackProcessing(feedbackProcessingDepthRef.current > 0);
      return;
    }

    if (payload.type === "recognized_action") {
      setRecognizedActionLabel(payload.label);
      return;
    }

    if (payload.type === "protocol_error") {
      logger.error("WebSocket protocol error.", {
        detail: payload.detail,
        messageType: payload.message_type ?? "unknown",
        activeNotificationId,
        hasActiveDraft: parsedActiveDraft !== null,
      });
      return;
    }

    if (payload.type === "transcript_partial") {
      applyTranscriptPartialFromWs(payload.text);
      return;
    }

    if (payload.type === "transcript_final") {
      applyTranscriptFinalFromWs(payload.text);
    }
  }, [
    activeNotificationId,
    applyTranscriptFinalFromWs,
    applyTranscriptPartialFromWs,
    clearCloseWindowTimer,
    closeWindowTimerRef,
    hideWindow,
    parsedActiveDraft,
    raiseMainWindow,
    setMainWindowExpanded,
    refreshActiveDraft,
    scheduleConversationRefreshes,
    setActiveNotificationId,
    setAgentStatus,
    setConversationTurns,
    setIsFeedbackProcessing,
    setNotifications,
    setPendingDismissIds,
    setRecognizedActionLabel,
    feedbackProcessingDepthRef,
    unreadCountRef,
  ]);
}
