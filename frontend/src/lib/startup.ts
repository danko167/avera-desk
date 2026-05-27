import { invoke } from "@tauri-apps/api/core";
import type { AgentStatus, AppSettings, ConnectionSettings, OAuthStatus } from "./api";
import { createLogger } from "./logger";

const logger = createLogger("startup");

export const DEFAULT_AGENT_STATUS: AgentStatus = {
  state: "standby",
  detail: "No active agent jobs",
  updated_at: new Date().toISOString(),
};

export const STARTUP_FETCH_RETRY_DELAY_MS = 500;
export const STARTUP_FETCH_MAX_ATTEMPTS = 30;

export const DEFAULT_APP_SETTINGS: AppSettings = {
  enable_transcription_trace: false,
  enable_text_input_mode: false,
  email_sync_interval_minutes: 5,
  app_api_base_url: "",
  app_ws_url: "",
  email_provider: "m365",
  m365_client_id: "",
  m365_tenant_id: "",
  m365_redirect_url: "",
  gmail_client_id: "",
  gmail_client_secret_configured: false,
  gmail_redirect_url: "",
  speech_provider: "openai",
  speech_model: "whisper-1",
  speech_base_url: "",
  speech_api_key_configured: false,
  llm_provider: "openai",
  llm_model: "",
  llm_base_url: "",
  llm_api_key_configured: false,
};

export const DEFAULT_OAUTH_STATUS: OAuthStatus = {
  authenticated: false,
  connected_mailbox: null,
  persistence: "none",
  setup_required: false,
  missing_settings: [],
};

export const APP_SETTINGS_STORAGE_KEY = "avera_app_settings";
export const APP_SETTINGS_SYNC_KEY = "avera_app_settings_sync";

type StoredConnectionSettings = ConnectionSettings;

export type StartupDiagnosticsPaths = {
  bootstrap_log_path: string;
  startup_log_path: string;
};

export type BootstrapErrorInfo = {
  stage: "settings" | "oauth";
  summary: string;
  detail: string;
  diagnosticsPaths: StartupDiagnosticsPaths | null;
};

export function readSettingsFromStorage(): AppSettings | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(APP_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<StoredConnectionSettings>;

    return {
      ...DEFAULT_APP_SETTINGS,
      app_api_base_url: parsed.app_api_base_url?.trim() ?? "",
      app_ws_url: parsed.app_ws_url?.trim() ?? "",
    };
  } catch {
    return null;
  }
}

export function writeSettingsToStorage(settings: AppSettings, options?: { broadcast?: boolean }) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const stored: StoredConnectionSettings = {
      app_api_base_url: settings.app_api_base_url,
      app_ws_url: settings.app_ws_url,
    };
    window.localStorage.setItem(APP_SETTINGS_STORAGE_KEY, JSON.stringify(stored));
    if (options?.broadcast) {
      window.localStorage.setItem(APP_SETTINGS_SYNC_KEY, String(Date.now()));
    }
  } catch {
    // Ignore storage errors; runtime state still updates.
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export async function retryBootstrapRequest<T>(request: () => Promise<T>): Promise<T> {
  let lastError: unknown;

  for (let attempt = 1; attempt <= STARTUP_FETCH_MAX_ATTEMPTS; attempt += 1) {
    const started = Date.now();
    try {
      const value = await request();
      await logStartupDiagnostic(
        `bootstrap_retry_success attempt=${attempt}/${STARTUP_FETCH_MAX_ATTEMPTS} duration_ms=${Date.now() - started}`
      );
      return value;
    } catch (error) {
      lastError = error;
      await logStartupDiagnostic(
        `bootstrap_retry_failure attempt=${attempt}/${STARTUP_FETCH_MAX_ATTEMPTS} duration_ms=${Date.now() - started} error=${describeBootstrapFailure(error)}`
      );
      if (attempt < STARTUP_FETCH_MAX_ATTEMPTS) {
        await delay(STARTUP_FETCH_RETRY_DELAY_MS);
      }
    }
  }

  throw lastError;
}

function describeBootstrapFailure(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

async function logStartupDiagnostic(message: string): Promise<StartupDiagnosticsPaths | null> {
  const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  if (!isTauri) {
    return null;
  }

  try {
    return await invoke<StartupDiagnosticsPaths>("log_startup_diagnostic", { message });
  } catch (error) {
    logger.error("Failed to log startup diagnostic.", error);
    return null;
  }
}

export async function buildBootstrapErrorInfo(
  stage: "settings" | "oauth",
  error: unknown,
): Promise<BootstrapErrorInfo> {
  const summary = stage === "settings"
    ? "Could not load app settings from the local backend."
    : "Could not load setup status from the local backend.";
  const detail = describeBootstrapFailure(error);
  const diagnosticsPaths = await logStartupDiagnostic(`${stage} bootstrap failed: ${detail}`);

  return {
    stage,
    summary,
    detail,
    diagnosticsPaths,
  };
}