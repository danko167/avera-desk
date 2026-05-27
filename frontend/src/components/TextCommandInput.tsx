import { Button, Group, Kbd, Stack, Text, TextInput } from "@mantine/core";
import { useState } from "react";

type TextCommandInputProps = {
  onSubmit: (text: string) => void;
  disabled?: boolean;
};

export function TextCommandInput({ onSubmit, disabled = false }: TextCommandInputProps) {
  const [text, setText] = useState("");

  const trimmed = text.trim();

  const submit = () => {
    if (disabled || !trimmed) {
      return;
    }
    onSubmit(trimmed);
    setText("");
  };

  return (
    <Stack gap={6}>
      <Group gap={6}>
        <TextInput
          size="xs"
          placeholder="Type a command..."
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !disabled) {
              event.preventDefault();
              submit();
            }
          }}
        />

        <Button size="xs" onClick={submit} disabled={disabled || !trimmed}>
          Send
        </Button>
        <Button
          size="xs"
          variant="default"
          onClick={() => setText("")}
          disabled={disabled || !text.length}
        >
          Clear
        </Button>
      </Group>
      <Group gap={4} justify="center" wrap="wrap">
        <Kbd>Enter</Kbd>
        <Text size="xs" c="dimmed">to send</Text>
      </Group>
    </Stack>
  );
}
