import { Box, Button, Stack, Text, Title } from "@mantine/core";
import { NarrativeLoader } from "@danko167/narrative-loader";
import { REQUEST_PROCESSING_MESSAGES } from "../lib/narrativeLoader";

function getTranscriptPreview(liveTranscript: string): string {
  const trimmed = liveTranscript.trim();
  if (!trimmed) {
    return "Transcript will appear here in real time.";
  }

  const normalized = trimmed.toLowerCase();
  if (
    normalized === "listening..." ||
    normalized === 'listening locally... say "avera"' ||
    normalized === 'listening... (say "avera")' ||
    normalized === "listening for your command..." ||
    normalized === "processing..." ||
    normalized === "no speech detected."
  ) {
    return "Transcript will appear here in real time.";
  }

  return liveTranscript;
}

type NoNotificationsProps = {
  liveTranscript: string;
  audioControls: React.ReactNode;
  isFeedbackProcessing: boolean;
  recognizedActionLabel: string | null;
  mailboxConnected: boolean;
  onOpenSettings: () => void;
};

export function NoNotifications({
  liveTranscript,
  audioControls,
  isFeedbackProcessing,
  recognizedActionLabel,
  mailboxConnected,
  onOpenSettings,
}: NoNotificationsProps) {
  if (!mailboxConnected) {
    return (
      <Stack justify="center" align="center" style={{ height: "100%" }} gap={8}>
        <Title order={4} ta="center">
          Mailbox is disconnected
        </Title>
        <Text c="dimmed" ta="center" maw={340} size="xs">
          Avera can&apos;t receive new notifications or process inbox actions until you connect a mailbox.
        </Text>
        <Button size="xs" onClick={onOpenSettings}>
          Open Settings
        </Button>
      </Stack>
    );
  }

  return (
    <Stack justify="flex-start" align="center" style={{ height: "100%" }} gap={5}>
      <Title order={4} ta="center">
        No active notifications
      </Title>
      <Text c="dimmed" ta="center" maw={320} size="xs">
        Waiting for your agents to trigger the next attention event.
      </Text>
      <Box my={5}>{audioControls}</Box>
      <Text size="xs" c="dimmed" ta="center" lineClamp={1}>
        {getTranscriptPreview(liveTranscript)}
      </Text>
      {isFeedbackProcessing ? (
        <NarrativeLoader
          loading
          doneMessage={false}
          tone="friendly"
          variant="analysis"
          useEmojis
          emojiPosition="start"
          messages={REQUEST_PROCESSING_MESSAGES}
          className="avera-narrative-loader"
        />
      ) : recognizedActionLabel ? (
        <Text size="xs" c="dimmed" ta="center" lineClamp={1}>
          {recognizedActionLabel}
        </Text>
      ) : null}
    </Stack>
  );
}
