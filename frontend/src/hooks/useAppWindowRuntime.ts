import { useEffect } from "react";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { WsClientMessage } from "../lib/api";
import { createLogger } from "../lib/logger";

const logger = createLogger("useAppWindowRuntime");

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

declare global {
  interface Window {
    __AVERA_WINDOW_LABEL?: string;
  }
}

export function getInitialWindowLabel(): string {
  if (typeof window === "undefined") {
    return "main";
  }

  const injected = (window.__AVERA_WINDOW_LABEL ?? "").trim().toLowerCase();
  if (injected === "startup" || injected === "settings" || injected === "main" || injected === "manual") {
    return injected;
  }

  try {
    const params = new URLSearchParams(window.location.search);
    const candidate = (params.get("window") ?? "").trim().toLowerCase();
    if (candidate === "startup" || candidate === "settings" || candidate === "main" || candidate === "manual") {
      return candidate;
    }
  } catch {
    // Ignore URL parsing issues and fall back to main label.
  }

  return "main";
}

export function useRendererDiagnostics(
  windowLabel: string,
  logFrontendDiagnostic: (message: string) => Promise<void>,
): void {
  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }

    const onWindowError = (event: ErrorEvent) => {
      const detail = event.error instanceof Error
        ? `${event.error.name}: ${event.error.message}`
        : String(event.message || "unknown window error");
      void logFrontendDiagnostic(`[renderer:${windowLabel}] window.error ${detail}`);
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason instanceof Error
        ? `${event.reason.name}: ${event.reason.message}`
        : String(event.reason);
      void logFrontendDiagnostic(`[renderer:${windowLabel}] unhandledrejection ${reason}`);
    };

    window.addEventListener("error", onWindowError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);

    return () => {
      window.removeEventListener("error", onWindowError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, [logFrontendDiagnostic, windowLabel]);
}

export function useCurrentWindowLabel(setWindowLabel: (label: string) => void): void {
  useEffect(() => {
    let cancelled = false;

    const detectWindowLabel = async () => {
      if (!isTauriRuntime()) {
        return;
      }

      try {
        const currentWindow = getCurrentWindow();
        if (!cancelled) {
          setWindowLabel(currentWindow.label);
        }
      } catch (error) {
        logger.error("Failed to read current window label.", error);
      }
    };

    void detectWindowLabel();

    return () => {
      cancelled = true;
    };
  }, [setWindowLabel]);
}

type SendWsMessage = (message: WsClientMessage) => void;

export function useAttentionEventBridge(windowLabel: string, sendWsMessage: SendWsMessage): void {
  useEffect(() => {
    const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
    if (!isTauri || windowLabel !== "main") {
      return;
    }

    let disposed = false;
    let cleanup: (() => void) | null = null;

    const listenPromise = listen<string>("attention-event", (event) => {
      const source = String(event.payload || "trigger.unknown").toLowerCase();
      const isCalendarAttention = source.includes("calendar");
      sendWsMessage({
        type: "mock_trigger",
        message: isCalendarAttention
          ? `Calendar attention signal from ${event.payload}`
          : `Attention signal from ${event.payload}`,
        notification_type: isCalendarAttention ? "info" : "warning",
      });
    });

    listenPromise.then((fn) => {
      if (disposed) {
        fn();
        return;
      }
      cleanup = fn;
    });

    return () => {
      disposed = true;
      if (cleanup) {
        cleanup();
      } else {
        listenPromise.then((fn) => fn());
      }
    };
  }, [sendWsMessage, windowLabel]);
}
