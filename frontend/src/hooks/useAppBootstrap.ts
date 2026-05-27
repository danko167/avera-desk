import { useCallback, useEffect, useState } from "react";
import {
  applyRuntimeConnectionSettings,
  ensureLocalAuthToken,
  fetchAppSettings,
  fetchOAuthStatus,
  type AppSettings,
  type OAuthStatus,
} from "../lib/api";
import {
  APP_SETTINGS_STORAGE_KEY,
  APP_SETTINGS_SYNC_KEY,
  buildBootstrapErrorInfo,
  DEFAULT_APP_SETTINGS,
  DEFAULT_OAUTH_STATUS,
  readSettingsFromStorage,
  retryBootstrapRequest,
  type BootstrapErrorInfo,
  writeSettingsToStorage,
} from "../lib/startup";
import { createLogger } from "../lib/logger";

const logger = createLogger("useAppBootstrap");

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function useAppBootstrap() {
  const [hasLoadedAppSettings, setHasLoadedAppSettings] = useState(false);
  const [hasLoadedOAuthStatus, setHasLoadedOAuthStatus] = useState(false);
  const [bootstrapError, setBootstrapError] = useState<BootstrapErrorInfo | null>(null);
  const [isLocalAuthReady, setIsLocalAuthReady] = useState(false);
  const [localAuthReadyNonce, setLocalAuthReadyNonce] = useState(0);
  const [appSettings, setAppSettings] = useState<AppSettings>(() => {
    const stored = readSettingsFromStorage();
    if (stored !== null) {
      return stored;
    }

    return DEFAULT_APP_SETTINGS;
  });
  const [oauthStatus, setOAuthStatus] = useState<OAuthStatus>(DEFAULT_OAUTH_STATUS);

  const refreshBootstrapState = useCallback(async (useRetry: boolean) => {
    let bootstrapStage: "settings" | "oauth" = "settings";

    try {
      await ensureLocalAuthToken();
      setIsLocalAuthReady(true);
      setLocalAuthReadyNonce((current) => current + 1);

      const settings = useRetry
        ? await retryBootstrapRequest(() => fetchAppSettings())
        : await fetchAppSettings();

      setAppSettings(settings);
      applyRuntimeConnectionSettings(settings);
      writeSettingsToStorage(settings);
      setHasLoadedAppSettings(true);
      bootstrapStage = "oauth";

      const status = useRetry
        ? await retryBootstrapRequest(() => fetchOAuthStatus())
        : await fetchOAuthStatus();

      setOAuthStatus((current) => ({
        ...status,
        connected_mailbox:
          status.connected_mailbox ??
          (status.authenticated ? current.connected_mailbox ?? null : null),
      }));
      setHasLoadedOAuthStatus(true);
      setBootstrapError(null);
    } catch (error) {
      if (useRetry) {
        if (bootstrapStage === "settings") {
          logger.error("Failed to load app settings.", error);
          setBootstrapError(await buildBootstrapErrorInfo("settings", error));
          return;
        }

        logger.error("Failed to load OAuth status.", error);
        setBootstrapError(await buildBootstrapErrorInfo("oauth", error));
        return;
      }

      logger.warn("Transient bootstrap refresh failed.", error);
    }
  }, []);

  useEffect(() => {
    void refreshBootstrapState(true);
  }, [refreshBootstrapState]);

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }

    let refreshing = false;

    const refreshIfVisible = () => {
      if (document.visibilityState === "hidden" || refreshing) {
        return;
      }

      refreshing = true;
      void refreshBootstrapState(false).finally(() => {
        refreshing = false;
      });
    };

    window.addEventListener("focus", refreshIfVisible);
    document.addEventListener("visibilitychange", refreshIfVisible);

    return () => {
      window.removeEventListener("focus", refreshIfVisible);
      document.removeEventListener("visibilitychange", refreshIfVisible);
    };
  }, [refreshBootstrapState]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== APP_SETTINGS_STORAGE_KEY && event.key !== APP_SETTINGS_SYNC_KEY) {
        return;
      }

      if (event.key === APP_SETTINGS_STORAGE_KEY) {
        const stored = readSettingsFromStorage();
        if (stored !== null) {
          setAppSettings((current) => ({
            ...current,
            app_api_base_url: stored.app_api_base_url,
            app_ws_url: stored.app_ws_url,
          }));
          applyRuntimeConnectionSettings(stored);
        }
      }

      void refreshBootstrapState(false);
    };

    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener("storage", handleStorage);
    };
  }, [refreshBootstrapState]);

  const handleAppSettingsChange = useCallback((nextSettings: AppSettings) => {
    setAppSettings(nextSettings);
    applyRuntimeConnectionSettings(nextSettings);
    writeSettingsToStorage(nextSettings, { broadcast: true });
  }, []);

  return {
    appSettings,
    oauthStatus,
    hasLoadedAppSettings,
    hasLoadedOAuthStatus,
    bootstrapError,
    isLocalAuthReady,
    localAuthReadyNonce,
    setOAuthStatus,
    refreshBootstrapState,
    handleAppSettingsChange,
  };
}
