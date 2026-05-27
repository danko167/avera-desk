import { useCallback, useEffect, useRef, useState } from "react";
import {
  approveCalendarProposal,
  cancelCalendarProposal,
  fetchCalendarProposalById,
  planCalendarProposal,
  rejectCalendarProposal,
  updateCalendarProposal,
  type CalendarPlanningRequest,
  type CalendarProposal,
  type ParsedCalendarProposalNotification,
} from "../lib/api";
import { createLogger } from "../lib/logger";

type UseCalendarProposalManagerParams = {
  parsedActiveCalendarProposal: ParsedCalendarProposalNotification | null;
};

const logger = createLogger("useCalendarProposalManager");

function formatStartAtForInput(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function parseAttendeesCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter((item, index, all) => item.length > 0 && all.indexOf(item) === index);
}

function buildEditorSignature(params: {
  title: string;
  startAt: string;
  endAt: string;
  attendeesCsv: string;
  notes: string;
}): string {
  return JSON.stringify({
    title: params.title.trim(),
    start_at: params.startAt.trim(),
    end_at: params.endAt.trim(),
    attendees: parseAttendeesCsv(params.attendeesCsv),
    notes: (params.notes || "").trim() || null,
  });
}

export function useCalendarProposalManager({
  parsedActiveCalendarProposal,
}: UseCalendarProposalManagerParams) {
  const [activeCalendarProposal, setActiveCalendarProposal] = useState<CalendarProposal | null>(null);
  const [isCalendarPlanning, setIsCalendarPlanning] = useState(false);
  const [isCalendarSaving, setIsCalendarSaving] = useState(false);
  const [calendarError, setCalendarError] = useState<string | null>(null);

  const [proposalTitle, setProposalTitle] = useState("");
  const [proposalStartAtInput, setProposalStartAtInput] = useState("");
  const [proposalEndAtInput, setProposalEndAtInput] = useState("");
  const [proposalAttendeesInput, setProposalAttendeesInput] = useState("");
  const [proposalNotes, setProposalNotes] = useState("");

  const activeProposalIdRef = useRef<string | null>(null);
  const autoSaveTimerRef = useRef<number | null>(null);
  const isAutoSavingRef = useRef(false);
  const lastSyncedSignatureRef = useRef<string>("");

  const syncEditorFromProposal = useCallback((proposal: CalendarProposal) => {
    setProposalTitle(proposal.title ?? "");
    setProposalStartAtInput(formatStartAtForInput(proposal.start_at));
    setProposalEndAtInput(formatStartAtForInput(proposal.end_at));
    setProposalAttendeesInput((proposal.attendees ?? []).join(", "));
    setProposalNotes(proposal.notes ?? "");
    lastSyncedSignatureRef.current = buildEditorSignature({
      title: proposal.title ?? "",
      startAt: formatStartAtForInput(proposal.start_at),
      endAt: formatStartAtForInput(proposal.end_at),
      attendeesCsv: (proposal.attendees ?? []).join(", "),
      notes: proposal.notes ?? "",
    });
  }, []);

  const refreshCalendarProposal = useCallback(async (proposalId: string) => {
    try {
      const proposal = await fetchCalendarProposalById(proposalId);
      setActiveCalendarProposal(proposal);
      activeProposalIdRef.current = proposal.id;
      syncEditorFromProposal(proposal);
      setCalendarError(null);
    } catch (error) {
      logger.error("Failed to refresh calendar proposal.", error, {
        proposalId,
      });
      setCalendarError(error instanceof Error ? error.message : String(error));
    }
  }, [syncEditorFromProposal]);

  useEffect(() => {
    if (!parsedActiveCalendarProposal) {
      setActiveCalendarProposal(null);
      activeProposalIdRef.current = null;
      setCalendarError(null);
      if (autoSaveTimerRef.current !== null) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
      return;
    }

    void refreshCalendarProposal(parsedActiveCalendarProposal.proposalId);
  }, [parsedActiveCalendarProposal, refreshCalendarProposal]);

  useEffect(() => {
    if (autoSaveTimerRef.current !== null) {
      window.clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }

    const proposal = activeCalendarProposal;
    if (!proposal || !(proposal.status === "proposed" || proposal.status === "awaiting_user_decision")) {
      return;
    }

    if (isCalendarPlanning || isCalendarSaving || isAutoSavingRef.current) {
      return;
    }

    const editorSignature = buildEditorSignature({
      title: proposalTitle,
      startAt: proposalStartAtInput,
      endAt: proposalEndAtInput,
      attendeesCsv: proposalAttendeesInput,
      notes: proposalNotes,
    });
    if (editorSignature === lastSyncedSignatureRef.current) {
      return;
    }

    autoSaveTimerRef.current = window.setTimeout(() => {
      autoSaveTimerRef.current = null;

      void (async () => {
        try {
          const startAtIso = new Date(proposalStartAtInput).toISOString();
          const endAtIso = new Date(proposalEndAtInput).toISOString();
          if (new Date(endAtIso).getTime() < new Date(startAtIso).getTime()) {
            return;
          }

          isAutoSavingRef.current = true;
          const updated = await updateCalendarProposal(proposal.id, {
            title: proposalTitle,
            start_at: startAtIso,
            end_at: endAtIso,
            attendees: parseAttendeesCsv(proposalAttendeesInput),
            notes: proposalNotes || null,
          });
          setActiveCalendarProposal(updated);
          syncEditorFromProposal(updated);
          setCalendarError(null);
        } catch (error) {
          logger.error("Failed to auto-save calendar proposal.", error, {
            proposalId: proposal.id,
            titleLength: proposalTitle.trim().length,
            attendeeCount: parseAttendeesCsv(proposalAttendeesInput).length,
          });
        } finally {
          isAutoSavingRef.current = false;
        }
      })();
    }, 450);

    return () => {
      if (autoSaveTimerRef.current !== null) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, [
    activeCalendarProposal,
    isCalendarPlanning,
    isCalendarSaving,
    proposalAttendeesInput,
    proposalEndAtInput,
    proposalNotes,
    proposalStartAtInput,
    proposalTitle,
    syncEditorFromProposal,
  ]);

  const planFromInputs = useCallback(async (action: CalendarPlanningRequest["action"]) => {
    const desiredStartAt = proposalStartAtInput.trim();
    if (!desiredStartAt) {
      setCalendarError("Start time is required to plan a calendar proposal.");
      return false;
    }

    setIsCalendarPlanning(true);
    setCalendarError(null);
    try {
      const desiredStartIso = new Date(desiredStartAt).toISOString();
      const desiredEndIso = proposalEndAtInput.trim()
        ? new Date(proposalEndAtInput.trim()).toISOString()
        : undefined;

      if (desiredEndIso && new Date(desiredEndIso).getTime() < new Date(desiredStartIso).getTime()) {
        setCalendarError("End date and time cannot be before start date and time.");
        return false;
      }

      const result = await planCalendarProposal({
        action,
        title: proposalTitle,
        desired_start_at: desiredStartIso,
        desired_end_at: desiredEndIso,
        timezone_name: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        attendees: parseAttendeesCsv(proposalAttendeesInput),
        notes: proposalNotes || null,
      });
      setActiveCalendarProposal(result.proposal);
      activeProposalIdRef.current = result.proposal.id;
      syncEditorFromProposal(result.proposal);
      return true;
    } catch (error) {
      logger.error("Failed to plan calendar proposal.", error, {
        action,
        desiredStartAt,
        hasEndAt: proposalEndAtInput.trim().length > 0,
      });
      setCalendarError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setIsCalendarPlanning(false);
    }
  }, [proposalAttendeesInput, proposalEndAtInput, proposalNotes, proposalStartAtInput, proposalTitle, syncEditorFromProposal]);

  const saveCalendarProposalEdits = useCallback(async () => {
    const proposal = activeCalendarProposal;
    if (!proposal) {
      return false;
    }

    setIsCalendarSaving(true);
    setCalendarError(null);
    try {
      const startAtIso = new Date(proposalStartAtInput).toISOString();
      const endAtIso = new Date(proposalEndAtInput).toISOString();
      if (new Date(endAtIso).getTime() < new Date(startAtIso).getTime()) {
        setCalendarError("End date and time cannot be before start date and time.");
        return false;
      }

      const updated = await updateCalendarProposal(proposal.id, {
        title: proposalTitle,
        start_at: startAtIso,
        end_at: endAtIso,
        attendees: parseAttendeesCsv(proposalAttendeesInput),
        notes: proposalNotes || null,
      });
      setActiveCalendarProposal(updated);
      syncEditorFromProposal(updated);
      return true;
    } catch (error) {
      logger.error("Failed to update calendar proposal.", error, {
        proposalId: proposal.id,
      });
      setCalendarError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setIsCalendarSaving(false);
    }
  }, [activeCalendarProposal, proposalAttendeesInput, proposalEndAtInput, proposalNotes, proposalStartAtInput, proposalTitle, syncEditorFromProposal]);

  const approveActiveCalendarProposal = useCallback(async () => {
    const proposal = activeCalendarProposal;
    if (!proposal) {
      return false;
    }

    setIsCalendarSaving(true);
    setCalendarError(null);
    try {
      const approved = await approveCalendarProposal(proposal.id);
      setActiveCalendarProposal(approved);
      syncEditorFromProposal(approved);
      return true;
    } catch (error) {
      logger.error("Failed to approve calendar proposal.", error, {
        proposalId: proposal.id,
      });
      setCalendarError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setIsCalendarSaving(false);
    }
  }, [activeCalendarProposal, syncEditorFromProposal]);

  const rejectActiveCalendarProposal = useCallback(async () => {
    const proposal = activeCalendarProposal;
    if (!proposal) {
      return false;
    }

    setIsCalendarSaving(true);
    setCalendarError(null);
    try {
      const rejected = await rejectCalendarProposal(proposal.id, "Rejected from UI");
      setActiveCalendarProposal(rejected);
      syncEditorFromProposal(rejected);
      return true;
    } catch (error) {
      logger.error("Failed to reject calendar proposal.", error, {
        proposalId: proposal.id,
      });
      setCalendarError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setIsCalendarSaving(false);
    }
  }, [activeCalendarProposal, syncEditorFromProposal]);

  const cancelActiveCalendarProposal = useCallback(async () => {
    const proposal = activeCalendarProposal;
    if (!proposal) {
      return false;
    }

    setIsCalendarSaving(true);
    setCalendarError(null);
    try {
      const canceled = await cancelCalendarProposal(proposal.id);
      setActiveCalendarProposal(canceled);
      syncEditorFromProposal(canceled);
      return true;
    } catch (error) {
      logger.error("Failed to cancel calendar proposal.", error, {
        proposalId: proposal.id,
      });
      setCalendarError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setIsCalendarSaving(false);
    }
  }, [activeCalendarProposal, syncEditorFromProposal]);

  return {
    activeCalendarProposal,
    isCalendarPlanning,
    isCalendarSaving,
    calendarError,
    proposalTitle,
    proposalStartAtInput,
    proposalEndAtInput,
    proposalAttendeesInput,
    proposalNotes,
    setProposalTitle,
    setProposalStartAtInput,
    setProposalEndAtInput,
    setProposalAttendeesInput,
    setProposalNotes,
    refreshCalendarProposal,
    planFromInputs,
    saveCalendarProposalEdits,
    approveActiveCalendarProposal,
    rejectActiveCalendarProposal,
    cancelActiveCalendarProposal,
  };
}
