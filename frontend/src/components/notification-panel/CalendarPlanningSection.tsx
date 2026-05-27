import { ActionIcon, Badge, Paper, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { IconChevronDown, IconChevronUp, IconDots } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import type { CalendarProposal } from "../../lib/api";
import { formatDateTime } from "../../lib/time";
import { ConfirmCancelActions } from "./ConfirmCancelActions";

const parseLocalDateTime = (value: string): Date => {
  const normalized = value.trim().replace(" ", "T");
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
};

const parseLocalDateTimeOrNull = (value: string): Date | null => {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = new Date(trimmed.replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatLocalDateTime = (value: Date): string => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  const hours = String(value.getHours()).padStart(2, "0");
  const minutes = String(value.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

const stepDateTime = (value: string, minutesDelta: number): string => {
  const next = parseLocalDateTime(value);
  next.setMinutes(next.getMinutes() + minutesDelta, 0, 0);
  return formatLocalDateTime(next);
};

type CalendarPlanningSectionProps = {
  showCalendarPanel: boolean;
  controlsDisabled: boolean;
  isCalendarPlanning: boolean;
  isCalendarSaving: boolean;
  proposalTitle: string;
  proposalStartAtInput: string;
  proposalEndAtInput: string;
  proposalAttendeesInput: string;
  proposalNotes: string;
  calendarError: string | null;
  activeCalendarProposal: CalendarProposal | null;
  onProposalTitleChange: (value: string) => void;
  onProposalStartAtChange: (value: string) => void;
  onProposalEndAtChange: (value: string) => void;
  onProposalAttendeesChange: (value: string) => void;
  onProposalNotesChange: (value: string) => void;
  onCalendarApprove: () => void;
  onCalendarCancel: () => void;
};

export function CalendarPlanningSection({
  showCalendarPanel,
  controlsDisabled,
  isCalendarPlanning,
  isCalendarSaving,
  proposalTitle,
  proposalStartAtInput,
  proposalEndAtInput,
  proposalAttendeesInput,
  proposalNotes,
  calendarError,
  activeCalendarProposal,
  onProposalTitleChange,
  onProposalStartAtChange,
  onProposalEndAtChange,
  onProposalAttendeesChange,
  onProposalNotesChange,
  onCalendarApprove,
  onCalendarCancel,
}: CalendarPlanningSectionProps) {
  const [showAttendeeSuggestions, setShowAttendeeSuggestions] = useState(true);

  const applyStartDateTime = (nextStart: string) => {
    onProposalStartAtChange(nextStart);

    const startDate = parseLocalDateTimeOrNull(nextStart);
    const endDate = parseLocalDateTimeOrNull(proposalEndAtInput);
    if (startDate && endDate && endDate < startDate) {
      onProposalEndAtChange(formatLocalDateTime(startDate));
    }
  };

  const applyEndDateTime = (nextEnd: string) => {
    const startDate = parseLocalDateTimeOrNull(proposalStartAtInput);
    const endDate = parseLocalDateTimeOrNull(nextEnd);
    if (startDate && endDate && endDate < startDate) {
      onProposalEndAtChange(formatLocalDateTime(startDate));
      return;
    }

    onProposalEndAtChange(nextEnd);
  };

  const applyAttendeeSuggestion = (email: string) => {
    const trimmed = email.trim().toLowerCase();
    if (!trimmed) {
      return;
    }

    const current = proposalAttendeesInput
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter((item, index, all) => item.length > 0 && all.indexOf(item) === index);

    if (current.includes(trimmed)) {
      return;
    }

    onProposalAttendeesChange([...current, trimmed].join(", "));
    setShowAttendeeSuggestions(false);
  };

  useEffect(() => {
    setShowAttendeeSuggestions(true);
  }, [activeCalendarProposal?.id]);

  if (!showCalendarPanel) {
    return null;
  }

  const sortedAttendeeSuggestions = (activeCalendarProposal?.attendee_suggestions ?? [])
    .slice()
    .sort((left, right) => right.confidence - left.confidence)
    .slice(0, 6);

  return (
    <Paper
      p={6}
      radius="md"
      bg="rgba(255,255,255,0.7)"
      style={{ border: "1px solid rgba(13, 148, 136, 0.24)" }}
    >
      <Stack gap={2}>
        <Text size="xs" fw={600} c="dimmed">
          Calendar planning
        </Text>
        <TextInput
          label="Meeting title"
          size="xs"
          value={proposalTitle}
          disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
          onChange={(event) => onProposalTitleChange(event.currentTarget.value)}
          placeholder="Meeting title"
        />
        <DateTimePicker
          label="Start"
          size="xs"
          value={proposalStartAtInput || null}
          disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
          onChange={(value) => applyStartDateTime(value ?? "")}
          placeholder="Select start"
          clearable
          popoverProps={{ withinPortal: true }}
          timePickerProps={{
            minutesStep: 30,
            rightSection: (
              <Stack gap={0}>
                <ActionIcon
                  size="xs"
                  variant="subtle"
                  color="gray"
                  aria-label="Increase start time by 30 minutes"
                  onClick={() => applyStartDateTime(stepDateTime(proposalStartAtInput, 30))}
                  disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
                >
                  <IconChevronUp size={12} />
                </ActionIcon>
                <ActionIcon
                  size="xs"
                  variant="subtle"
                  color="gray"
                  aria-label="Decrease start time by 30 minutes"
                  onClick={() => applyStartDateTime(stepDateTime(proposalStartAtInput, -30))}
                  disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
                >
                  <IconChevronDown size={12} />
                </ActionIcon>
              </Stack>
            ),
            rightSectionPointerEvents: "all",
            rightSectionWidth: 22,
          }}
          valueFormat="YYYY-MM-DD HH:mm"
        />
        <DateTimePicker
          label="End"
          size="xs"
          value={proposalEndAtInput || null}
          disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
          onChange={(value) => applyEndDateTime(value ?? "")}
          placeholder="Select end"
          clearable
          popoverProps={{ withinPortal: true }}
          minDate={parseLocalDateTimeOrNull(proposalStartAtInput) ?? undefined}
          timePickerProps={{
            minutesStep: 30,
            rightSection: (
              <Stack gap={0}>
                <ActionIcon
                  size="xs"
                  variant="subtle"
                  color="gray"
                  aria-label="Increase end time by 30 minutes"
                  onClick={() => applyEndDateTime(stepDateTime(proposalEndAtInput, 30))}
                  disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
                >
                  <IconChevronUp size={12} />
                </ActionIcon>
                <ActionIcon
                  size="xs"
                  variant="subtle"
                  color="gray"
                  aria-label="Decrease end time by 30 minutes"
                  onClick={() => applyEndDateTime(stepDateTime(proposalEndAtInput, -30))}
                  disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
                >
                  <IconChevronDown size={12} />
                </ActionIcon>
              </Stack>
            ),
            rightSectionPointerEvents: "all",
            rightSectionWidth: 22,
          }}
          valueFormat="YYYY-MM-DD HH:mm"
        />
        <TextInput
          label="Attendees (comma separated)"
          size="xs"
          value={proposalAttendeesInput}
          disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
          onChange={(event) => onProposalAttendeesChange(event.currentTarget.value)}
          placeholder="john@doe.com, jane@doe.com"
          rightSection={sortedAttendeeSuggestions.length > 0 ? (
            <ActionIcon
              size="sm"
              variant="subtle"
              color="gray"
              aria-label="Toggle attendee suggestions"
              onClick={() => setShowAttendeeSuggestions((previous) => !previous)}
              disabled={controlsDisabled || isCalendarSaving}
            >
              <IconDots size={14} />
            </ActionIcon>
          ) : undefined}
          rightSectionPointerEvents="all"
        />
        <Textarea
          label="Notes (optional)"
          minRows={2}
          autosize
          size="xs"
          value={proposalNotes}
          disabled={controlsDisabled || isCalendarPlanning || isCalendarSaving}
          onChange={(event) => onProposalNotesChange(event.currentTarget.value)}
          placeholder="Optional context for this proposal"
        />
        {calendarError ? <Text size="xs" c="red">{calendarError}</Text> : null}

        {sortedAttendeeSuggestions.length > 0 && showAttendeeSuggestions ? (
          <Stack gap={2}>
            <Text size="xs" fw={600}>Suggested attendees</Text>
            <Stack gap={4}>
              {sortedAttendeeSuggestions.map((suggestion) => (
                <Badge
                  key={suggestion.email}
                  size="xs"
                  variant="light"
                  color="grape"
                  style={{ cursor: controlsDisabled || isCalendarSaving ? "default" : "pointer", width: "fit-content" }}
                  onClick={() => {
                    if (controlsDisabled || isCalendarSaving) {
                      return;
                    }
                    applyAttendeeSuggestion(suggestion.email);
                  }}
                >
                  {suggestion.label ? `${suggestion.label} <${suggestion.email}>` : suggestion.email} ({Math.round(suggestion.confidence * 100)}%)
                </Badge>
              ))}
            </Stack>
          </Stack>
        ) : null}

        {activeCalendarProposal ? (
          <Stack gap={4}>
            <Text size="xs" c="dimmed">
              Proposal status: {activeCalendarProposal.status}
            </Text>
            {activeCalendarProposal.conflicts.length > 0 ? (
              <Stack gap={2}>
                <Text size="xs" fw={700} c="red">Conflicts</Text>
                {activeCalendarProposal.conflicts.slice(0, 4).map((conflict, index) => (
                  <Text key={`${conflict.start_at}-${index}`} size="xs" c="dimmed">
                    {conflict.title}: {formatDateTime(conflict.start_at)} - {formatDateTime(conflict.end_at)}
                  </Text>
                ))}
              </Stack>
            ) : (
              <Text size="xs" c="dimmed">No conflicts detected.</Text>
            )}

            {activeCalendarProposal.options.length > 0 ? (
              <Stack gap={2}>
                <Text size="xs" fw={600}>Suggested options</Text>
                {activeCalendarProposal.options.slice(0, 3).map((option, index) => (
                  <Badge key={`${option.start_at}-${index}`} size="xs" variant="light" color="blue">
                    {formatDateTime(option.start_at)} - {formatDateTime(option.end_at)} ({Math.round(option.confidence * 100)}%)
                  </Badge>
                ))}
              </Stack>
            ) : null}

            <ConfirmCancelActions
              onCancel={onCalendarCancel}
              onConfirm={onCalendarApprove}
              disabled={controlsDisabled}
              loading={isCalendarSaving}
              cancelLabel="Cancel"
              confirmLabel="Send now"
            />
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}
