import type { Dispatch, SetStateAction } from "react";
import { renderHook } from "@testing-library/react";
import type { WsServerMessage } from "../../lib/api";
import { useWsMessageHandler } from "../../hooks/useWsMessageHandler";

describe("useWsMessageHandler", () => {
  it("keeps feedback processing active while overlapping operations are still running", () => {
    const unreadCountRef = { current: 0 };
    const feedbackProcessingDepthRef = { current: 0 };
    const closeWindowTimerRef = { current: null as number | null };

    let feedbackProcessingState = false;
    const setIsFeedbackProcessing: Dispatch<SetStateAction<boolean>> = (value) => {
      feedbackProcessingState = typeof value === "function" ? value(feedbackProcessingState) : value;
    };

    const { result } = renderHook(() =>
      useWsMessageHandler({
        activeNotificationId: null,
        parsedActiveDraft: null,
        unreadCountRef,
        feedbackProcessingDepthRef,
        closeWindowTimerRef,
        scheduleConversationRefreshes: vi.fn(),
        clearCloseWindowTimer: vi.fn(),
        hideWindow: vi.fn(async () => {}),
        raiseMainWindow: vi.fn(async () => {}),
        setMainWindowExpanded: vi.fn(async () => {}),
        refreshActiveDraft: vi.fn(async () => {}),
        setAgentStatus: vi.fn(),
        setIsFeedbackProcessing,
        setNotifications: vi.fn(),
        setPendingDismissIds: vi.fn(),
        setActiveNotificationId: vi.fn(),
        setConversationTurns: vi.fn(),
        setRecognizedActionLabel: vi.fn(),
        applyTranscriptPartialFromWs: vi.fn(),
        applyTranscriptFinalFromWs: vi.fn(),
      })
    );

    const send = (payload: WsServerMessage) => {
      result.current(payload);
    };

    send({ type: "feedback_processing", active: true });
    send({ type: "feedback_processing", active: true });
    send({ type: "feedback_processing", active: false });

    expect(feedbackProcessingDepthRef.current).toBe(1);
    expect(feedbackProcessingState).toBe(true);

    send({ type: "feedback_processing", active: false });

    expect(feedbackProcessingDepthRef.current).toBe(0);
    expect(feedbackProcessingState).toBe(false);
  });

  it("resets stale feedback processing depth on snapshot", () => {
    const unreadCountRef = { current: 0 };
    const feedbackProcessingDepthRef = { current: 2 };
    const closeWindowTimerRef = { current: null as number | null };

    let feedbackProcessingState = true;
    const setIsFeedbackProcessing: Dispatch<SetStateAction<boolean>> = (value) => {
      feedbackProcessingState = typeof value === "function" ? value(feedbackProcessingState) : value;
    };

    const { result } = renderHook(() =>
      useWsMessageHandler({
        activeNotificationId: null,
        parsedActiveDraft: null,
        unreadCountRef,
        feedbackProcessingDepthRef,
        closeWindowTimerRef,
        scheduleConversationRefreshes: vi.fn(),
        clearCloseWindowTimer: vi.fn(),
        hideWindow: vi.fn(async () => {}),
        raiseMainWindow: vi.fn(async () => {}),
        setMainWindowExpanded: vi.fn(async () => {}),
        refreshActiveDraft: vi.fn(async () => {}),
        setAgentStatus: vi.fn(),
        setIsFeedbackProcessing,
        setNotifications: vi.fn(),
        setPendingDismissIds: vi.fn(),
        setActiveNotificationId: vi.fn(),
        setConversationTurns: vi.fn(),
        setRecognizedActionLabel: vi.fn(),
        applyTranscriptPartialFromWs: vi.fn(),
        applyTranscriptFinalFromWs: vi.fn(),
      })
    );

    result.current({
      type: "snapshot",
      status: { state: "standby", detail: "No active agent jobs", updated_at: new Date().toISOString() },
      notifications: [],
    });

    expect(feedbackProcessingDepthRef.current).toBe(0);
    expect(feedbackProcessingState).toBe(false);
  });
});
