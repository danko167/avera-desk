import { Box, Group, Kbd, Paper, Text } from "@mantine/core";

export function PushToTalkHint() {
  return (
    <Box
      style={{
        position: "fixed",
        left: 4,
        bottom: 4,
        zIndex: 999,
        pointerEvents: "none",
      }}
    >
      <Paper
        withBorder
        radius="md"
        p={6}
        shadow="md"
        bg="rgba(255, 255, 255, 0.78)"
        style={{
          pointerEvents: "auto",
          width: "fit-content",
          borderColor: "rgba(234, 88, 12, 0.18)",
          backdropFilter: "blur(14px)",
        }}
      >
        <Group gap={4} justify="center" wrap="wrap">
          <Kbd size="xs">Ctrl</Kbd>
          <Text size="xs" c="dimmed">+</Text>
          <Kbd size="xs">Space</Kbd>
          <Text size="xs" c="dimmed">to talk</Text>
        </Group>
      </Paper>
    </Box>
  );
}