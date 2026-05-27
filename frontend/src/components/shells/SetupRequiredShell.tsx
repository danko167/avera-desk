import { Box, Button, Group, Paper, Stack, Text } from "@mantine/core";
import type { AgentStatus, OAuthStatus } from "../../lib/api";
import { TitleBar } from "../TitleBar";

type SetupRequiredShellProps = {
  isSettingsWindow: boolean;
  isAlwaysOnTop: boolean;
  agentStatus: AgentStatus;
  oauthStatus: OAuthStatus;
  onStartDragging: (event: React.MouseEvent<HTMLElement>) => void;
  onToggleAlwaysOnTop: () => void;
  onClose: () => void | Promise<void>;
  onOpenSetup: () => void | Promise<void>;
};

export function SetupRequiredShell({
  isSettingsWindow,
  isAlwaysOnTop,
  agentStatus,
  oauthStatus,
  onStartDragging,
  onToggleAlwaysOnTop,
  onClose,
  onOpenSetup,
}: SetupRequiredShellProps) {
  return (
    <Box
      component="main"
      w="100%"
      h="100vh"
      style={{
        overflow: "hidden",
        border: "1px solid rgba(234, 88, 12, 0.16)",
        background:
          "linear-gradient(to bottom left, rgba(255, 148, 25, 0.7) 0%, rgba(255, 137, 64, 0.6) 30%, rgba(255, 213, 192, 0.48) 40%, #fff3e8 65%, #ffffff 100%)",
        backdropFilter: "blur(18px)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <TitleBar
        onStartDragging={onStartDragging}
        onOpenHistory={() => { }}
        onOpenSettings={() => { }}
        onOpenManual={() => { }}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onClose}
        title={isSettingsWindow ? "Avera Desk - Settings" : "Avera Desk"}
        variant="minimal"
        notificationCount={0}
        isAlwaysOnTop={isAlwaysOnTop}
        isRecording={false}
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
      />

      <Box style={{ flex: 1, minHeight: 0, padding: 8, display: "flex" }}>
        <Paper
          withBorder
          radius="md"
          p="xs"
          bg="rgba(255, 255, 255, 0.7)"
          style={{
            borderColor: "rgba(234, 88, 12, 0.16)",
            border: "1px solid rgba(234, 88, 12, 0.16)",
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 8,
            minHeight: 0,
          }}
        >
          <Stack gap="xs" align="center">
            <Text size="sm" fw={600}>Setup is required</Text>
            <Text size="xs" c="dimmed" ta="center" maw={380}>
              Your main/settings window stays available, but setup must be completed in the dedicated setup window.
            </Text>
            <Group gap="xs">
              <Button size="xs" onClick={() => {
                void onOpenSetup();
              }}>
                Open Setup
              </Button>
            </Group>
          </Stack>
        </Paper>
      </Box>
    </Box>
  );
}
