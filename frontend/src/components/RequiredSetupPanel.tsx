import {
  Anchor,
  Badge,
  Box,
  Button,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { useEffect, useMemo, useState } from "react";
import {
  fetchAppSettings,
  fetchOAuthLoginUrl,
  fetchOAuthStatus,
  updateAppSettings,
  type AppSettings,
  type OAuthStatus,
  type UpdateAppSettings,
} from "../lib/api";
import {
  validateClientId,
  validateGmailClientSecret,
  validateRedirectUrl,
  validateTenantId,
} from "../lib/settingsValidation";

type RequiredSetupPanelProps = {
  settings: AppSettings;
  missingSettings: string[];
  onSettingsChange: (next: AppSettings) => void;
  onOAuthStatusChange: (next: OAuthStatus) => void;
};

const OPENAI_BASE_URL = "https://api.openai.com/v1";
const OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1";
const LOCAL_BASE_URL = "http://localhost:11434/v1";
const KNOWN_AI_BASE_URLS = [OPENAI_BASE_URL, OPENROUTER_BASE_URL, LOCAL_BASE_URL];

type SetupStep = "email" | "ai" | "stt" | "review";

const stepOrder: SetupStep[] = ["email", "ai", "stt", "review"];

const setupSteps = [
  { key: "email", label: "Email", description: "Mailbox" },
  { key: "ai", label: "AI", description: "LLM" },
  { key: "stt", label: "Speech", description: "STT" },
  { key: "review", label: "Review", description: "Finish" },
] satisfies Array<{
  key: SetupStep;
  label: string;
  description: string;
}>;

function getDefaultBaseUrl(provider: AppSettings["llm_provider"]): string {
  if (provider === "openrouter") return OPENROUTER_BASE_URL;
  if (provider === "local") return LOCAL_BASE_URL;
  return OPENAI_BASE_URL;
}

function shouldAutoSwitchBaseUrl(currentBaseUrl: string): boolean {
  const normalized = currentBaseUrl.trim().replace(/\/+$/, "");
  if (!normalized) return true;

  return KNOWN_AI_BASE_URLS.some((url) => url === normalized);
}

function normalizeDraftSettings(settings: AppSettings): AppSettings {
  return {
    ...settings,
    speech_provider: "openai",
    speech_base_url: settings.speech_base_url.trim() || OPENAI_BASE_URL,
  };
}

export function RequiredSetupPanel({
  settings,
  missingSettings,
  onSettingsChange,
  onOAuthStatusChange,
}: RequiredSetupPanelProps) {
  const [step, setStep] = useState<SetupStep>("email");
  const [draftSettings, setDraftSettings] = useState<AppSettings>(() =>
    normalizeDraftSettings(settings)
  );
  const [isDraftDirty, setIsDraftDirty] = useState(false);
  const [gmailClientSecretInput, setGmailClientSecretInput] = useState("");
  const [speechApiKeyInput, setSpeechApiKeyInput] = useState("");
  const [llmApiKeyInput, setLlmApiKeyInput] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);

  const updateDraftSettings = (
    updater: AppSettings | ((current: AppSettings) => AppSettings)
  ) => {
    setIsDraftDirty(true);
    setDraftSettings((current) =>
      typeof updater === "function" ? (updater as (current: AppSettings) => AppSettings)(current) : updater
    );
  };

  useEffect(() => {
    if (isDraftDirty) {
      return;
    }

    setDraftSettings(normalizeDraftSettings(settings));
  }, [isDraftDirty, settings]);

  useEffect(() => {
    if (!saveSuccessMessage) return;

    const timeoutId = window.setTimeout(() => {
      setSaveSuccessMessage(null);
    }, 1800);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [saveSuccessMessage]);

  const emailProviderReady =
    draftSettings.email_provider === "m365" || draftSettings.email_provider === "gmail";
  const llmProviderReady =
    draftSettings.llm_provider === "openai" ||
    draftSettings.llm_provider === "openrouter" ||
    draftSettings.llm_provider === "local";
  const sttProviderReady = draftSettings.speech_provider === "openai";

  const requiresM365 = draftSettings.email_provider === "m365";
  const requiresGmail = draftSettings.email_provider === "gmail";
  const requiresSpeechKey = draftSettings.speech_provider !== "local";
  const requiresLlmKey = draftSettings.llm_provider !== "local";
  const hasExistingSpeechKey = draftSettings.speech_api_key_configured === true;
  const hasExistingLlmKey = draftSettings.llm_api_key_configured === true;
  const trimmedLlmApiKeyInput = llmApiKeyInput.trim();
  const trimmedSpeechApiKeyInput = speechApiKeyInput.trim();
  const canReuseOpenAiLlmKeyForSpeech =
    draftSettings.llm_provider === "openai" &&
    draftSettings.speech_provider === "openai" &&
    trimmedSpeechApiKeyInput.length === 0 &&
    trimmedLlmApiKeyInput.length > 0;
  const effectiveSpeechApiKeyInput =
    trimmedSpeechApiKeyInput.length > 0 ? speechApiKeyInput : canReuseOpenAiLlmKeyForSpeech
      ? llmApiKeyInput
      : "";

  const fieldErrors = {
    m365_client_id: requiresM365
      ? validateClientId(draftSettings.m365_client_id, { required: true })
      : undefined,
    m365_tenant_id: requiresM365
      ? validateTenantId(draftSettings.m365_tenant_id, { required: true })
      : undefined,
    m365_redirect_url: requiresM365
      ? validateRedirectUrl(draftSettings.m365_redirect_url, { required: true })
      : undefined,
    gmail_client_id:
      requiresGmail && !draftSettings.gmail_client_id.trim()
        ? "Gmail client ID is required."
        : undefined,
    gmail_client_secret: validateGmailClientSecret(gmailClientSecretInput, {
      required: requiresGmail && !draftSettings.gmail_client_secret_configured,
    }),
    gmail_redirect_url: requiresGmail
      ? validateRedirectUrl(draftSettings.gmail_redirect_url, { required: true })
      : undefined,
    speech_api_key:
      requiresSpeechKey &&
        !hasExistingSpeechKey &&
        !trimmedSpeechApiKeyInput &&
        !canReuseOpenAiLlmKeyForSpeech
        ? "Speech API key is required."
        : undefined,
    llm_api_key:
      requiresLlmKey && !hasExistingLlmKey && !llmApiKeyInput.trim()
        ? "LLM API key is required."
        : undefined,
  };

  const emailStepValid =
    emailProviderReady &&
    !Object.entries(fieldErrors)
      .filter(([key]) => key.startsWith("m365_") || key.startsWith("gmail_"))
      .some(([, value]) => typeof value === "string");

  const aiStepValid = llmProviderReady && fieldErrors.llm_api_key === undefined;
  const sttStepValid = sttProviderReady && fieldErrors.speech_api_key === undefined;

  const readinessChecks = useMemo(() => {
    const missingKeyLabels = missingSettings
      .filter((value) => !["speech_api_key", "llm_api_key"].includes(value))
      .map((value) => value.replace(/_/g, " "));

    return [
      {
        label: `Email provider configured (${draftSettings.email_provider === "gmail" ? "Gmail" : "Microsoft 365"
          })`,
        ok: emailStepValid,
      },
      {
        label: `AI provider configured (${draftSettings.llm_provider})`,
        ok: aiStepValid,
      },
      {
        label: `Speech provider configured (${draftSettings.speech_provider})`,
        ok: sttStepValid,
      },
      {
        label: "No remaining required settings",
        ok: missingKeyLabels.length === 0 || (emailStepValid && aiStepValid && sttStepValid),
      },
    ];
  }, [
    aiStepValid,
    draftSettings.email_provider,
    draftSettings.llm_provider,
    draftSettings.speech_provider,
    emailStepValid,
    missingSettings,
    sttStepValid,
  ]);

  const allChecksPassed = emailStepValid && aiStepValid && sttStepValid;
  const activeStep = stepOrder.indexOf(step);

  const stepSuccessLabels: Record<SetupStep, string> = {
    email: "email",
    ai: "AI",
    stt: "speech",
    review: "setup",
  };

  const moveStep = (direction: 1 | -1) => {
    setSaveError(null);
    setSaveSuccessMessage(null);

    setStep((current) => {
      const nextIndex = Math.min(
        stepOrder.length - 1,
        Math.max(0, stepOrder.indexOf(current) + direction)
      );

      return stepOrder[nextIndex];
    });
  };

  const persistSetup = async (
    connectMailbox: boolean,
    options?: { refreshOAuthStatus?: boolean }
  ): Promise<boolean> => {
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccessMessage(null);

    const payload: UpdateAppSettings = {
      ...draftSettings,
      gmail_client_secret: gmailClientSecretInput.trim() ? gmailClientSecretInput.trim() : undefined,
      speech_api_key: trimmedSpeechApiKeyInput
        ? trimmedSpeechApiKeyInput
        : canReuseOpenAiLlmKeyForSpeech
          ? trimmedLlmApiKeyInput
          : undefined,
      llm_api_key: trimmedLlmApiKeyInput ? trimmedLlmApiKeyInput : undefined,
    };

    try {
      const savedSettings = await updateAppSettings(payload);
      const refreshedSettings = await fetchAppSettings();
      const nextSettings = refreshedSettings.app_api_base_url ? refreshedSettings : savedSettings;

      onSettingsChange(nextSettings);
      setDraftSettings(normalizeDraftSettings(nextSettings));
      setIsDraftDirty(false);

      if (connectMailbox) {
        const loginUrl = await fetchOAuthLoginUrl();
        await openUrl(loginUrl);
      }

      if (options?.refreshOAuthStatus ?? true) {
        const refreshedStatus = await fetchOAuthStatus(true);
        onOAuthStatusChange(refreshedStatus);
      }
      setGmailClientSecretInput("");
      setSpeechApiKeyInput("");
      setLlmApiKeyInput("");
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setSaveError(message);
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const handleContinue = async (nextStep: SetupStep, canContinue: boolean) => {
    if (!canContinue) return;

    const saved = await persistSetup(false, { refreshOAuthStatus: false });

    if (saved) {
      setSaveError(null);
      setSaveSuccessMessage(`Saved ${stepSuccessLabels[step]} setup.`);
      setStep(nextStep);
    }
  };

  const handleSave = async (connectMailbox: boolean) => {
    if (!allChecksPassed) return;

    const saved = await persistSetup(connectMailbox);

    if (saved) {
      setSaveSuccessMessage(
        connectMailbox ? "Setup saved. Opening mailbox connection..." : "Setup saved."
      );
    }
  };

  return (
    <Stack gap="sm">
      <SimpleGrid cols={{ base: 4 }} spacing="xs">
        {setupSteps.map((item, index) => {
          const isActive = item.key === step;
          const isDone = index < activeStep;

          return (
            <Paper
              key={item.key}
              withBorder
              p="xs"
              // bg={isActive ? "orange.0" : undefined}
              bg="none"
              style={{
                cursor: "default",
                border: "none"
                // borderColor: isActive ? "var(--mantine-color-orange-4)" : undefined,
              }}
            >
              <Group gap="xs" wrap="nowrap">
                <Badge
                  size="lg"
                  circle
                  variant={isActive ? "filled" : isDone ? "light" : "outline"}
                  color={isDone ? "green" : isActive ? "orange" : "orange"}
                >
                  {index + 1}
                </Badge>

                <Box style={{ minWidth: 0 }}>
                  <Text size="xs" fw={600} truncate>
                    {item.label}
                  </Text>
                  <Text size="xs" c="dimmed" truncate>
                    {item.description}
                  </Text>
                </Box>
              </Group>
            </Paper>
          );
        })}
      </SimpleGrid>

      {step === "email" ? (
        <Stack gap="sm">
          <Stack gap={4}>
            <Text size="xs" fw={500}>
              Email provider
            </Text>

            <Select
              size="xs"
              data={[
                { value: "m365", label: "Microsoft 365 (Outlook)" },
                { value: "gmail", label: "Gmail" },
              ]}
              value={draftSettings.email_provider}
              onChange={(value) =>
                updateDraftSettings((current) => ({
                  ...current,
                  email_provider: (value as AppSettings["email_provider"]) ?? "m365",
                }))
              }
              allowDeselect={false}
            />
          </Stack>

          {requiresM365 ? (
            <>
              <Text size="xs" c="dimmed">
                Microsoft 365 app setup docs:{" "}
                <Anchor
                  size="xs"
                  onClick={() =>
                    openUrl(
                      "https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app"
                    )
                  }
                  style={{ cursor: "pointer" }}
                >
                  Entra app registration quickstart
                </Anchor>
              </Text>

              <TextInput
                size="xs"
                label="Microsoft 365 Client ID"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={draftSettings.m365_client_id}
                error={fieldErrors.m365_client_id}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  updateDraftSettings((current) => ({ ...current, m365_client_id: value }));
                }}
              />

              <TextInput
                size="xs"
                label="Microsoft 365 Tenant ID"
                placeholder="tenant UUID, domain, or common/organizations/consumers"
                value={draftSettings.m365_tenant_id}
                error={fieldErrors.m365_tenant_id}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  updateDraftSettings((current) => ({ ...current, m365_tenant_id: value }));
                }}
              />

              <Text size="xs" c="dimmed">
                Alias behavior: common = work/school + personal, organizations = work/school only,
                consumers = personal only.
              </Text>

              <TextInput
                size="xs"
                label="Microsoft 365 Redirect URL"
                placeholder="http://localhost:8000/api/oauth/callback"
                value={draftSettings.m365_redirect_url}
                error={fieldErrors.m365_redirect_url}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  updateDraftSettings((current) => ({ ...current, m365_redirect_url: value }));
                }}
              />
            </>
          ) : null}

          {requiresGmail ? (
            <>
              <Text size="xs" c="dimmed">
                Gmail app setup docs:{" "}
                <Anchor
                  size="xs"
                  onClick={() =>
                    openUrl("https://developers.google.com/workspace/guides/create-credentials")
                  }
                  style={{ cursor: "pointer" }}
                >
                  Google OAuth credentials guide
                </Anchor>
              </Text>

              <TextInput
                size="xs"
                label="Gmail Client ID"
                placeholder="xxxxxxxxxx-abc.apps.googleusercontent.com"
                value={draftSettings.gmail_client_id}
                error={fieldErrors.gmail_client_id}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  updateDraftSettings((current) => ({ ...current, gmail_client_id: value }));
                }}
              />

              <TextInput
                type="password"
                size="xs"
                label="Gmail Client Secret"
                placeholder={draftSettings.gmail_client_secret_configured ? "Stored in OS keychain" : "Enter client secret"}
                description={draftSettings.gmail_client_secret_configured
                  ? "A Gmail client secret is already stored securely. Enter a new one only if you want to replace it."
                  : undefined}
                value={gmailClientSecretInput}
                error={fieldErrors.gmail_client_secret}
                onChange={(event) => {
                  setGmailClientSecretInput(event.currentTarget.value);
                }}
              />

              <TextInput
                size="xs"
                label="Gmail Redirect URL"
                placeholder="http://localhost:8000/api/oauth/google/callback"
                value={draftSettings.gmail_redirect_url}
                error={fieldErrors.gmail_redirect_url}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  updateDraftSettings((current) => ({ ...current, gmail_redirect_url: value }));
                }}
              />
            </>
          ) : null}

          <Group justify="flex-end">
            <Button
              size="xs"
              onClick={() => void handleContinue("ai", emailStepValid)}
              disabled={isSaving || !emailStepValid}
            >
              {isSaving ? "Saving..." : "Save and Continue to AI"}
            </Button>
          </Group>
        </Stack>
      ) : null}

      {step === "ai" ? (
        <Stack gap="sm">
          <Stack gap={4}>
            <Text size="xs" fw={500}>
              LLM provider
            </Text>

            <Select
              size="xs"
              data={[
                { value: "openai", label: "OpenAI" },
                { value: "openrouter", label: "OpenRouter" },
                { value: "local", label: "Ollama / Local (OpenAI-compatible)" },
              ]}
              value={draftSettings.llm_provider}
              onChange={(value) => {
                const provider = (value as AppSettings["llm_provider"]) ?? "openai";

                updateDraftSettings((current) => ({
                  ...current,
                  llm_provider: provider,
                  llm_base_url: shouldAutoSwitchBaseUrl(current.llm_base_url)
                    ? getDefaultBaseUrl(provider)
                    : current.llm_base_url,
                }));
              }}
              allowDeselect={false}
            />

            {draftSettings.llm_provider === "openai" ? (
              <Text size="xs" c="dimmed">
                OpenAI is currently the only Speech provider. The Speech step will automatically
                reuse this OpenAI API key unless you enter a different key there.
              </Text>
            ) : null}
          </Stack>

          {requiresLlmKey ? (
            <TextInput
              type="password"
              size="xs"
              label="LLM API Key"
              description={
                hasExistingLlmKey
                  ? "An API key is already configured. Enter a new one only if you want to replace it."
                  : undefined
              }
              placeholder="Enter API key"
              value={llmApiKeyInput}
              error={fieldErrors.llm_api_key}
              onChange={(event) => setLlmApiKeyInput(event.currentTarget.value)}
            />
          ) : (
            <Text size="xs" c="dimmed">
              Ollama/local provider selected. No LLM API key is required.
            </Text>
          )}

          <Group justify="space-between">
            <Button size="xs" variant="default" onClick={() => moveStep(-1)}>
              Back
            </Button>

            <Button
              size="xs"
              onClick={() => void handleContinue("stt", aiStepValid)}
              disabled={isSaving || !aiStepValid}
            >
              {isSaving ? "Saving..." : "Save and Continue to Speech"}
            </Button>
          </Group>
        </Stack>
      ) : null}

      {step === "stt" ? (
        <Stack gap="sm">
          <Stack gap={4}>
            <Text size="xs" fw={500}>
              Speech-to-text provider
            </Text>

            <Select
              size="xs"
              data={[{ value: "openai", label: "OpenAI" }]}
              value="openai"
              disabled
              allowDeselect={false}
            />

            <Text size="xs" c="dimmed">
              Speech provider selection is reserved for future expansion. Current transcription
              uses the built-in OpenAI-compatible path and defaults to whisper-1.
            </Text>
          </Stack>

          <TextInput
            type="password"
            size="xs"
            label="Speech API Key"
            description={
              hasExistingSpeechKey
                ? "A speech API key is already configured. Enter a new one only if you want to replace it."
                : canReuseOpenAiLlmKeyForSpeech
                  ? "Automatically reusing the OpenAI LLM API key from the previous step. You can still override it here."
                  : undefined
            }
            placeholder="Enter API key"
            value={effectiveSpeechApiKeyInput}
            error={fieldErrors.speech_api_key}
            onChange={(event) => setSpeechApiKeyInput(event.currentTarget.value)}
          />

          <Group justify="space-between">
            <Button size="xs" variant="default" onClick={() => moveStep(-1)}>
              Back
            </Button>

            <Button
              size="xs"
              onClick={() => void handleContinue("review", sttStepValid)}
              disabled={isSaving || !sttStepValid}
            >
              {isSaving ? "Saving..." : "Save and Continue to Review"}
            </Button>
          </Group>
        </Stack>
      ) : null}

      {step === "review" ? (
        <Stack gap="sm">
          <Text size="xs" fw={600}>
            Final setup check
          </Text>

          <Stack gap={2}>
            {readinessChecks.map((check) => (
              <Text key={check.label} size="xs" c={check.ok ? "teal.7" : "red.7"}>
                {check.ok ? "PASS" : "MISSING"} {check.label}
              </Text>
            ))}
          </Stack>

          <Text size="xs" c="dimmed">
            After saving, you can optionally launch the mailbox connection flow immediately.
            Authentication itself is not required to finish setup storage.
          </Text>

          <Group justify="space-between">
            <Button size="xs" variant="default" onClick={() => moveStep(-1)}>
              Back
            </Button>

            <Group gap="xs">
              <Button
                size="xs"
                variant="default"
                onClick={() => void handleSave(false)}
                disabled={isSaving || !allChecksPassed}
              >
                {isSaving ? "Saving..." : "Save setup"}
              </Button>

              <Button
                size="xs"
                onClick={() => void handleSave(true)}
                disabled={isSaving || !allChecksPassed}
              >
                {isSaving ? "Saving..." : "Save and Connect Mailbox"}
              </Button>
            </Group>
          </Group>
        </Stack>
      ) : null}

      {saveSuccessMessage ? (
        <Text size="xs" c="teal.7">
          {saveSuccessMessage}
        </Text>
      ) : null}

      {saveError ? (
        <Text size="xs" c="red.7" style={{ whiteSpace: "pre-wrap" }}>
          {saveError}
        </Text>
      ) : null}
    </Stack>
  );
}