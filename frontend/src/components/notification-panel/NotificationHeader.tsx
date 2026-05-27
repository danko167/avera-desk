import { Badge, Box, Group, Popover, Stack, Text, Title, Tooltip } from "@mantine/core";
import { IconBell, IconCalendarEvent, IconMail } from "@tabler/icons-react";
import { useState } from "react";
import {
  getNotificationContextLine,
  getNotificationHeadline,
  getNotificationInstruction,
  type Notification,
} from "../../lib/api";
import type { SeverityPalette } from "../../lib/severity";
import { formatTime } from "../../lib/time";
import { EmailDetailsModal } from "./EmailDetailsModal";

type NotificationHeaderProps = {
  notification: Notification;
  palette: SeverityPalette;
  hasCalendarTag: boolean;
  isEmailNotification: boolean;
};

export function NotificationHeader({
  notification,
  palette,
  hasCalendarTag,
  isEmailNotification,
}: NotificationHeaderProps) {
  const ActiveIcon = palette.icon;
  const [tokenPopoverOpened, setTokenPopoverOpened] = useState(false);
  const [emailDetailsModalOpened, setEmailDetailsModalOpened] = useState(false);
  const contextLine = getNotificationContextLine(notification);
  const headline = getNotificationHeadline(notification);
  const instruction = getNotificationInstruction(notification);
  const emailSubject = notification.details?.subject ?? undefined;
  const emailFrom = notification.details?.from_email ?? undefined;

  const hasTokenUsage = Boolean(notification.llm_total_tokens && notification.llm_total_tokens > 0);
  const llmTokenLabel = hasTokenUsage
    ? `LLM ${notification.llm_total_tokens?.toLocaleString()} tok`
    : null;

  return (
    <Stack gap={6}>
      <Group gap="xs" justify="space-between">
        <Group gap={6} wrap="nowrap">
          <Badge
            color={hasCalendarTag ? "teal" : isEmailNotification ? "blue" : palette.badge}
            variant="filled"
            radius="md"
            size="xs"
          >
            {hasCalendarTag ? "calendar" : isEmailNotification ? "email" : palette.label}
          </Badge>
          {llmTokenLabel ? (
            <Popover
              opened={tokenPopoverOpened}
              onChange={setTokenPopoverOpened}
              position="bottom-start"
              withArrow
              shadow="md"
              offset={8}
            >
              <Popover.Target>
                <Badge
                  color="cyan"
                  variant="light"
                  radius="md"
                  size="xs"
                  style={{ cursor: "default" }}
                  onMouseEnter={() => setTokenPopoverOpened(true)}
                  onMouseLeave={() => setTokenPopoverOpened(false)}
                >
                  {llmTokenLabel}
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
        <Group gap={4} wrap="nowrap">
          {hasCalendarTag ? (
            <IconCalendarEvent size={14} stroke={1.9} color="#0f766e" />
          ) : isEmailNotification ? (
            <IconMail size={14} stroke={1.9} color="#1d4ed8" />
          ) : (
            <IconBell size={14} stroke={1.9} color="#9a3412" />
          )}
          <Text size="xs" c="dimmed">
            {formatTime(notification.timestamp)}
          </Text>
        </Group>
      </Group>

      <Group gap="xs" align="flex-start" wrap="nowrap">
        <Tooltip label={instruction} withArrow multiline w={280} disabled={!instruction}>
          <Box
            style={{
              borderRadius: 999,
              width: 30,
              height: 30,
              minWidth: 30,
              display: "grid",
              placeItems: "center",
              background: "rgba(255, 255, 255, 0.08)",
              border: `1px solid ${palette.panelBorder}`,
            }}
          >
            {ActiveIcon ? <ActiveIcon size={22} color={palette.highlight} /> : null}
          </Box>
        </Tooltip>

        {isEmailNotification ? (
          <Stack gap={4} style={{ flex: 1 }}>
            <Text size="sm" fw={700} lineClamp={1} title={emailSubject}>
              {notification.details?.subject}
            </Text>
            <Text size="xs" c="dimmed" lineClamp={1} title={emailFrom}>
              From: {notification.details?.from_email}
            </Text>
            {contextLine ? (
              <Text size="xs" lineClamp={2}>
                {contextLine}
              </Text>
            ) : null}
            <Text
              component="button"
              type="button"
              size="xs"
              c="blue"
              onClick={() => setEmailDetailsModalOpened(true)}
              style={{
                alignSelf: "flex-start",
                background: "none",
                border: 0,
                padding: 0,
                cursor: "pointer",
                textDecoration: "underline",
              }}
            >
              View email details
            </Text>

            <EmailDetailsModal
              notification={notification}
              opened={emailDetailsModalOpened}
              onClose={() => setEmailDetailsModalOpened(false)}
            />
          </Stack>
        ) : (
          <Stack gap={2} style={{ flex: 1 }}>
            <Title order={6} fw={700} style={{ letterSpacing: "-0.01em" }} lineClamp={2}>
              {headline}
            </Title>
            {contextLine ? (
              <Text size="xs" lineClamp={2}>
                {contextLine}
              </Text>
            ) : null}
          </Stack>
        )}
      </Group>
    </Stack>
  );
}
