import { useMemo } from "react";
import {
  parseCalendarProposalNotification,
  parseDraftNotification,
  parseFollowUpNotification,
  type ConversationTurn,
  type Notification,
} from "../lib/api";
import { timestampToMs } from "../lib/time";

type UseNotificationCenterParams = {
  notifications: Notification[];
  activeNotificationId: string | null;
  conversationTurns: ConversationTurn[];
  liveTranscript: string;
  isListeningPrompt: (text: string) => boolean;
};

export function useNotificationCenter({
  notifications,
  activeNotificationId,
  conversationTurns,
  liveTranscript,
  isListeningPrompt,
}: UseNotificationCenterParams) {
  const unreadNotifications = useMemo(
    () => notifications.filter((notification) => !notification.read),
    [notifications]
  );

  const activeNotification = useMemo(() => {
    if (notifications.length === 0) {
      return null;
    }

    if (activeNotificationId) {
      const selected = notifications.find(
        (notification) => notification.id === activeNotificationId
      );
      if (selected) {
        return selected;
      }
    }

    return unreadNotifications[0] ?? null;
  }, [activeNotificationId, notifications, unreadNotifications]);

  const activeNotificationTurns = useMemo(() => {
    if (!activeNotification) {
      return [];
    }
    return conversationTurns
      .filter((turn) => turn.notification_id === activeNotification.id)
      .sort((a, b) => timestampToMs(b.timestamp) - timestampToMs(a.timestamp));
  }, [activeNotification, conversationTurns]);

  const activeNotificationTranscript = useMemo(() => {
    const live = liveTranscript.trim();
    if (live.length > 0 && !isListeningPrompt(live)) {
      return live;
    }

    const linkedUserTurn = activeNotificationTurns.find((turn) => turn.role === "user")?.text;
    if (linkedUserTurn && linkedUserTurn.trim().length > 0) {
      return linkedUserTurn;
    }

    return "";
  }, [activeNotificationTurns, isListeningPrompt, liveTranscript]);

  const parsedActiveFollowUp = useMemo(() => {
    if (!activeNotification) {
      return null;
    }
    return parseFollowUpNotification(activeNotification.message);
  }, [activeNotification]);

  const parsedActiveDraft = useMemo(() => {
    if (!activeNotification) {
      return null;
    }
    return parseDraftNotification(activeNotification.message);
  }, [activeNotification]);

  const parsedActiveCalendarProposal = useMemo(() => {
    if (!activeNotification) {
      return null;
    }
    return parseCalendarProposalNotification(activeNotification.message);
  }, [activeNotification]);

  return {
    unreadNotifications,
    activeNotification,
    activeNotificationTurns,
    activeNotificationTranscript,
    parsedActiveFollowUp,
    parsedActiveDraft,
    parsedActiveCalendarProposal,
  };
}
