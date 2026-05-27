import {
  Box,
  Button,
  Divider,
  Group,
  ScrollArea,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { type AppSettings, type LlmUsageSummary } from "../../lib/api";

const PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "local", label: "Ollama / Local (OpenAI-compatible)" },
] as const;

const SPEECH_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
] as const;

const SPEECH_MODEL_OPTIONS = [
  { value: "gpt-realtime-whisper", label: "gpt-realtime-whisper" },
  { value: "gpt-4o-transcribe", label: "gpt-4o-transcribe" },
  { value: "gpt-4o-mini-transcribe", label: "gpt-4o-mini-transcribe" },
  { value: "whisper-1", label: "whisper-1" },
] as const;

const OPENAI_BASE_URL = "https://api.openai.com/v1";
const OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1";
const LOCAL_BASE_URL = "http://localhost:11434/v1";
const KNOWN_AI_BASE_URLS = [OPENAI_BASE_URL, OPENROUTER_BASE_URL, LOCAL_BASE_URL];

type AiSettingsTabProps = {
  settings: AppSettings;
  isSaving: boolean;
  isTestingConnection: boolean;
  llmUsageSummary: LlmUsageSummary | null;
  isLoadingLlmUsageSummary: boolean;
  llmUsageSummaryError: string | null;
  speechApiKeyInput: string;
  llmApiKeyInput: string;
  onChange: (next: AppSettings) => void;
  onSpeechApiKeyChange: (value: string) => void;
  onLlmApiKeyChange: (value: string) => void;
  onTestConnection: () => void;
  testConnectionResult: { endpoint: string; detail: string } | null;
  testConnectionError: string | null;
  onSave: () => void;
};

