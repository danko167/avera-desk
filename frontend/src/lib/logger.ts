type LogLevel = "debug" | "info" | "warn" | "error";

const LOG_LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

const DEFAULT_LOG_LEVEL: LogLevel = import.meta.env.DEV ? "debug" : "warn";

function parseLogLevel(value: unknown): LogLevel | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.toLowerCase();
  if (normalized === "debug" || normalized === "info" || normalized === "warn" || normalized === "error") {
    return normalized;
  }

  return null;
}

function resolveConfiguredLevel(): LogLevel {
  const envLevel = parseLogLevel(import.meta.env.VITE_LOG_LEVEL);
  if (envLevel) {
    return envLevel;
  }

  try {
    const storageLevel = parseLogLevel(window.localStorage.getItem("avera:log-level"));
    if (storageLevel) {
      return storageLevel;
    }
  } catch {
    // Ignore storage errors and keep default log behavior.
  }

  return DEFAULT_LOG_LEVEL;
}

function shouldLog(level: LogLevel): boolean {
  const configuredLevel = resolveConfiguredLevel();
  return LOG_LEVEL_PRIORITY[level] >= LOG_LEVEL_PRIORITY[configuredLevel];
}

function formatPrefix(level: LogLevel, scope: string): string {
  return `[${level.toUpperCase()}][${scope}]`;
}

function writeLog(level: LogLevel, scope: string, message: string, details: unknown[]): void {
  if (!shouldLog(level)) {
    return;
  }

  const prefixedMessage = `${formatPrefix(level, scope)} ${message}`;
  if (level === "error") {
    console.error(prefixedMessage, ...details);
    return;
  }
  if (level === "warn") {
    console.warn(prefixedMessage, ...details);
    return;
  }
  if (level === "info") {
    console.info(prefixedMessage, ...details);
    return;
  }

  console.debug(prefixedMessage, ...details);
}

export function createLogger(scope: string) {
  return {
    debug: (message: string, ...details: unknown[]) => {
      writeLog("debug", scope, message, details);
    },
    info: (message: string, ...details: unknown[]) => {
      writeLog("info", scope, message, details);
    },
    warn: (message: string, ...details: unknown[]) => {
      writeLog("warn", scope, message, details);
    },
    error: (message: string, ...details: unknown[]) => {
      writeLog("error", scope, message, details);
    },
  };
}