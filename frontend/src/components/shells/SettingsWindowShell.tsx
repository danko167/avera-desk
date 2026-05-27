import { Box, Paper, Text } from "@mantine/core";
import type { AgentStatus, OAuthStatus } from "../../lib/api";
import { TitleBar } from "../TitleBar";

type SettingsWindowShellProps = {
  isAlwaysOnTop: boolean;
  agentStatus: AgentStatus;
  oauthStatus: OAuthStatus;
  onStartDragging: (event: React.MouseEvent<HTMLElement>) => void;
  onToggleAlwaysOnTop: () => void;
  onClose: () => void | Promise<void>;
  children: React.ReactNode;
};

export function SettingsWindowShell({
  isAlwaysOnTop,
  agentStatus,
  oauthStatus,
  onStartDragging,
  onToggleAlwaysOnTop,
  onClose,
  children,
}: SettingsWindowShellProps) {
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
        title="Avera Desk - Settings"
        variant="minimal"
        notificationCount={0}
        isAlwaysOnTop={isAlwaysOnTop}
        isRecording={false}
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
      />

      <Box style={{ flex: 1, minHeight: 0, padding: 6, display: "flex" }}>
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
            minHeight: 0,
          }}
        >
          {children}
        </Paper>
      </Box>
    </Box>
  );
}

export function SettingsLoadingFallback() {
  return (
    <Text size="xs" c="dimmed" p="sm">
      Loading settings...
    </Text>
  );
}
