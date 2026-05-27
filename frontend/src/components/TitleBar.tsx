import type { MouseEvent } from "react";
import {
  ActionIcon,
  Badge,
  Box,
  Group,
  Indicator,
  Text,
  ThemeIcon,
  Tooltip,
} from "@mantine/core";
import {
  IconBook,
  IconBell,
  IconMicrophone,
  IconMicrophoneOff,
  IconPinned,
  IconSettings,
  IconX,
  IconDeviceDesktop,
} from "@tabler/icons-react";
import type { AgentStatus, OAuthStatus } from "../lib/api";

type TitleBarProps = {
  onStartDragging: (event: MouseEvent<HTMLElement>) => void;
  onOpenHistory: () => void;
  onOpenSettings: () => void;
  onOpenManual?: () => void;
  onToggleAlwaysOnTop: () => void;
  onClose: () => void | Promise<void>;
  title?: string;
  variant?: "full" | "minimal";
  notificationCount: number;
  isAlwaysOnTop: boolean;
  isRecording: boolean;
  agentStatus: AgentStatus;
  oauthStatus: OAuthStatus;
};

export function TitleBar({
  onStartDragging,
  onOpenHistory,
  onOpenSettings,
  onOpenManual,
  onToggleAlwaysOnTop,
  onClose,
  title = "Avera Desk",
  variant = "full",
  notificationCount,
  isAlwaysOnTop,
  isRecording,
  agentStatus,
  oauthStatus,
}: TitleBarProps) {
  const isBackendRunning = agentStatus.state === "running";

  const statusColor =
    agentStatus.state === "error"
      ? "red"
      : isRecording
        ? "orange"
        : isBackendRunning
          ? "teal"
          : oauthStatus.authenticated
            ? oauthStatus.persistence === "session"
              ? "yellow"
              : "green"
            : "gray";

  const statusLabel =
    agentStatus.state === "error"
      ? "Error"
      : isRecording
        ? "Listening"
        : isBackendRunning
          ? "Running"
          : oauthStatus.authenticated
            ? oauthStatus.persistence === "session"
              ? "Session-only"
              : "Connected"
            : "Disconnected";

  const statusTitle =
    agentStatus.state === "error"
      ? agentStatus.detail
      : isRecording
        ? "Listening (push-to-talk)"
        : isBackendRunning
          ? agentStatus.detail || "Background agent processing"
          : oauthStatus.authenticated
            ? oauthStatus.persistence === "session"
              ? `Mailbox is connected as ${oauthStatus.connected_mailbox ?? "your account"}, but only for this session.`
              : `Mailbox is connected as ${oauthStatus.connected_mailbox ?? "your account"} and should survive app restarts and PC reboots.`
            : "Mailbox is not connected. Open Settings to configure your email provider.";

  const centeredActionIconStyles = {
    root: {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    },
  };

  const isMinimal = variant === "minimal";

  return (
    <Box
      component="header"
      onMouseDown={onStartDragging}
      h={32}
      px={12}
      pr={6}
      style={{
        borderBottom: "1px solid rgba(234, 88, 12, 0.12)",
        background:
          "linear-gradient(to right, rgba(255,255,255,0.35) 0%, rgba(255,255,255,0.55) 35%, rgba(255,255,255,0.72) 100%)",
        userSelect: "none",
        cursor: "grab",
        display: "flex",
        alignItems: "center",
      }}
    >
      <Group justify="space-between" align="center" w="100%" gap={0}>
        <Group gap={6} align="center">
          <Text fw={500} fz="sm" c="#8b4b22">
            <IconDeviceDesktop
              size={16}
              style={{ marginBottom: -3 }}
            />{" "}
            {title}
          </Text>

          {!isMinimal && onOpenManual ? (
            <Tooltip label="Open manual guide">
              <ActionIcon
                variant="subtle"
                color="orange"
                radius="md"
                size="sm"
                onMouseDown={(event) => event.stopPropagation()}
                onClick={onOpenManual}
                aria-label="Open manual guide"
                styles={{
                  root: {
                    ...centeredActionIconStyles.root,
                    color: "#8b4b22",
                  },
                }}
              >
                <IconBook size={16} />
              </ActionIcon>
            </Tooltip>
          ) : null}
        </Group>

        <Group gap={6} align="center">
          {!isMinimal ? (
            <>
              <Tooltip label={statusTitle}>
                <Badge
                  color={statusColor}
                  variant="outline"
                  radius="md"
                  size="sm"
                  style={{ textTransform: "none" }}
                  mr="xs"
                >
                  {statusLabel}
                </Badge>
              </Tooltip>

              <Tooltip
                label={
                  isRecording
                    ? "Recording"
                    : "Not recording"
                }
              >
                <ThemeIcon
                  variant={isRecording ? "light" : "subtle"}
                  color={isRecording ? "red" : "gray"}
                  radius="md"
                  size="sm"
                  style={{
                    color: isRecording ? "#dc2626" : "#8b4b22",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {isRecording ? (
                    <IconMicrophone size={16} />
                  ) : (
                    <IconMicrophoneOff size={16} />
                  )}
                </ThemeIcon>
              </Tooltip>

              <Tooltip label="Open notifications">
                <Indicator
                  disabled={notificationCount === 0}
                  color="red"
                  label={notificationCount > 9 ? "9+" : notificationCount}
                  size={14}
                  offset={4}
                >
                  <ActionIcon
                    variant="subtle"
                    color="orange"
                    radius="md"
                    size="sm"
                    onMouseDown={(event) => event.stopPropagation()}
                    onClick={onOpenHistory}
                    aria-label="Open notifications"
                    styles={{
                      root: {
                        ...centeredActionIconStyles.root,
                        color: "#8b4b22",
                      },
                    }}
                  >
                    <IconBell
                      size={16}
                    />
                  </ActionIcon>
                </Indicator>
              </Tooltip>

              <Tooltip label="Open settings">
                <ActionIcon
                  variant="subtle"
                  color="orange"
                  radius="md"
                  size="sm"
                  onMouseDown={(event) => event.stopPropagation()}
                  onClick={onOpenSettings}
                  aria-label="Open settings"
                  styles={{
                    root: {
                      ...centeredActionIconStyles.root,
                      color: "#8b4b22",
                    },
                  }}
                >
                  <IconSettings size={16} />
                </ActionIcon>
              </Tooltip>

              <Tooltip label={isAlwaysOnTop ? "Disable always on top" : "Enable always on top"}>
                <ActionIcon
                  variant={isAlwaysOnTop ? "light" : "subtle"}
                  color="orange"
                  radius="md"
                  size="sm"
                  onMouseDown={(event) => event.stopPropagation()}
                  onClick={onToggleAlwaysOnTop}
                  aria-label={
                    isAlwaysOnTop
                      ? "Disable always on top"
                      : "Enable always on top"
                  }
                  styles={{
                    root: {
                      ...centeredActionIconStyles.root,
                      color: isAlwaysOnTop ? "#f97316" : "#8b4b22",
                    },
                  }}
                >
                  <IconPinned size={16} />
                </ActionIcon>
              </Tooltip>
            </>
          ) : null}

          <Tooltip label={isMinimal ? "Close window" : "Close Avera Desk"}>
            <ActionIcon
              variant="subtle"
              color="red"
              radius="md"
              size="sm"
              onMouseDown={(event) => event.stopPropagation()}
              onClick={onClose}
              aria-label={isMinimal ? "Close window" : "Close Avera Desk"}
              styles={{
                root: {
                  ...centeredActionIconStyles.root,
                  color: "#8b4b22",
                },
              }}
            >
              <IconX size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>
    </Box>
  );
}