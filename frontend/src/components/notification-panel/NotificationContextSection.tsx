import { Badge, Box, Button, Group, Paper, Stack, Text } from "@mantine/core";
import { NarrativeLoader } from "@danko167/narrative-loader";
import type { ReactNode } from "react";
import type { ConversationTurn, FollowUpItem } from "../../lib/api";
import { RESPONSE_PROCESSING_MESSAGES } from "../../lib/narrativeLoader";
import { formatDateTime } from "../../lib/time";

type NotificationContextSectionProps = {
  interactionsBlocked: boolean;
  onOpenSettings: () => void;
  audioControls: ReactNode;
  isFeedbackProcessing: boolean;
  liveTranscript: string;
  linkedTurns: ConversationTurn[];
  followUpDetails: FollowUpItem | null;
};

function getTurnBadge(role: string) {
  if (role === "assistant") {
    return { label: "Decision", color: "grape" };
  }

  return { label: "You", color: "teal" };
}

export function NotificationContextSection({
  interactionsBlocked,
  onOpenSettings,
  audioControls,
  isFeedbackProcessing,
  liveTranscript,
  linkedTurns,
  followUpDetails,
}: NotificationContextSectionProps) {
  return (
    <>
      {interactionsBlocked ? (
        <Paper
          p={6}
          radius="md"
          bg="rgba(255,255,255,0.7)"
          style={{ border: "1px solid rgba(217, 119, 6, 0.24)" }}
        >
          <Stack gap={6}>
            <Text size="xs" fw={600} c="orange">
              Mailbox is disconnected
            </Text>
            <Text size="xs" c="dimmed">
              Review is still available, but Avera cannot process new inbox or calendar actions until you reconnect.
            </Text>
            <Group justify="flex-end">
              <Button size="xs" onClick={onOpenSettings}>
                Open Settings
              </Button>
            </Group>
          </Stack>
        </Paper>
      ) : (
        audioControls
      )}

      <Paper
        p={5}
        radius="md"
        bg="rgba(255,255,255,0.62)"
        style={{
          border: "1px solid rgba(234, 88, 12, 0.14)",
        }}
      >
        {isFeedbackProcessing ? (
          <Box mb={4}>
            <NarrativeLoader
              loading
              doneMessage={false}
              tone="friendly"
              variant="analysis"
              useEmojis
              emojiPosition="start"
              messages={RESPONSE_PROCESSING_MESSAGES}
              className="avera-narrative-loader"
            />
          </Box>
        ) : null}
        <Text size="xs" c="dimmed" lineClamp={1}>
          {liveTranscript || "Transcript will appear here in real time."}
        </Text>
      </Paper>

      {linkedTurns.length > 0 ? (
        <Paper
          p={5}
          radius="md"
          bg="rgba(255,255,255,0.62)"
          style={{
            border: "1px solid rgba(22, 163, 74, 0.18)",
          }}
        >
          <Stack gap={4}>
            <Text size="xs" fw={600} c="dimmed">
              Conversation
            </Text>
            {linkedTurns.map((turn) => (
              <Stack key={turn.id} gap={1}>
                <Badge
                  size="xs"
                  radius="md"
                  variant="light"
                  color={getTurnBadge(turn.role).color}
                  style={{ width: "fit-content" }}
                >
                  {getTurnBadge(turn.role).label}
                </Badge>
                <Text size="xs" lineClamp={2}>
                  {turn.text}
                </Text>
                <Text size="xs" c="dimmed">
                  {formatDateTime(turn.timestamp)}
                </Text>
              </Stack>
            ))}
          </Stack>
        </Paper>
      ) : null}

      {followUpDetails ? (
        <Paper
          p={5}
          radius="md"
          bg="rgba(255,255,255,0.62)"
          style={{ border: "1px solid rgba(14, 116, 144, 0.22)" }}
        >
          <Stack gap={4}>
            <Text size="xs" fw={600} c="dimmed">
              Follow-up details
            </Text>
            {followUpDetails.requested_action ? (
              <Text size="xs" lineClamp={2}>
                {followUpDetails.requested_action}
              </Text>
            ) : null}
            <Text size="xs" c="dimmed">
              Status: {followUpDetails.status} | Confidence: {Math.round(followUpDetails.confidence * 100)}%
            </Text>
            <Text size="xs" c="dimmed">
              Next reminder: {formatDateTime(followUpDetails.next_reminder_at)}
            </Text>
          </Stack>
        </Paper>
      ) : null}
    </>
  );
}
