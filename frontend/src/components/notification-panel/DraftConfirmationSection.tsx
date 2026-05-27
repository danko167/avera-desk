import { ActionIcon, Badge, Group, Paper, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { IconDots } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import type { EmailDraft } from "../../lib/api";
import { ConfirmCancelActions } from "./ConfirmCancelActions";

type DraftConfirmationSectionProps = {
  activeDraft: EmailDraft | null;
  controlsDisabled: boolean;
  isDraftSaving: boolean;
  draftRecipient: string;
  draftSubject: string;
  draftBody: string;
  draftSyncHint: string | null;
  draftActionError: string | null;
  onDraftRecipientChange: (value: string) => void;
  onDraftSubjectChange: (value: string) => void;
  onDraftBodyChange: (value: string) => void;
  onDraftUseSuggestion: (email: string) => void;
  onDraftCancel: () => void;
  onDraftSend: () => void;
};

export function DraftConfirmationSection({
  activeDraft,
  controlsDisabled,
  isDraftSaving,
  draftRecipient,
  draftSubject,
  draftBody,
  draftSyncHint,
  draftActionError,
  onDraftRecipientChange,
  onDraftSubjectChange,
  onDraftBodyChange,
  onDraftUseSuggestion,
  onDraftCancel,
  onDraftSend,
}: DraftConfirmationSectionProps) {
  const [showRecipientSuggestions, setShowRecipientSuggestions] = useState(true);
  const suggestionCount = activeDraft?.suggestions.length ?? 0;

  const draftStatusMessage = draftActionError ?? draftSyncHint;
  const draftStatusColor = draftActionError || draftSyncHint === "Autosave failed" ? "red" : "dimmed";

  useEffect(() => {
    setShowRecipientSuggestions(true);
  }, [activeDraft?.id]);

  if (!activeDraft || activeDraft.status !== "pending") {
    return null;
  }

  return (
    <Paper
      p={6}
      radius="md"
      bg="rgba(255,255,255,0.7)"
      style={{ border: "1px solid rgba(2, 132, 199, 0.22)" }}
    >
      <Stack gap={3}>
        <Text size="xs" fw={600} c="dimmed">
          Email draft confirmation
        </Text>
        <Group justify="space-between" align="center" gap="xs" wrap="nowrap">
          <Text size="xs" fw={500}>
            Recipient
          </Text>
          <Text
            size="xs"
            c={draftStatusColor}
            aria-live="polite"
            style={{ minHeight: 18, visibility: draftStatusMessage ? "visible" : "hidden", textAlign: "right" }}
          >
            {draftStatusMessage ?? " "}
          </Text>
        </Group>
        <TextInput
          size="xs"
          value={draftRecipient}
          disabled={controlsDisabled || isDraftSaving}
          onChange={(event) => onDraftRecipientChange(event.currentTarget.value)}
          placeholder="name@example.com"
          rightSection={suggestionCount > 0 ? (
            <ActionIcon
              size="sm"
              variant="subtle"
              color="gray"
              aria-label="Toggle recipient suggestions"
              onClick={() => setShowRecipientSuggestions((previous) => !previous)}
              disabled={controlsDisabled || isDraftSaving}
            >
              <IconDots size={14} />
            </ActionIcon>
          ) : undefined}
          rightSectionPointerEvents="all"
        />
        {suggestionCount > 0 && showRecipientSuggestions ? (
          <Group gap={4}>
            {activeDraft.suggestions.slice(0, 4).map((suggestion) => (
              <Badge
                key={suggestion.email}
                size="xs"
                variant="light"
                color="blue"
                style={{ cursor: controlsDisabled ? "default" : "pointer" }}
                onClick={() => {
                  if (!controlsDisabled) {
                    onDraftUseSuggestion(suggestion.email);
                    setShowRecipientSuggestions(false);
                  }
                }}
              >
                {suggestion.label ? `${suggestion.label} <${suggestion.email}>` : suggestion.email} ({Math.round(suggestion.confidence * 100)}%)
              </Badge>
            ))}
          </Group>
        ) : null}
        <TextInput
          label="Subject"
          size="xs"
          value={draftSubject}
          disabled={controlsDisabled || isDraftSaving}
          onChange={(event) => onDraftSubjectChange(event.currentTarget.value)}
          placeholder="Subject"
        />
        <Textarea
          label="Body"
          minRows={3}
          maxRows={6}
          autosize
          size="xs"
          value={draftBody}
          disabled={controlsDisabled || isDraftSaving}
          onChange={(event) => onDraftBodyChange(event.currentTarget.value)}
        />
        <ConfirmCancelActions
          onCancel={onDraftCancel}
          onConfirm={onDraftSend}
          disabled={controlsDisabled}
          loading={isDraftSaving}
          cancelLabel="Cancel"
          confirmLabel="Send now"
        />
      </Stack>
    </Paper>
  );
}
