import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelEmailDraft,
  fetchEmailDraftById,
  sendEmailDraft,
  updateEmailDraft,
  type EmailDraft,
  type ParsedDraftNotification,
} from "../lib/api";
import { createLogger } from "../lib/logger";

type DraftSyncState = "idle" | "saving" | "saved" | "error";

type UseDraftManagerParams = {
  parsedActiveDraft: ParsedDraftNotification | null;
};

const logger = createLogger("useDraftManager");

export function useDraftManager({
  parsedActiveDraft,
}: UseDraftManagerParams) {
  const [activeDraft, setActiveDraft] = useState<EmailDraft | null>(null);
  const [draftRecipient, setDraftRecipient] = useState("");
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [isDraftSaving, setIsDraftSaving] = useState(false);
  const [isDraftDirty, setIsDraftDirty] = useState(false);
  const [draftSyncState, setDraftSyncState] = useState<DraftSyncState>("idle");
  const [draftActionError, setDraftActionError] = useState<string | null>(null);

  const draftAutoSaveTimerRef = useRef<number | null>(null);
  const draftSavedBadgeTimerRef = useRef<number | null>(null);
  const draftDirtyRef = useRef(false);

  useEffect(() => {
    draftDirtyRef.current = isDraftDirty;
  }, [isDraftDirty]);

  const refreshActiveDraft = useCallback(async (draftId: string) => {
    try {
      const draft = await fetchEmailDraftById(draftId);
      setActiveDraft(draft);
      if (!draftDirtyRef.current) {
        setDraftRecipient(draft.recipient_email ?? "");
        setDraftSubject(draft.subject ?? "");
        setDraftBody(draft.body ?? "");
      }
    } catch (error) {
      logger.error("Failed to refresh active draft.", error, {
        draftId,
      });
    }
  }, []);

  useEffect(() => {
    if (!parsedActiveDraft) {
      setActiveDraft(null);
      setDraftRecipient("");
      setDraftSubject("");
      setDraftBody("");
      setIsDraftDirty(false);
      setDraftSyncState("idle");
      setDraftActionError(null);
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const draft = await fetchEmailDraftById(parsedActiveDraft.draftId);
        if (!cancelled) {
          setActiveDraft(draft);
          setDraftRecipient(draft.recipient_email ?? "");
          setDraftSubject(draft.subject ?? "");
          setDraftBody(draft.body ?? "");
          setIsDraftDirty(false);
          setDraftSyncState("idle");
          setDraftActionError(null);
        }
      } catch (error) {
        logger.error("Failed to fetch draft details.", error, {
          draftId: parsedActiveDraft.draftId,
        });
        if (!cancelled) {
          setActiveDraft(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [parsedActiveDraft]);

  useEffect(() => {
    if (!activeDraft || activeDraft.status !== "pending" || !isDraftDirty) {
      if (draftAutoSaveTimerRef.current !== null) {
        window.clearTimeout(draftAutoSaveTimerRef.current);
        draftAutoSaveTimerRef.current = null;
      }
      return;
    }

    const draftId = activeDraft.id;
    draftAutoSaveTimerRef.current = window.setTimeout(() => {
      void (async () => {
        try {
          setDraftSyncState("saving");
          const updated = await updateEmailDraft(draftId, {
            recipient_email: draftRecipient.trim() || null,
            subject: draftSubject,
            body: draftBody,
          });
          if (activeDraft?.id === draftId) {
            setActiveDraft(updated);
          }
          setIsDraftDirty(false);
          setDraftSyncState("saved");
          if (draftSavedBadgeTimerRef.current !== null) {
            window.clearTimeout(draftSavedBadgeTimerRef.current);
          }
          draftSavedBadgeTimerRef.current = window.setTimeout(() => {
            setDraftSyncState("idle");
            draftSavedBadgeTimerRef.current = null;
          }, 1800);
        } catch (error) {
          logger.error("Failed to autosave draft.", error, {
            draftId,
            recipientLength: draftRecipient.trim().length,
            subjectLength: draftSubject.length,
            bodyLength: draftBody.length,
          });
          setDraftSyncState("error");
        }
      })();
    }, 450);

    return () => {
      if (draftAutoSaveTimerRef.current !== null) {
        window.clearTimeout(draftAutoSaveTimerRef.current);
        draftAutoSaveTimerRef.current = null;
      }
    };
  }, [activeDraft, draftBody, draftRecipient, draftSubject, isDraftDirty]);

  useEffect(() => {
    return () => {
      if (draftAutoSaveTimerRef.current !== null) {
        window.clearTimeout(draftAutoSaveTimerRef.current);
      }
      if (draftSavedBadgeTimerRef.current !== null) {
        window.clearTimeout(draftSavedBadgeTimerRef.current);
      }
    };
  }, []);

  const handleDraftSave = useCallback(async () => {
    if (!activeDraft || activeDraft.status !== "pending") {
      return;
    }
    setIsDraftSaving(true);
    setDraftActionError(null);
    try {
      const updated = await updateEmailDraft(activeDraft.id, {
        recipient_email: draftRecipient.trim() || null,
        subject: draftSubject,
        body: draftBody,
      });
      setActiveDraft(updated);
      setDraftRecipient(updated.recipient_email ?? "");
      setDraftSubject(updated.subject ?? "");
      setDraftBody(updated.body ?? "");
      setIsDraftDirty(false);
      setDraftSyncState("saved");
    } catch (error) {
      logger.error("Failed to save draft.", error, {
        draftId: activeDraft.id,
      });
      setDraftSyncState("error");
      setDraftActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsDraftSaving(false);
    }
  }, [activeDraft, draftBody, draftRecipient, draftSubject]);

  const handleDraftSend = useCallback(async (): Promise<boolean> => {
    if (!activeDraft || activeDraft.status !== "pending") {
      return false;
    }
    setIsDraftSaving(true);
    setDraftActionError(null);
    try {
      await updateEmailDraft(activeDraft.id, {
        recipient_email: draftRecipient.trim() || null,
        subject: draftSubject,
        body: draftBody,
      });
      const sent = await sendEmailDraft(activeDraft.id);
      setActiveDraft(sent);
      setIsDraftDirty(false);
      return true;
    } catch (error) {
      logger.error("Failed to send draft.", error, {
        draftId: activeDraft.id,
      });
      setDraftActionError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setIsDraftSaving(false);
    }
  }, [activeDraft, draftBody, draftRecipient, draftSubject]);

  const handleDraftCancel = useCallback(async (): Promise<boolean> => {
    if (!activeDraft || activeDraft.status !== "pending") {
      return false;
    }
    setIsDraftSaving(true);
    setDraftActionError(null);
    try {
      const canceled = await cancelEmailDraft(activeDraft.id);
      setActiveDraft(canceled);
      setIsDraftDirty(false);
      return true;
    } catch (error) {
      logger.error("Failed to cancel draft.", error, {
        draftId: activeDraft.id,
      });
      setDraftActionError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setIsDraftSaving(false);
    }
  }, [activeDraft]);

  const setDraftRecipientDirty = useCallback((value: string) => {
    setDraftRecipient(value);
    setIsDraftDirty(true);
    setDraftSyncState("idle");
    setDraftActionError(null);
  }, []);

  const setDraftSubjectDirty = useCallback((value: string) => {
    setDraftSubject(value);
    setIsDraftDirty(true);
    setDraftSyncState("idle");
    setDraftActionError(null);
  }, []);

  const setDraftBodyDirty = useCallback((value: string) => {
    setDraftBody(value);
    setIsDraftDirty(true);
    setDraftSyncState("idle");
    setDraftActionError(null);
  }, []);

  const draftSyncHint =
    draftSyncState === "saving"
      ? "Saving..."
      : draftSyncState === "saved"
        ? "Autosaved"
        : draftSyncState === "error"
          ? "Autosave failed"
          : null;

  return {
    activeDraft,
    draftRecipient,
    draftSubject,
    draftBody,
    isDraftSaving,
    draftSyncState,
    draftSyncHint,
    draftActionError,
    refreshActiveDraft,
    handleDraftSave,
    handleDraftSend,
    handleDraftCancel,
    setDraftRecipientDirty,
    setDraftSubjectDirty,
    setDraftBodyDirty,
  };
}
