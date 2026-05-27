import { useCallback, useEffect, useRef, useState } from "react";
import type { WsClientMessage } from "../lib/api";
import type { ListenPhase } from "../components/AudioInput";

const TRANSCRIPT_VISIBILITY_HOLD_MS = 3500;
const TRANSCRIPT_RESET_TO_DEFAULT_MS = 5000;

function isListeningPrompt(text: string): boolean {
  const normalized = text.trim().toLowerCase();
  return (
    normalized === "listening..." ||
    normalized === 'listening locally... say "avera"' ||
    normalized === 'listening... (say "avera")' ||
    normalized === "listening for your command..."
  );
}

type SendWsMessage = (message: WsClientMessage, options?: { queueIfDisconnected?: boolean }) => void;

type UseTranscriptStateParams = {
  activeNotificationId: string | null;
  scheduleConversationRefreshes: (options?: { immediate?: boolean }) => void;
  raiseMainWindow: () => Promise<void>;
};

export function useTranscriptState({
  activeNotificationId,
  scheduleConversationRefreshes,
  raiseMainWindow,
}: UseTranscriptStateParams) {
  const [liveTranscript, setLiveTranscript] = useState("");
  const [isRecording, setIsRecording] = useState(false);

  const transcriptionSessionRef = useRef(0);
  const hasCapturedAudioRef = useRef(false);
  const processingFallbackTimerRef = useRef<number | null>(null);
  const transcriptResetTimerRef = useRef<number | null>(null);
  const transcriptVisibleUntilRef = useRef(0);
  const isRecordingRef = useRef(false);

  const clearTranscriptResetTimer = useCallback(() => {
    if (transcriptResetTimerRef.current !== null) {
      window.clearTimeout(transcriptResetTimerRef.current);
      transcriptResetTimerRef.current = null;
    }
  }, []);

  const scheduleTranscriptResetToDefault = useCallback(() => {
    clearTranscriptResetTimer();
    transcriptResetTimerRef.current = window.setTimeout(() => {
      setLiveTranscript(() => {
        if (isRecordingRef.current) {
          return "Listening...";
        }
        return "";
      });
      transcriptResetTimerRef.current = null;
    }, TRANSCRIPT_RESET_TO_DEFAULT_MS);
  }, [clearTranscriptResetTimer]);

  const handleAudioChunk = useCallback((
    sendWsMessage: SendWsMessage,
    chunk: { audioBase64: string; bytes: number },
  ) => {
    if (!chunk.audioBase64 || chunk.bytes <= 0) {
      return;
    }

    if (transcriptionSessionRef.current < 1) {
      return;
    }

    hasCapturedAudioRef.current = true;
    sendWsMessage({
      type: "audio_blob",
      bytes: chunk.bytes,
      audio_base64: chunk.audioBase64,
      audio_format: "pcm16",
    });
  }, []);

  const handleListenStateChange = useCallback((active: boolean, phase: ListenPhase) => {
    setIsRecording(active);
    isRecordingRef.current = active;

    if (phase === "starting") {
      if (processingFallbackTimerRef.current !== null) {
        window.clearTimeout(processingFallbackTimerRef.current);
        processingFallbackTimerRef.current = null;
      }
      clearTranscriptResetTimer();
      return;
    }

    if (phase === "stopping") {
      clearTranscriptResetTimer();
      return;
    }

    if (active) {
      if (processingFallbackTimerRef.current !== null) {
        window.clearTimeout(processingFallbackTimerRef.current);
        processingFallbackTimerRef.current = null;
      }
      clearTranscriptResetTimer();
      const prompt = "Listening...";
      if (!(isListeningPrompt(prompt) && Date.now() < transcriptVisibleUntilRef.current)) {
        setLiveTranscript(prompt);
      }
      return;
    }
    clearTranscriptResetTimer();

    setLiveTranscript((current) => (isListeningPrompt(current) ? "" : current));
  }, [clearTranscriptResetTimer]);

  const handleCloudSessionChange = useCallback((
    sendWsMessage: SendWsMessage,
    active: boolean,
  ) => {
    if (active) {
      transcriptionSessionRef.current += 1;
      hasCapturedAudioRef.current = false;
      if (processingFallbackTimerRef.current !== null) {
        window.clearTimeout(processingFallbackTimerRef.current);
        processingFallbackTimerRef.current = null;
      }
      sendWsMessage({
        type: "audio_start",
        notification_id: activeNotificationId ?? undefined,
      });
      return;
    }

    sendWsMessage({ type: "audio_stop" });
    window.setTimeout(() => {
      scheduleConversationRefreshes();
    }, 500);

    if (hasCapturedAudioRef.current) {
      setLiveTranscript((current) => {
        if (current.trim().length > 0 && !isListeningPrompt(current)) {
          return current;
        }
        return "Processing...";
      });
      processingFallbackTimerRef.current = window.setTimeout(() => {
        setLiveTranscript((current) => (current === "Processing..." ? "No speech detected." : current));
      }, 2500);
    } else {
      setLiveTranscript("No speech detected.");
    }
    void raiseMainWindow();
  }, [activeNotificationId, raiseMainWindow, scheduleConversationRefreshes]);

  const handleTypedCommandSubmit = useCallback((sendWsMessage: SendWsMessage, text: string) => {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    transcriptVisibleUntilRef.current = Date.now() + TRANSCRIPT_VISIBILITY_HOLD_MS;
    setLiveTranscript(trimmed);
    scheduleTranscriptResetToDefault();

    sendWsMessage({
      type: "text_command",
      text: trimmed,
      notification_id: activeNotificationId ?? undefined,
    });
  }, [activeNotificationId, scheduleTranscriptResetToDefault]);

  const applyTranscriptPartialFromWs = useCallback((text: string) => {
    const isPrompt = isListeningPrompt(text);
    if (isPrompt && Date.now() < transcriptVisibleUntilRef.current) {
      return;
    }

    if (!isPrompt && text.trim().length > 0) {
      transcriptVisibleUntilRef.current = Date.now() + TRANSCRIPT_VISIBILITY_HOLD_MS;
    }

    setLiveTranscript(text);
    if (!isPrompt && text.trim().length > 0) {
      scheduleTranscriptResetToDefault();
    }
  }, [scheduleTranscriptResetToDefault]);

  const applyTranscriptFinalFromWs = useCallback((text: string) => {
    if (text.trim().length > 0 && !isListeningPrompt(text)) {
      transcriptVisibleUntilRef.current = Date.now() + TRANSCRIPT_VISIBILITY_HOLD_MS;
    }
    setLiveTranscript(text);
    scheduleConversationRefreshes();
    if (text.trim().length > 0 && !isListeningPrompt(text)) {
      scheduleTranscriptResetToDefault();
    }
    void raiseMainWindow();
  }, [raiseMainWindow, scheduleConversationRefreshes, scheduleTranscriptResetToDefault]);

  useEffect(() => {
    if (liveTranscript !== "Processing..." && processingFallbackTimerRef.current !== null) {
      window.clearTimeout(processingFallbackTimerRef.current);
      processingFallbackTimerRef.current = null;
    }
  }, [liveTranscript]);

  useEffect(() => {
    return () => {
      if (processingFallbackTimerRef.current !== null) {
        window.clearTimeout(processingFallbackTimerRef.current);
      }
      if (transcriptResetTimerRef.current !== null) {
        window.clearTimeout(transcriptResetTimerRef.current);
      }
    };
  }, []);

  return {
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
  };
}
