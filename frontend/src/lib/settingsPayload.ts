import type { AppSettings, UpdateAppSettings } from "./api";

type BuildUpdateSettingsPayloadOptions = {
  gmailClientSecretInput?: string;
  speechApiKeyInput?: string;
  llmApiKeyInput?: string;
};

function optionalTrimmedValue(value: string | undefined): string | undefined {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

export function buildUpdateSettingsPayload(
  settings: AppSettings,
  options?: BuildUpdateSettingsPayloadOptions,
): UpdateAppSettings {
  return {
    ...settings,
    gmail_client_secret: optionalTrimmedValue(options?.gmailClientSecretInput),
    speech_api_key: optionalTrimmedValue(options?.speechApiKeyInput),
    llm_api_key: optionalTrimmedValue(options?.llmApiKeyInput),
  };
}