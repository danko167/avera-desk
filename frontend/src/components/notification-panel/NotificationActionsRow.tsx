import { Button, Group } from "@mantine/core";

type NotificationActionsRowProps = {
  badgeColor: string;
  onDismiss: () => void;
  isDismissingNotification: boolean;
};

export function NotificationActionsRow({
  badgeColor,
  onDismiss,
  isDismissingNotification,
}: NotificationActionsRowProps) {
  return (
    <Group justify="end">
      <Button size="xs" color={badgeColor} onClick={onDismiss} loading={isDismissingNotification} disabled={isDismissingNotification}>
        {isDismissingNotification ? "Dismissing..." : "Dismiss"}
      </Button>
    </Group>
  );
}
