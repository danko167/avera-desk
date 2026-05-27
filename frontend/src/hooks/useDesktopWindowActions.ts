import { useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { createLogger } from "../lib/logger";

const logger = createLogger("useDesktopWindowActions");

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function formatErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export function useDesktopWindowActions() {
  const logFrontendDiagnostic = useCallback(async (message: string) => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await invoke("log_startup_diagnostic", { message });
    } catch {
      // Avoid recursive logging loops if diagnostic command fails.
    }
  }, []);

  const raiseMainWindow = useCallback(async () => {
    try {
      await invoke("show_main_window");
    } catch (error) {
      logger.error("Failed to raise main window.", error, {
        action: "show_main_window",
      });
    }
  }, []);

  const completeStartupSetupWindow = useCallback(async () => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await invoke("complete_startup_setup");
    } catch (error) {
      logger.error("Failed to complete startup setup window.", error, {
        action: "complete_startup_setup",
      });
    }
  }, []);

  const quitApplication = useCallback(async () => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await invoke("quit_app");
    } catch (error) {
      logger.error("Failed to quit app.", error, {
        action: "quit_app",
      });
    }
  }, []);

  const closeCurrentWindow = useCallback(async () => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await getCurrentWindow().hide();
    } catch (error) {
      logger.error("Failed to close current window.", error, {
        action: "hide_current_window",
      });
      await logFrontendDiagnostic(`[action] closeCurrentWindow failed: ${formatErrorMessage(error)}`);
    }
  }, [logFrontendDiagnostic]);

  const openSettingsWindow = useCallback(async () => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await logFrontendDiagnostic("[action] openSettingsWindow invoked");
      await invoke("open_settings_window");
      await logFrontendDiagnostic("[action] openSettingsWindow success");
    } catch (error) {
      logger.error("Failed to open settings window.", error, {
        action: "open_settings_window",
      });
      await logFrontendDiagnostic(`[action] openSettingsWindow failed: ${formatErrorMessage(error)}`);
    }
  }, [logFrontendDiagnostic]);

  const openManualWindow = useCallback(async () => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await logFrontendDiagnostic("[action] openManualWindow invoked");
      await invoke("open_manual_window");
      await logFrontendDiagnostic("[action] openManualWindow success");
    } catch (error) {
      logger.error("Failed to open manual window.", error, {
        action: "open_manual_window",
      });
      await logFrontendDiagnostic(`[action] openManualWindow failed: ${formatErrorMessage(error)}`);
    }
  }, [logFrontendDiagnostic]);

  const openStartupWindow = useCallback(async () => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await invoke("open_startup_window");
    } catch (error) {
      logger.error("Failed to open setup window.", error, {
        action: "open_startup_window",
      });
      await logFrontendDiagnostic(`[action] openStartupWindow failed: ${formatErrorMessage(error)}`);
    }
  }, [logFrontendDiagnostic]);

  const setMainWindowExpanded = useCallback(async (expanded: boolean) => {
    if (!isTauriRuntime()) {
      return;
    }

    try {
      await invoke("set_main_window_expanded", { expanded });
    } catch (error) {
      logger.error("Failed to resize main window.", error, {
        action: "set_main_window_expanded",
        expanded,
      });
      await logFrontendDiagnostic(`[action] setMainWindowExpanded failed: ${formatErrorMessage(error)}`);
    }
  }, [logFrontendDiagnostic]);

  return {
    logFrontendDiagnostic,
    raiseMainWindow,
    completeStartupSetupWindow,
    quitApplication,
    closeCurrentWindow,
    openSettingsWindow,
    openManualWindow,
    openStartupWindow,
    setMainWindowExpanded,
  };
}
