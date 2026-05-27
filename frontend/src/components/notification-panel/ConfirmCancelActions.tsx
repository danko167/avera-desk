import { Button, Group } from "@mantine/core";

type ConfirmCancelActionsProps = {
  onCancel: () => void;
  onConfirm: () => void;
  disabled?: boolean;
  loading?: boolean;
  cancelLabel?: string;
  confirmLabel?: string;
};

export function ConfirmCancelActions({
  onCancel,
  onConfirm,
  disabled = false,
  loading = false,
  cancelLabel = "Cancel",
  confirmLabel = "Send now",
}: ConfirmCancelActionsProps) {
  return (
    <Group justify="space-between" mt={2}>
      <Button
        size="xs"
        variant="light"
        color="gray"
        onClick={onCancel}
        disabled={disabled || loading}
      >
        {cancelLabel}
      </Button>
      <Button
        size="xs"
        color="teal"
        onClick={onConfirm}
        loading={loading}
        disabled={disabled || loading}
      >
        {confirmLabel}
      </Button>
    </Group>
  );
}