function formatTokenCount(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function getBaseUrlPlaceholder(provider: AppSettings["llm_provider"]): string {
  if (provider === "openrouter") {
    return OPENROUTER_BASE_URL;
  }

  if (provider === "local") {
    return LOCAL_BASE_URL;
  }

  return OPENAI_BASE_URL;
}

function shouldAutoSwitchBaseUrl(currentBaseUrl: string): boolean {
  const normalized = currentBaseUrl.trim().replace(/\/+$/, "");
  if (!normalized) {
    return true;
  }
  return KNOWN_AI_BASE_URLS.some((url) => url === normalized);
}

export function AiSettingsTab({
  settings,
  isSaving,
  isTestingConnection,
  llmUsageSummary,
  isLoadingLlmUsageSummary,
  llmUsageSummaryError,
  speechApiKeyInput,
  llmApiKeyInput,
  onChange,
  onSpeechApiKeyChange,
  onLlmApiKeyChange,
  onTestConnection,
  testConnectionResult,
  testConnectionError,
  onSave,
}: AiSettingsTabProps) {
  const speechModelValue = settings.speech_model.trim();
  const speechModelOptions =
    speechModelValue && !SPEECH_MODEL_OPTIONS.some((option) => option.value === speechModelValue)
      ? [{ value: speechModelValue, label: `${speechModelValue} (custom)` }, ...SPEECH_MODEL_OPTIONS]
      : [...SPEECH_MODEL_OPTIONS];

  return (
    <ScrollArea h="100%" offsetScrollbars>
      <Stack gap="xs">
        <Stack gap={4}>
          <Text size="xs" fw={500}>
            LLM
          </Text>
          <Text size="xs" c="dimmed">
            LLM settings power AI features like draft generation and follow-up extraction.
          </Text>
          <Text size="xs" c="dimmed">
            OpenAI, OpenRouter, and Ollama/local OpenAI-compatible backends are supported here.
          </Text>

          <Box>
            <Group justify="space-between" align="center" mb={4}>
              <Text size="xs" fw={600}>
                Token usage
              </Text>
              <Text size="10px" c="dimmed">
                Lifetime
              </Text>
            </Group>

            {isLoadingLlmUsageSummary ? (
              <Text size="xs" c="dimmed">
                Loading token usage...
              </Text>
            ) : null}

            {!isLoadingLlmUsageSummary && llmUsageSummaryError ? (
              <Text size="xs" c="red.7" style={{ whiteSpace: "pre-wrap" }}>
                {llmUsageSummaryError}
              </Text>
            ) : null}

            {!isLoadingLlmUsageSummary && !llmUsageSummaryError && llmUsageSummary ? (
              <Group gap={8} wrap="wrap" justify="space-between">
                <Text size="xs">
                  <Text span c="dimmed">Total:</Text> {formatTokenCount(llmUsageSummary.total_tokens)}
                </Text>
                <Text size="xs">
                  <Text span c="dimmed">Prompt:</Text> {formatTokenCount(llmUsageSummary.prompt_tokens)}
                </Text>
                <Text size="xs">
                  <Text span c="dimmed">Completion:</Text> {formatTokenCount(llmUsageSummary.completion_tokens)}
                </Text>
                <Text size="xs">
                  <Text span c="dimmed">Events:</Text> {formatTokenCount(llmUsageSummary.record_count)}
                </Text>
              </Group>
            ) : null}
          </Box>

          <Select
            size="xs"
            label="Provider"
            data={[...PROVIDER_OPTIONS]}
            value={settings.llm_provider}
            onChange={(value) => {
              const provider = (value as AppSettings["llm_provider"]) ?? "openai";
              const nextBaseUrl = shouldAutoSwitchBaseUrl(settings.llm_base_url)
                ? getBaseUrlPlaceholder(provider)
                : settings.llm_base_url;
              onChange({
                ...settings,
                llm_provider: provider,
                llm_base_url: nextBaseUrl,
              });
            }}
          />

          <TextInput
            size="xs"
            label="Model"
            placeholder="gpt-5.4-mini"
            value={settings.llm_model}
            onChange={(e) =>
              onChange({
                ...settings,
                llm_model: e.currentTarget.value,
              })
            }
          />

          <TextInput
            size="xs"
            label="Base URL"
            placeholder={getBaseUrlPlaceholder(settings.llm_provider)}
            value={settings.llm_base_url}
            onChange={(e) =>
              onChange({
                ...settings,
                llm_base_url: e.currentTarget.value,
              })
            }
          />

          <TextInput
            size="xs"
            type="password"
            label="API Key"
            placeholder={settings.llm_api_key_configured ? "Stored in OS keychain" : "Enter API key"}
            value={llmApiKeyInput}
            onChange={(e) => onLlmApiKeyChange(e.currentTarget.value)}
            description={
              settings.llm_api_key_configured
                ? "A key is already stored in the OS keychain. Leave this blank to keep it."
                : "This will be stored securely in the OS keychain when you click Save AI Settings."
            }
          />
        </Stack>

        <Divider my={2} />

        <Stack gap={4}>
          <Text size="xs" fw={500}>
            STT
          </Text>
          <Text size="xs" c="dimmed">
            Current live transcription uses an OpenAI realtime API. Speech provider selection is reserved for future expansion.
          </Text>

          <Select
            size="xs"
            label="Provider"
            data={[...SPEECH_PROVIDER_OPTIONS]}
            value={settings.speech_provider}
            disabled
          />

          <Select
            size="xs"
            label="Model"
            placeholder="Choose speech model"
            description="Pick the speech-to-text model used for realtime transcription. Supported presets include gpt-realtime-whisper, gpt-4o-transcribe, gpt-4o-mini-transcribe, and whisper-1."
            data={speechModelOptions}
            value={speechModelValue || null}
            onChange={(value) =>
              onChange({
                ...settings,
                speech_model: value ?? "",
              })
            }
          />

          <TextInput
            size="xs"
            label="Base URL"
            placeholder={getBaseUrlPlaceholder(settings.speech_provider)}
            value={settings.speech_base_url}
            onChange={(e) =>
              onChange({
                ...settings,
                speech_base_url: e.currentTarget.value,
              })
            }
          />

          <TextInput
            size="xs"
            type="password"
            label="API Key"
            placeholder={settings.speech_api_key_configured ? "Stored in OS keychain" : "Enter API key"}
            value={speechApiKeyInput}
            onChange={(e) => onSpeechApiKeyChange(e.currentTarget.value)}
            description={
              settings.speech_api_key_configured
                ? "A key is already stored in the OS keychain. Leave this blank to keep it."
                : "This will be stored securely in the OS keychain when you click Save AI Settings."
            }
          />
        </Stack>

        <Divider my={2} />

        <Group justify="space-between" align="flex-start">
          <Stack gap={4}>
            <Button
              onClick={onTestConnection}
              disabled={isSaving || isTestingConnection || !settings.llm_model.trim() || !settings.llm_base_url.trim()}
              size="xs"
              variant="default"
            >
              {isTestingConnection ? "Testing..." : "Test LLM connection"}
            </Button>
            {testConnectionResult ? (
              <Text size="xs" c="teal.7">
                {testConnectionResult.detail}
              </Text>
            ) : null}
            {testConnectionError ? (
              <Text size="xs" c="red.7" style={{ whiteSpace: "pre-wrap" }}>
                {testConnectionError}
              </Text>
            ) : null}
          </Stack>

          <Button onClick={onSave} disabled={isSaving} size="xs">
            {isSaving ? "Saving..." : "Save AI Settings"}
          </Button>
        </Group>
      </Stack>
    </ScrollArea>
  );
}
