import React from "react";
import ReactDOM from "react-dom/client";
import { MantineProvider, createTheme } from "@mantine/core";
import { invoke } from "@tauri-apps/api/core";
import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@danko167/narrative-loader/styles.css";
import "./styles/narrative-loader-overrides.css";
import App from "./App.tsx";
import { createLogger } from "./lib/logger";

const logger = createLogger("main");

const tauriWindowLabel = (window as Window & { __AVERA_WINDOW_LABEL?: string }).__AVERA_WINDOW_LABEL;
const earlyBootMessage = `[main.tsx] href=${window.location.href} injectedLabel=${tauriWindowLabel ?? "none"}`;
logger.info("Renderer boot diagnostics.", { message: earlyBootMessage });

if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
  void invoke("log_startup_diagnostic", { message: earlyBootMessage }).catch(() => {
    // keep renderer boot resilient even if diagnostics command fails
  });
}

const isTauriRuntime = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const theme = createTheme({
  primaryColor: "orange",
  defaultRadius: "md",
  fontFamily: "'Outfit', 'Segoe UI', sans-serif",
  headings: {
    fontFamily: "'Sora', 'Segoe UI', sans-serif",
  },
  components: {
    Tooltip: {
      defaultProps: {
        withArrow: true,
        openDelay: 140,
        closeDelay: 40,
        position: "bottom",
        offset: 6,
        multiline: true,
      },
      styles: {
        tooltip: {
          fontSize: "11px",
          lineHeight: 1.3,
          maxWidth: 260,
        },
      },
    },
  },
});

const appTree = (
  <MantineProvider theme={theme} defaultColorScheme="light">
    <App />
  </MantineProvider>
);

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  isTauriRuntime ? appTree : <React.StrictMode>{appTree}</React.StrictMode>,
);
