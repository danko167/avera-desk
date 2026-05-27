import { Button, Group, Stack, Switch, Text } from "@mantine/core";
import { type AppSettings } from "../../lib/api";

type UiSettingsTabProps = {
  settings: AppSettings;
  isSaving: boolean;
  onChange: (next: AppSettings) => void;
  onSave: () => void;
};

export function UiSettingsTab({ settings, isSaving, onChange, onSave }: UiSettingsTabProps) {
  return (
    <Stack gap="xs">
      <Text size="xs" fw={500}>Interaction</Text>
      <Switch
        size="xs"
        label="Enable typing mode instead of microphone (EXPERIMENTAL)"
        checked={settings.enable_text_input_mode}
        onChange={(event) => {
          onChange({
            ...settings,
            enable_text_input_mode: event.currentTarget.checked,
          });
        }}
      />
      <Text size="xs" c="dimmed">
        When enabled, the main panel shows a text command input instead of voice capture controls.
        The flow is the same, but the UI is not fully polished for this mode.     </Text>
      <Group justify="flex-end">
        <Button size="xs" onClick={onSave} loading={isSaving}>Save UI Settings</Button>
      </Group>
    </Stack>
  );
}
