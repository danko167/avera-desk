import { Modal, Stack, Text } from "@mantine/core";

import type { Notification } from "../../lib/api";

function pickFirstNonEmptyString(values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

type EmailDetailsModalProps = {
  notification: Notification;
  opened: boolean;
  onClose: () => void;
};

export function EmailDetailsModal({ notification, opened, onClose }: EmailDetailsModalProps) {
  const emailDetailsRecord = notification.details as Record<string, unknown> | null | undefined;
  const originalEmailText = pickFirstNonEmptyString([
    emailDetailsRecord?.original_email_text,
    emailDetailsRecord?.original_text,
    emailDetailsRecord?.body_text,
    emailDetailsRecord?.body,
    emailDetailsRecord?.snippet,
    emailDetailsRecord?.body_preview,
  ]);

  return (
    <Modal opened={opened} onClose={onClose} title="Email details" size="lg" centered>
      <Stack gap="sm">
        {originalEmailText ? (
          <div>
            <Text size="xs" fw={600} c="dimmed" mb={4}>
              Original email text
            </Text>
            <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {originalEmailText}
            </Text>
          </div>
        ) : (
          <Text size="sm" c="dimmed">
            Original email text is not available in this notification payload yet.
          </Text>
        )}

        {notification.details?.followup_summary ? (
          <div>
            <Text size="xs" fw={600} c="dimmed" mb={4}>
              Follow-up summary
            </Text>
            <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {notification.details.followup_summary}
            </Text>
          </div>
        ) : null}

        {notification.source_email_id ? (
          <div>
            <Text size="xs" fw={600} c="dimmed" mb={4}>
              Source email ID
            </Text>
            <Text size="xs" style={{ wordBreak: "break-word" }}>
              {notification.source_email_id}
            </Text>
          </div>
        ) : null}
      </Stack>
    </Modal>
  );
}
