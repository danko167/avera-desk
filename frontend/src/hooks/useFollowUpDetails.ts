import { useEffect, useState } from "react";
import { fetchFollowUpById, type FollowUpItem, type ParsedFollowUpNotification } from "../lib/api";
import { createLogger } from "../lib/logger";

type UseFollowUpDetailsResult = {
  activeFollowUp: FollowUpItem | null;
};

const logger = createLogger("useFollowUpDetails");

export function useFollowUpDetails(
  parsedActiveFollowUp: ParsedFollowUpNotification | null
): UseFollowUpDetailsResult {
  const [activeFollowUp, setActiveFollowUp] = useState<FollowUpItem | null>(null);

  useEffect(() => {
    if (!parsedActiveFollowUp) {
      setActiveFollowUp(null);
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const followUp = await fetchFollowUpById(parsedActiveFollowUp.followUpId);
        if (!cancelled) {
          setActiveFollowUp(followUp);
        }
      } catch (error) {
        logger.error("Failed to fetch follow-up details.", error);
        if (!cancelled) {
          setActiveFollowUp(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [parsedActiveFollowUp]);

  return {
    activeFollowUp,
  };
}
