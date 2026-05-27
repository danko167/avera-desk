import {
  IconAlertTriangle,
  IconCircleCheck,
  IconInfoCircle,
  IconMoodAnnoyed,
} from "@tabler/icons-react";
import type { Notification } from "./api";

export type SeverityPalette = {
  badge: string;
  highlight: string;
  panelBg: string;
  panelBorder: string;
  icon: React.ComponentType<{ size?: number; color?: string }>;
  label: string;
};

export function getSeverityPalette(type: Notification["type"]): SeverityPalette {
  switch (type) {
    case "error":
      return {
        badge: "red",
        highlight: "rgba(239, 68, 68, 0.95)",
        panelBg:
          "radial-gradient(circle at 18% 12%, rgba(255, 221, 210, 0.85) 0%, rgba(255, 240, 232, 0.96) 62%, rgba(255, 255, 255, 1) 100%)",
        panelBorder: "rgba(239, 68, 68, 0.28)",
        icon: IconMoodAnnoyed,
        label: "Critical attention",
      };
    case "warning":
      return {
        badge: "orange",
        highlight: "rgba(234, 88, 12, 0.95)",
        panelBg:
          "radial-gradient(circle at 20% 14%, rgba(255, 234, 208, 0.82) 0%, rgba(255, 246, 235, 0.96) 62%, rgba(255, 255, 255, 1) 100%)",
        panelBorder: "rgba(234, 88, 12, 0.24)",
        icon: IconAlertTriangle,
        label: "Heads-up",
      };
    case "success":
      return {
        badge: "orange",
        highlight: "rgba(249, 115, 22, 0.95)",
        panelBg:
          "radial-gradient(circle at 22% 14%, rgba(255, 238, 214, 0.84) 0%, rgba(255, 248, 239, 0.96) 62%, rgba(255, 255, 255, 1) 100%)",
        panelBorder: "rgba(249, 115, 22, 0.2)",
        icon: IconCircleCheck,
        label: "Resolved signal",
      };
    case "info":
    default:
      return {
        badge: "orange",
        highlight: "rgba(249, 115, 22, 0.95)",
        panelBg:
          "radial-gradient(circle at 20% 12%, rgba(255, 231, 204, 0.84) 0%, rgba(255, 244, 232, 0.95) 58%, rgba(255, 255, 255, 1) 100%)",
        panelBorder: "rgba(249, 115, 22, 0.22)",
        icon: IconInfoCircle,
        label: "Agent update",
      };
  }
}
