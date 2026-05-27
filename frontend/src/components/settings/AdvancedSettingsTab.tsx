import { Button, Divider, Group, ScrollArea, Stack, Switch, Text, TextInput } from "@mantine/core";
import { type AppSettings } from "../../lib/api";
import {
  getApiBaseUrlPolicyHint,
  getWebSocketUrlPolicyHint,
  validateApiBaseUrl,
  validateWebSocketUrl,
} from "../../lib/settingsValidation";

type AdvancedSettingsTabProps = {
  settings: AppSettings;
  isSaving: boolean;
  isClearingSecrets: boolean;
  onChange: (next: AppSettings) => void;
  onClearAiSecrets: () => void;
  onSave: () => void;
};

export function AdvancedSettingsTab({
  settings,
  isSaving,
  isClearingSecrets,
  onChange,
  onClearAiSecrets,
  onSave,
}: AdvancedSettingsTabProps) {
  const apiBaseUrlHint = getApiBaseUrlPolicyHint(settings.app_api_base_url);
  const wsUrlHint = getWebSocketUrlPolicyHint(settings.app_ws_url);

  return (
    <ScrollArea h="100%" offsetScrollbars>
      <Stack gap="xs">
        <Stack gap={4}>
          <Text size="xs" fw={500}>
            Caution!
          </Text>
          <Text size="xs" c="dimmed">
            Changing these settings can cause the app to malfunction if not done correctly.
            Usually, you should not need to change these unless you have a custom deployment or are doing development work.
          </Text>
          <TextInput
            size="xs"
            label="API Base URL"
            placeholder="http://127.0.0.1:8000"
            description={
              apiBaseUrlHint
                ? `Saved to backend settings and used as the canonical API base URL. ${apiBaseUrlHint}`
                : "Saved to backend settings and used as the canonical API base URL. If invalid or empty, backend falls back to the default local URL."
            }
            error={validateApiBaseUrl(settings.app_api_base_url)}
            value={settings.app_api_base_url}
            onChange={(event) =>
              onChange({
                ...settings,
                app_api_base_url: event.currentTarget.value,
              })
            }
          />

          <TextInput
            size="xs"
            label="WebSocket URL"
            placeholder="ws://127.0.0.1:8000/ws"
            description={
              wsUrlHint
                ? `Saved to backend settings and normalized by backend. ${wsUrlHint}`
                : "Saved to backend settings and normalized by backend. If empty or invalid, backend derives a websocket URL from the API base URL."
            }
            error={validateWebSocketUrl(settings.app_ws_url)}
            value={settings.app_ws_url}
            onChange={(event) =>
              onChange({
                ...settings,
                app_ws_url: event.currentTarget.value,
              })
            }
          />
        </Stack>

        <Divider my={2} />

        <Stack gap={4}>
          <Text size="xs" fw={500}>
            Diagnostics
          </Text>

          <Switch
            size="xs"
            label="Enable transcription trace logging"
            checked={settings.enable_transcription_trace}
            onChange={(event) =>
              onChange({
                ...settings,
                enable_transcription_trace: event.currentTarget.checked,
              })
            }
          />

          <Text size="xs" c="dimmed" mb="xs">
            Off by default. Enable only when debugging, because logs can grow quickly.
          </Text>

          <Button
            variant="light"
            color="red"
            size="xs"
            onClick={onClearAiSecrets}
            disabled={isSaving || isClearingSecrets}
          >
            {isClearingSecrets ? "Clearing AI Keys..." : "Clear Stored AI API Keys"}
          </Button>

          <Text size="xs" c="dimmed">
            Removes the stored speech and LLM API keys from secure OS storage. Use this to reset setup checks without editing Windows Credential Manager manually.
          </Text>
        </Stack>

        <Group justify="flex-end">
          <Button onClick={onSave} disabled={isSaving} size="xs">
            {isSaving ? "Saving..." : "Save Advanced Settings"}
          </Button>
        </Group>
      </Stack>
    </ScrollArea>
  );
}
