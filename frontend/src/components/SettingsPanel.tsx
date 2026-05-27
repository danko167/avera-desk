import { Tabs } from "@mantine/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  clearAiSecrets,
  fetchAppSettings,
  fetchLlmUsageSummary,
  fetchOAuthLoginUrl,
  fetchOAuthStatus,
  logoutOAuth,
  updateAppSettings,
  testAiConnection,
  type AppSettings,
  type AiConnectionTestResult,
  type LlmUsageSummary,
  type OAuthStatus,
} from "../lib/api";
import { createLogger } from "../lib/logger";
import { buildUpdateSettingsPayload } from "../lib/settingsPayload";
import { AdvancedSettingsTab } from "./settings/AdvancedSettingsTab";
import { AiSettingsTab } from "./settings/AiSettingsTab";
import { OutlookSettingsTab } from "./settings/OutlookSettingsTab";
import { UiSettingsTab } from "./settings/UiSettingsTab";

type SettingsPanelProps = {
  settings: AppSettings;
  onChange: (next: AppSettings) => void;
  oauthStatus: OAuthStatus;
  onOAuthStatusChange: (next: OAuthStatus) => void;
};

const logger = createLogger("SettingsPanel");

export function SettingsPanel({
  settings,
  onChange,
  oauthStatus,
  onOAuthStatusChange,
}: SettingsPanelProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isClearingSecrets, setIsClearingSecrets] = useState(false);
  const [isTestingAiConnection, setIsTestingAiConnection] = useState(false);
  const [draftSettings, setDraftSettings] = useState(settings);
  const [isDraftDirty, setIsDraftDirty] = useState(false);
  const preservedDraftOverridesRef = useRef<Partial<AppSettings> | null>(null);
  const [gmailClientSecretInput, setGmailClientSecretInput] = useState("");
  const [speechApiKeyInput, setSpeechApiKeyInput] = useState("");
  const [llmApiKeyInput, setLlmApiKeyInput] = useState("");
  const [aiConnectionTestResult, setAiConnectionTestResult] = useState<AiConnectionTestResult | null>(null);
  const [aiConnectionTestError, setAiConnectionTestError] = useState<string | null>(null);
  const [llmUsageSummary, setLlmUsageSummary] = useState<LlmUsageSummary | null>(null);
  const [isLoadingLlmUsageSummary, setIsLoadingLlmUsageSummary] = useState(false);
  const [llmUsageSummaryError, setLlmUsageSummaryError] = useState<string | null>(null);
  const oauthPollIntervalRef = useRef<number | null>(null);
  const isMountedRef = useRef(true);

  const clearOAuthPollInterval = useCallback(() => {
    if (oauthPollIntervalRef.current !== null) {
      window.clearInterval(oauthPollIntervalRef.current);
      oauthPollIntervalRef.current = null;
    }
  }, []);

  const updateDraftSettings = useCallback((next: AppSettings) => {
    setIsDraftDirty(true);
    setDraftSettings(next);
  }, []);

  useEffect(() => {
    if (preservedDraftOverridesRef.current !== null) {
      setDraftSettings({
        ...settings,
        ...preservedDraftOverridesRef.current,
      });
      setIsDraftDirty(true);
      preservedDraftOverridesRef.current = null;
      return;
    }

    if (isDraftDirty) {
      return;
    }

    setDraftSettings(settings);
  }, [isDraftDirty, settings]);

  useEffect(() => {
    setAiConnectionTestResult(null);
    setAiConnectionTestError(null);
  }, [draftSettings.llm_provider, draftSettings.llm_model, draftSettings.llm_base_url]);

  useEffect(() => {
    void checkAuthStatus();
    void loadLlmUsageSummary();
  }, []);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      clearOAuthPollInterval();
    };
  }, [clearOAuthPollInterval]);

  // When authenticated status arrives (e.g. from the poll propagating through the
  // parent), always clear the loading state so the button switches immediately
  // rather than waiting for a potentially out-of-order setIsLoading(false) call.
  useEffect(() => {
    if (oauthStatus.authenticated) {
      setIsLoading(false);
      clearOAuthPollInterval();
    }
  }, [oauthStatus.authenticated, clearOAuthPollInterval]);

  const checkAuthStatus = async (): Promise<OAuthStatus | null> => {
    try {
      const data = await fetchOAuthStatus(true);
      onOAuthStatusChange(data);
      return data;
    } catch (error) {
      logger.error("Failed to check auth status.", error);
      return null;
    }
  };

  const loadLlmUsageSummary = async () => {
    setIsLoadingLlmUsageSummary(true);
    setLlmUsageSummaryError(null);
    try {
      const summary = await fetchLlmUsageSummary();
      setLlmUsageSummary(summary);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLlmUsageSummaryError(message);
      logger.warn("Failed to load LLM usage summary.", error);
    } finally {
      setIsLoadingLlmUsageSummary(false);
    }
  };

  const handleSaveSettings = async () => {
    setIsSaving(true);

    const payload = buildUpdateSettingsPayload(draftSettings, {
      gmailClientSecretInput,
      speechApiKeyInput,
      llmApiKeyInput,
    });

    try {
      const saved = await updateAppSettings(payload);
      onChange(saved);
      setDraftSettings(saved);
      setIsDraftDirty(false);
      setGmailClientSecretInput("");
      setSpeechApiKeyInput("");
      setLlmApiKeyInput("");
      await checkAuthStatus();
    } catch (error) {
      logger.error("Failed to save settings.", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveUiSettings = async () => {
    setIsSaving(true);

    const { enable_text_input_mode, ...preservedDraftOverrides } = draftSettings;
    preservedDraftOverridesRef.current = preservedDraftOverrides;

    const payload = buildUpdateSettingsPayload({
      ...settings,
      enable_text_input_mode,
    });

    try {
      const saved = await updateAppSettings(payload);
      onChange(saved);
      await checkAuthStatus();
    } catch (error) {
      preservedDraftOverridesRef.current = null;
      logger.error("Failed to save UI settings.", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestAiConnection = async () => {
    setIsTestingAiConnection(true);
    setAiConnectionTestError(null);
    setAiConnectionTestResult(null);

    try {
      const result = await testAiConnection({
        provider: draftSettings.llm_provider,
        model: draftSettings.llm_model,
        base_url: draftSettings.llm_base_url,
        api_key: llmApiKeyInput.trim() ? llmApiKeyInput.trim() : undefined,
      });
      setAiConnectionTestResult(result);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setAiConnectionTestError(message);
    } finally {
      setIsTestingAiConnection(false);
    }
  };

  const handleSyncIntervalCommit = async (minutes: number) => {
    const clampedMinutes = Math.min(60, Math.max(1, Math.round(minutes)));
    const nextDraft: AppSettings = {
      ...draftSettings,
      email_sync_interval_minutes: clampedMinutes,
    };

    updateDraftSettings(nextDraft);
    setIsSaving(true);

    const payload = buildUpdateSettingsPayload(nextDraft, {
      gmailClientSecretInput,
      speechApiKeyInput,
      llmApiKeyInput,
    });

    try {
      const saved = await updateAppSettings(payload);
      onChange(saved);
      setDraftSettings(saved);
      setIsDraftDirty(false);
      setGmailClientSecretInput("");
      setSpeechApiKeyInput("");
      setLlmApiKeyInput("");
      await checkAuthStatus();
    } catch (error) {
      logger.error("Failed to save sync interval.", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleConnectMailbox = async () => {
    const isM365Provider = draftSettings.email_provider === "m365";
    const missingProviderConfig = isM365Provider
      ? !draftSettings.m365_client_id || !draftSettings.m365_tenant_id
      : !draftSettings.gmail_client_id || (!gmailClientSecretInput.trim() && !draftSettings.gmail_client_secret_configured);

    if (missingProviderConfig) {
      alert(
        isM365Provider
          ? "Please configure Client ID and Tenant ID first."
          : "Please configure Gmail Client ID and Client Secret first."
      );
      return;
    }

    setIsLoading(true);
    clearOAuthPollInterval();

    const width = 500;
    const height = 700;
    const left = window.innerWidth / 2 - width / 2;
    const top = window.innerHeight / 2 - height / 2;

    let popup = window.open(
      "about:blank",
      `${draftSettings.email_provider}-login`,
      `width=${width},height=${height},left=${left},top=${top}`
    );

    if (popup && !popup.closed) {
      const providerLabel = isM365Provider ? "Microsoft" : "Gmail";
      popup.document.title = `Avera ${providerLabel} Login`;
      popup.document.body.replaceChildren();
      const loadingText = popup.document.createElement("p");
      loadingText.style.fontFamily = "sans-serif";
      loadingText.style.padding = "16px";
      loadingText.textContent = `Opening ${providerLabel} login...`;
      popup.document.body.appendChild(loadingText);
    }

    try {
      const loginUrl = await fetchOAuthLoginUrl();

      if (popup && !popup.closed) {
        popup.location.href = loginUrl;
      } else {
        await openUrl(loginUrl);
      }

      const startedAt = Date.now();
      const timeoutMs = 3 * 60 * 1000;
      const popupCloseGraceMs = 15 * 1000;
      let popupClosedAt: number | null = null;

      oauthPollIntervalRef.current = window.setInterval(async () => {
        const status = await checkAuthStatus();
        const isTimedOut = Date.now() - startedAt > timeoutMs;
        const isPopupClosed = Boolean(popup && popup.closed);

        if (isPopupClosed && popupClosedAt === null) {
          popupClosedAt = Date.now();
        }

        const popupGraceExpired =
          popupClosedAt !== null && Date.now() - popupClosedAt > popupCloseGraceMs;

        if (status?.authenticated || isTimedOut || popupGraceExpired) {
          clearOAuthPollInterval();
          if (!isMountedRef.current) {
            return;
          }
          setIsLoading(false);

          if (isTimedOut && !status?.authenticated) {
            alert(`${isM365Provider ? "Microsoft" : "Gmail"} connection timed out. Please try Connect again.`);
          }
        }
      }, 1000);
    } catch (error) {
      logger.error("Failed to initiate OAuth.", error);

      if (popup && !popup.closed) {
        popup.close();
      }

      clearOAuthPollInterval();
      setIsLoading(false);
    }
  };

  const handleDisconnectOutlook = async () => {
    setIsLoading(true);

    try {
      await logoutOAuth();
      onOAuthStatusChange({
        authenticated: false,
        connected_mailbox: null,
        persistence: "none",
        setup_required: false,
        missing_settings: [],
      });
    } catch (error) {
      logger.error("Failed to disconnect.", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearAiSecrets = async () => {
    const confirmed = window.confirm(
      "Clear the stored speech and LLM API keys from secure storage?"
    );
    if (!confirmed) {
      return;
    }

    setIsClearingSecrets(true);

    try {
      await clearAiSecrets();
      setSpeechApiKeyInput("");
      setLlmApiKeyInput("");

      const refreshedSettings = await fetchAppSettings();
      onChange(refreshedSettings);
      setDraftSettings(refreshedSettings);
      setIsDraftDirty(false);
      const stillConfiguredFromDefaults =
        refreshedSettings.speech_api_key_configured || refreshedSettings.llm_api_key_configured;
      if (stillConfiguredFromDefaults) {
        window.alert(
          "Stored secrets were cleared, but API keys are still available from environment variables (for example OPENAI_API_KEY or OPENROUTER_API_KEY)."
        );
      } else {
        window.alert("Stored speech and LLM API keys were cleared.");
      }
      await checkAuthStatus();
    } catch (error) {
      logger.error("Failed to clear AI secrets.", error);
    } finally {
      setIsClearingSecrets(false);
    }
  };

  return (
    <Tabs
      defaultValue="email"
      style={{ display: "flex", flexDirection: "column", height: "100%" }}
      styles={{
        tab: {
          padding: "5px 8px",
          minHeight: 28,
          fontSize: 12,
          fontWeight: 500,
        },
        panel: { flex: 1, overflow: "hidden", minHeight: 0 },
      }}
    >
      <Tabs.List grow>
        <Tabs.Tab value="email">Email</Tabs.Tab>
        <Tabs.Tab value="ai">AI</Tabs.Tab>
        <Tabs.Tab value="ui">UI</Tabs.Tab>
        <Tabs.Tab value="advanced">Advanced</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="email" pt="xs">
        <OutlookSettingsTab
          settings={draftSettings}
          gmailClientSecretInput={gmailClientSecretInput}
          oauthStatus={oauthStatus}
          isLoading={isLoading}
          isSaving={isSaving}
          onChange={updateDraftSettings}
          onGmailClientSecretChange={setGmailClientSecretInput}
          onSyncIntervalCommit={handleSyncIntervalCommit}
          onConnect={handleConnectMailbox}
          onDisconnect={handleDisconnectOutlook}
          onSave={handleSaveSettings}
        />
      </Tabs.Panel>

      <Tabs.Panel value="ai" pt="xs">
        <AiSettingsTab
          settings={draftSettings}
          isSaving={isSaving}
          isTestingConnection={isTestingAiConnection}
          llmUsageSummary={llmUsageSummary}
          isLoadingLlmUsageSummary={isLoadingLlmUsageSummary}
          llmUsageSummaryError={llmUsageSummaryError}
          speechApiKeyInput={speechApiKeyInput}
          llmApiKeyInput={llmApiKeyInput}
          onChange={updateDraftSettings}
          onSpeechApiKeyChange={setSpeechApiKeyInput}
          onLlmApiKeyChange={setLlmApiKeyInput}
          onTestConnection={handleTestAiConnection}
          testConnectionResult={aiConnectionTestResult}
          testConnectionError={aiConnectionTestError}
          onSave={handleSaveSettings}
        />
      </Tabs.Panel>

      <Tabs.Panel value="ui" pt="xs">
        <UiSettingsTab
          settings={draftSettings}
          isSaving={isSaving}
          onChange={updateDraftSettings}
          onSave={handleSaveUiSettings}
        />
      </Tabs.Panel>

      <Tabs.Panel value="advanced" pt="xs">
        <AdvancedSettingsTab
          settings={draftSettings}
          isSaving={isSaving}
          isClearingSecrets={isClearingSecrets}
          onChange={updateDraftSettings}
          onClearAiSecrets={handleClearAiSecrets}
          onSave={handleSaveSettings}
        />
      </Tabs.Panel>
    </Tabs>
  );
}