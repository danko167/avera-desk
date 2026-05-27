import { useCallback, useEffect, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { createLogger } from "../lib/logger";

const isTauriRuntime = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const logger = createLogger("useWindowManager");

export function useWindowManager() {
  const [isAlwaysOnTop, setIsAlwaysOnTop] = useState(false);

  useEffect(() => {
    const syncAlwaysOnTop = async () => {
      if (!isTauriRuntime()) return;

      try {
        const value = await getCurrentWindow().isAlwaysOnTop();
        setIsAlwaysOnTop(value);
      } catch (error) {
        logger.error("Failed to read always-on-top state.", error);
      }
    };

    void syncAlwaysOnTop();
  }, []);

  const hideWindow = useCallback(async () => {
    if (!isTauriRuntime()) return;
    await getCurrentWindow().hide();
  }, []);

  const toggleAlwaysOnTop = useCallback(async () => {
    if (!isTauriRuntime()) return;

    try {
      const nextValue = !isAlwaysOnTop;
      await getCurrentWindow().setAlwaysOnTop(nextValue);
      setIsAlwaysOnTop(nextValue);
    } catch (error) {
      logger.error("Failed to toggle always-on-top.", error);
    }
  }, [isAlwaysOnTop]);

  const startDragging = useCallback(async (event: React.MouseEvent<HTMLElement>) => {
    if (!isTauriRuntime()) return;

    const target = event.target as HTMLElement;
    if (target.closest("button")) {
      return;
    }

    await getCurrentWindow().startDragging();
  }, []);

  return {
    isAlwaysOnTop,
    hideWindow,
    toggleAlwaysOnTop,
    startDragging,
  };
}
