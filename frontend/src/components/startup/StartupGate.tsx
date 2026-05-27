import type { MouseEvent } from "react";
import { Box, Button, Paper, ScrollArea, Text } from "@mantine/core";
import type { AgentStatus, AppSettings, OAuthStatus } from "../../lib/api";
import type { BootstrapErrorInfo } from "../../lib/startup";
import { RequiredSetupPanel } from "../RequiredSetupPanel";
import { TitleBar } from "../TitleBar";

type StartupGateProps = {
  mode: "loading" | "error" | "setup";
  agentStatus: AgentStatus;
  oauthStatus: OAuthStatus;
  isAlwaysOnTop: boolean;
  onStartDragging: (event: MouseEvent<HTMLElement>) => void;
  onToggleAlwaysOnTop: () => void;
  onClose: () => void | Promise<void>;
  bootstrapError?: BootstrapErrorInfo | null;
  settings?: AppSettings;
  missingSettings?: string[];
  onSettingsChange?: (next: AppSettings) => void;
  onOAuthStatusChange?: (next: OAuthStatus) => void;
};

function StartupShell({
  agentStatus,
  oauthStatus,
  isAlwaysOnTop,
  onStartDragging,
  onToggleAlwaysOnTop,
  onClose,
  children,
}: Omit<StartupGateProps, "mode"> & { children: React.ReactNode }) {
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
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onClose}
        title="Avera Desk - Setup"
        variant="minimal"
        notificationCount={0}
        isAlwaysOnTop={isAlwaysOnTop}
        isRecording={false}
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
      />

      <Box
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          padding: 8,
        }}
      >
        {children}
      </Box>
    </Box>
  );
}

export function StartupGate({
  mode,
  agentStatus,
  oauthStatus,
  isAlwaysOnTop,
  onStartDragging,
  onToggleAlwaysOnTop,
  onClose,
  bootstrapError = null,
  settings,
  missingSettings = [],
  onSettingsChange,
  onOAuthStatusChange,
}: StartupGateProps) {
  if (mode === "loading") {
    return (
      <StartupShell
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
        isAlwaysOnTop={isAlwaysOnTop}
        onStartDragging={onStartDragging}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onClose}
      >
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
          <Text size="sm" fw={600}>Starting Avera Desk</Text>
          <Text size="xs" c="dimmed">
            Waiting for local services and setup status.
          </Text>
        </Paper>
      </StartupShell>
    );
  }

  if (mode === "error" && bootstrapError) {
    return (
      <StartupShell
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
        isAlwaysOnTop={isAlwaysOnTop}
        onStartDragging={onStartDragging}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onClose}
      >
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
          <Text size="sm" fw={600}>Startup issue</Text>
          <Text size="xs" c="dimmed">{bootstrapError.summary}</Text>
          <Text
            size="xs"
            style={{ whiteSpace: "pre-wrap", fontFamily: "Consolas, 'Courier New', monospace" }}
          >
            {bootstrapError.detail}
          </Text>
          {bootstrapError.diagnosticsPaths && (
            <Text
              size="xs"
              c="dimmed"
              style={{ whiteSpace: "pre-wrap", fontFamily: "Consolas, 'Courier New', monospace" }}
            >
              {`Bootstrap log: ${bootstrapError.diagnosticsPaths.bootstrap_log_path}\nStartup log: ${bootstrapError.diagnosticsPaths.startup_log_path}`}
            </Text>
          )}
          <Button size="xs" w="fit-content" onClick={() => window.location.reload()}>
            Retry startup
          </Button>
        </Paper>
      </StartupShell>
    );
  }

  if (mode === "setup" && settings && onSettingsChange && onOAuthStatusChange) {
    return (
      <StartupShell
        agentStatus={agentStatus}
        oauthStatus={oauthStatus}
        isAlwaysOnTop={isAlwaysOnTop}
        onStartDragging={onStartDragging}
        onToggleAlwaysOnTop={onToggleAlwaysOnTop}
        onClose={onClose}
      >
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
            gap: 8,
            minHeight: 0,
          }}
        >
          <Box>
            <Text size="sm" fw={600}>
              Setup required
            </Text>

            <Text size="xs" c="dimmed" mt={2}>
              Required settings are missing. Complete setup below to continue.
            </Text>
          </Box>
          <ScrollArea
            type="auto"
            offsetScrollbars
            scrollbarSize={8}
            style={{ flex: 1, minHeight: 0 }}
          >
            <Box pr={6}>
              <RequiredSetupPanel
                settings={settings}
                missingSettings={missingSettings}
                onSettingsChange={onSettingsChange}
                onOAuthStatusChange={onOAuthStatusChange}
              />
            </Box>
          </ScrollArea>
        </Paper>
      </StartupShell>
    );
  }

  return null;
}