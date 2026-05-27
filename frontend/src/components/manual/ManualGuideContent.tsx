import { Button, Group, List, Paper, ScrollArea, Stack, Text, ThemeIcon, Box } from "@mantine/core";
import {
  IconBellRinging,
  IconCalendarEvent,
  IconChecks,
  IconDeviceDesktop,
  IconMail,
  IconMicrophone,
  IconSparkles,
  type Icon,
} from "@tabler/icons-react";
import type { ReactNode } from "react";

type ManualGuideContentProps = {
  isSetupRequired: boolean;
  onOpenSetup: () => void;
};

export function ManualGuideContent({
  isSetupRequired,
  onOpenSetup,
}: ManualGuideContentProps) {
  const sections: Array<{ title: string; icon: Icon; items: ReactNode[] }> = [
    {
      title: "Notifications and review",
      icon: IconBellRinging,
      items: [
        "Get attention notifications from your connected mailbox and agent.",
        "Open history from the bell icon to review previous notifications.",
        "Dismiss the current notification after you are done.",
      ],
    },
    {
      title: "Voice and command input",
      icon: IconMicrophone,
      items: [
        <>
          Use <strong>Ctrl+Space</strong> as <em>push-to-talk</em>: hold to record, release to send.
        </>,
        "If text input mode is enabled in settings, you can type commands instead of speaking.",
      ],
    },
    {
      title: "Email draft workflow",
      icon: IconMail,
      items: [
        "Review generated draft suggestions for recipient, subject, and body.",
        "Edit any field before taking action.",
        "Save draft, send now, or cancel from the notification panel.",
      ],
    },
    {
      title: "Calendar workflow",
      icon: IconCalendarEvent,
      items: [
        "Review proposed title, start/end time, attendees, and notes.",
        "Adjust proposal details before confirming.",
        "Approve to proceed or cancel if the proposal is not correct.",
      ],
    },
    {
      title: "Tray and windows",
      icon: IconDeviceDesktop,
      items: [
        "Left click the tray icon to bring Avera Desk to front.",
        "Open Settings from tray to configure providers and behavior.",
        "Use Open Manual from tray any time to return to this guide.",
        "Quit from tray when you want to fully close the desktop app.",
      ],
    },
    {
      title: "Quick checks if something looks off",
      icon: IconChecks,
      items: [
        "In Settings, confirm mailbox authentication is connected.",
        "If commands are ignored, verify Ctrl+Space is not blocked by another app.",
        "If no new items appear, open history and verify recent events are arriving.",
      ],
    },
  ];

  return (
    <Box
      style={{
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Paper
        radius="md"
        p="xs"
        style={{
          background:
            "linear-gradient(130deg, rgba(255, 241, 229, 0.95) 0%, rgba(255, 255, 255, 0.9) 55%, rgba(255, 248, 237, 0.92) 100%)",
        }}
      >
        <Group justify="space-between" align="center" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <ThemeIcon color="orange" variant="light" size="md" radius="xl">
              <IconSparkles size={16} />
            </ThemeIcon>
            <Stack gap={0}>
              <Text size="sm" fw={700}>Avera Desk Manual</Text>
              <Text size="xs" c="dimmed">Practical guide for day-to-day usage. In other words: what you can do in Avera Desk</Text>
            </Stack>
          </Group>
        </Group>
      </Paper>

      <ScrollArea
        type="auto"
        offsetScrollbars="present"
        scrollbarSize={10}
        p="xs"
        style={{ flex: 1, minHeight: 0 }}
        styles={{
          viewport: {
            paddingRight: 4,
          },
          scrollbar: {
            background: "transparent",
          },
          thumb: {
            backgroundColor: "rgba(234, 88, 12, 0.33)",
            border: "2px solid rgba(255, 243, 232, 0.9)",
          },
        }}
      >
        {sections.map(({ title, icon: SectionIcon, items }) => (
          <>
            <Group gap="xs" mb={6} wrap="nowrap">
              <ThemeIcon color="orange" variant="light" size="sm" radius="xl">
                <SectionIcon size={14} />
              </ThemeIcon>
              <Text size="sm" fw={600}>{title}</Text>
            </Group>

            <List size="xs" spacing={5} withPadding mb="md">
              {items.map((item, index) => (
                <List.Item key={`${title}-${index}`}>{item}</List.Item>
              ))}
            </List>
          </>
        ))}

        <Stack gap={6} mt="xs" pb={2}>
          {isSetupRequired ? (
            <Button size="xs" variant="light" color="orange" onClick={onOpenSetup}>
              Open Setup
            </Button>
          ) : null}
        </Stack>
      </ScrollArea>
    </Box>
  );
}
