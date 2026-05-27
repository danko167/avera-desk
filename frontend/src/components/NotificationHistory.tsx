import { Badge, Group, Paper, Popover, ScrollArea, Stack, Text } from "@mantine/core";
import { IconBell, IconCalendarEvent, IconMail } from "@tabler/icons-react";
import { useState } from "react";
import type { ConversationTurn, Notification } from "../lib/api";
import {
  getNotificationContextLine,
  getNotificationHeadline,
  isEmailNotification,
  parseCalendarProposalNotification,
  parseFollowUpNotification,
} from "../lib/api";
import { getSeverityPalette } from "../lib/severity";
import { formatDateTime, timestampToMs } from "../lib/time";

type NotificationHistoryProps = {
  notifications: Notification[];
  turns: ConversationTurn[];
  activeNotificationId: string | null;
  onSelectNotification: (id: string) => void;
};

export function NotificationHistory({
  notifications,
  turns,
  activeNotificationId,
  onSelectNotification,
}: NotificationHistoryProps) {
  const [openTokenNotificationId, setOpenTokenNotificationId] = useState<string | null>(null);

  const getTurnBadge = (role: string) => {
    if (role === "assistant") {
      return { label: "decision", color: "grape" };
    }
    return { label: "user reply", color: "teal" };
  };

  const formatTokenBadge = (value: number | null | undefined) =>
    value && value > 0 ? `LLM ${value.toLocaleString()} tok` : null;

  const linkedTurnsByNotification = new Map<string, ConversationTurn[]>();
  for (const turn of turns) {
    if (!turn.notification_id) {
      continue;
    }
    const existing = linkedTurnsByNotification.get(turn.notification_id) ?? [];
    existing.push(turn);
    linkedTurnsByNotification.set(turn.notification_id, existing);
  }

  for (const [notificationId, linkedTurns] of linkedTurnsByNotification.entries()) {
    linkedTurnsByNotification.set(
      notificationId,
      [...linkedTurns].sort(
        (a, b) => timestampToMs(b.timestamp) - timestampToMs(a.timestamp)
      )
    );
  }

  const userInitiatedTurns = turns.filter((turn) => !turn.notification_id);

  const timeline = [
    ...notifications.map((notification) => ({
      id: `n:${notification.id}`,
      timestamp: notification.timestamp,
      type: "notification" as const,
      notification,
    })),
    ...userInitiatedTurns.map((turn) => ({
      id: `t:${turn.id}`,
      timestamp: turn.timestamp,
      type: "turn" as const,
      turn,
    })),
  ].sort((a, b) => timestampToMs(b.timestamp) - timestampToMs(a.timestamp));

  return (
    <ScrollArea h="100%" pr="xs">
      <Stack gap="xs">
        {timeline.length === 0 ? (
          <Text size="sm" c="dimmed">
            No history yet.
          </Text>
        ) : (
          timeline.map((entry) => {
            if (entry.type === "notification") {
              const notification = entry.notification;
              const palette = getSeverityPalette(notification.type);
              const parsedFollowup = parseFollowUpNotification(notification.message);
              const parsedCalendar = parseCalendarProposalNotification(notification.message);
              const isCalendarNotification = parsedCalendar !== null;
              const emailNotification = isEmailNotification(notification);
              const contextLine = getNotificationContextLine(notification);
              const hasStructuredHeadline = Boolean((notification.details?.headline ?? "").trim());
              const displayMessage = hasStructuredHeadline
                ? getNotificationHeadline(notification)
                : (parsedFollowup?.message ?? getNotificationHeadline(notification));
              const linkedTurns = linkedTurnsByNotification.get(notification.id) ?? [];
              const latestLinkedTurn = linkedTurns[0] ?? null;
              const olderReplyCount = Math.max(0, linkedTurns.length - 1);
              const tokenBadgeLabel = formatTokenBadge(notification.llm_total_tokens);
              return (
                <Paper
                  key={entry.id}
                  withBorder
                  radius="md"
                  p="6px"
                  bg={
                    notification.id === activeNotificationId
                      ? "rgba(249, 115, 22, 0.14)"
                      : "rgba(255, 255, 255, 0.6)"
                  }
                  style={{
                    borderColor:
                      notification.id === activeNotificationId
                        ? "rgba(249, 115, 22, 0.38)"
                        : "rgba(234, 88, 12, 0.16)",
                    cursor: "pointer",
                  }}
                  onClick={() => onSelectNotification(notification.id)}
                >
                  <Stack gap={4}>
                    <Group justify="space-between" align="center" wrap="nowrap">
                      <Group gap={4} wrap="nowrap">
                        <Badge
                          size="xs"
                          radius="md"
                          variant="light"
                          color={
                            isCalendarNotification
                              ? "teal"
                              : emailNotification
                                ? "blue"
                                : palette.badge
                          }
                          style={{ width: "fit-content" }}
                        >
                          {isCalendarNotification ? "calendar" : emailNotification ? "email" : palette.label}
                        </Badge>
                        {tokenBadgeLabel ? (
                          <Popover
                            opened={openTokenNotificationId === notification.id}
                            onChange={(opened) => setOpenTokenNotificationId(opened ? notification.id : null)}
                            position="bottom-start"
                            withArrow
                            shadow="md"
                            offset={8}
                          >
                            <Popover.Target>
                              <Badge
                                size="xs"
                                radius="md"
                                variant="light"
                                color="cyan"
                                style={{ width: "fit-content", cursor: "default" }}
                                onMouseEnter={() => setOpenTokenNotificationId(notification.id)}
                                onMouseLeave={() => setOpenTokenNotificationId(null)}
                              >
                                {tokenBadgeLabel}
                              </Badge>
                            </Popover.Target>
                            <Popover.Dropdown>
                              <Stack gap={2}>
                                <Text size="xs" fw={600}>
                                  LLM usage
                                </Text>
                                <Text size="xs" c="dimmed">
                                  Prompt: {notification.llm_prompt_tokens?.toLocaleString() ?? 0}
                                </Text>
                                <Text size="xs" c="dimmed">
                                  Completion: {notification.llm_completion_tokens?.toLocaleString() ?? 0}
                                </Text>
                                <Text size="xs" c="dimmed">
                                  Total: {notification.llm_total_tokens?.toLocaleString() ?? 0}
                                </Text>
                              </Stack>
                            </Popover.Dropdown>
                          </Popover>
                        ) : null}
                      </Group>
                      {isCalendarNotification ? (
                        <IconCalendarEvent size={14} stroke={1.9} color="#0f766e" />
                      ) : emailNotification ? (
                        <IconMail size={14} stroke={1.9} color="#1d4ed8" />
                      ) : (
                        <IconBell size={14} stroke={1.9} color="#9a3412" />
                      )}
                    </Group>
                    <Text fw={600} fz="xs" lineClamp={2}>
                      {displayMessage}
                    </Text>
                    {contextLine ? (
                      <Text size="xs" c="dimmed" lineClamp={2}>
                        {contextLine}
                      </Text>
                    ) : null}
                    {latestLinkedTurn ? (
                      <Stack gap={2}>
                        <Badge
                          size="xs"
                          radius="md"
                          variant="light"
                          color={getTurnBadge(latestLinkedTurn.role).color}
                          style={{ width: "fit-content" }}
                        >
                          {getTurnBadge(latestLinkedTurn.role).label}
                        </Badge>
                        <Text size="xs" c="dimmed" lineClamp={2}>
                          {latestLinkedTurn.text}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {formatDateTime(latestLinkedTurn.timestamp)}
                        </Text>
                        {olderReplyCount > 0 ? (
                          <Text size="xs" c="dimmed">
                            {olderReplyCount} more update{olderReplyCount === 1 ? "" : "s"} before this one
                          </Text>
                        ) : null}
                      </Stack>
                    ) : null}
                    <Text size="xs" c="dimmed" mt={2}>
                      {formatDateTime(notification.timestamp)}
                    </Text>
                  </Stack>
                </Paper>
              );
            }

            const turn = entry.turn;

            return (
              <Paper
                key={entry.id}
                withBorder
                radius="md"
                p="6px"
                bg="rgba(255, 255, 255, 0.6)"
                style={{
                  borderColor: "rgba(234, 88, 12, 0.16)",
                }}
              >
                <Stack gap={4}>
                  <Badge
                    size="xs"
                    radius="md"
                    variant="light"
                    color="blue"
                    style={{ width: "fit-content" }}
                  >
                    user initiated
                  </Badge>
                  <Text fw={600} fz="xs" lineClamp={3}>
                    {turn.text}
                  </Text>
                  <Text size="xs" c="dimmed" mt={2}>
                    {formatDateTime(turn.timestamp)}
                  </Text>
                </Stack>
              </Paper>
            );
          })
        )}
      </Stack>
    </ScrollArea>
  );
}