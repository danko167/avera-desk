import { invoke } from "@tauri-apps/api/core";
import { API_ENDPOINTS, WS_ENDPOINTS } from "../endpoints";
import type { ConnectionSettings } from "./types";

let runtimeConnectionSettings: ConnectionSettings = {
  app_api_base_url: "",
  app_ws_url: "",
};
const LOCAL_AUTH_HEADER = "X-Avera-Local-Token";
const LOCAL_AUTH_TOKEN_STORAGE_KEY = "avera_local_auth_token";

let localAuthToken: string | null = null;
let localAuthTokenPromise: Promise<string> | null = null;
let localWsTicket: string | null = null;
let localWsTicketPromise: Promise<string> | null = null;
let apiFetchSequence = 0;

const BOOTSTRAP_TRACE_PATHS = new Set<string>([
  API_ENDPOINTS.localAuthToken,
  API_ENDPOINTS.settings,
]);

function shouldTraceBootstrapPath(path: string): boolean {
  if (BOOTSTRAP_TRACE_PATHS.has(path)) {
    return true;
  }
  if (path.startsWith(`${API_ENDPOINTS.settings}?`)) {
    return true;
  }
  return false;
}

async function logStartupNetworkDiagnostic(message: string): Promise<void> {
  const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  if (!isTauri) {
    return;
  }

  try {
    await invoke("log_startup_diagnostic", { message: `network ${message}` });
  } catch {
    // Keep fetch path robust even if diagnostics channel fails.
  }
}

function readLocalAuthTokenFromStorage(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const token = (window.localStorage.getItem(LOCAL_AUTH_TOKEN_STORAGE_KEY) ?? "").trim();
    return token.length > 0 ? token : null;
  } catch {
    return null;
  }
}

function writeLocalAuthTokenToStorage(token: string | null): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    if ((token ?? "").trim().length > 0) {
      window.localStorage.setItem(LOCAL_AUTH_TOKEN_STORAGE_KEY, token as string);
    } else {
      window.localStorage.removeItem(LOCAL_AUTH_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Ignore storage failures; in-memory token still works for current window.
  }
}

function clearLocalAuthToken(): void {
  localAuthToken = null;
  writeLocalAuthTokenToStorage(null);
}

function normalizeConfiguredUrl(value: string | null | undefined): string {
  return (value ?? "").trim().replace(/\/+$/, "");
}

function isPackagedTauriHost(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return normalized === "tauri.localhost" || normalized === "app.localhost";
}

function isHttpLikeProtocol(protocol: string): boolean {
  return protocol === "http:" || protocol === "https:";
}

function getBootstrapApiBaseUrl(): string {
  const configured = normalizeConfiguredUrl(import.meta.env.VITE_API_URL ?? "");
  if (configured.length > 0) {
    return configured;
  }

  if (typeof window === "undefined" || window.location.protocol === "file:") {
    return "http://127.0.0.1:8000";
  }

  // Tauri app windows can run under custom schemes in dev/prod.
  if (!isHttpLikeProtocol(window.location.protocol)) {
    return "http://127.0.0.1:8000";
  }

  // In Tauri dev, the frontend runs on Vite :1420 while API is on :8000.
  if (window.location.hostname === "localhost" && window.location.port === "1420") {
    return "http://127.0.0.1:8000";
  }

  if (window.location.hostname === "127.0.0.1" && window.location.port === "1420") {
    return "http://127.0.0.1:8000";
  }

  if (isPackagedTauriHost(window.location.hostname)) {
    return "http://127.0.0.1:8000";
  }

  return window.location.origin;
}

function getBootstrapWebSocketUrl(): string {
  const configured = (import.meta.env.VITE_WS_URL ?? "").trim();
  if (configured.length > 0) {
    return configured;
  }

  if (typeof window === "undefined" || window.location.protocol === "file:") {
    return `ws://127.0.0.1:8000${WS_ENDPOINTS.websocket}`;
  }

  if (!isHttpLikeProtocol(window.location.protocol)) {
    return `ws://127.0.0.1:8000${WS_ENDPOINTS.websocket}`;
  }

  if (isPackagedTauriHost(window.location.hostname)) {
    return `ws://127.0.0.1:8000${WS_ENDPOINTS.websocket}`;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${WS_ENDPOINTS.websocket}`;
}

export function applyRuntimeConnectionSettings(settings: Partial<ConnectionSettings> | null | undefined): void {
  runtimeConnectionSettings = {
    app_api_base_url: normalizeConfiguredUrl(settings?.app_api_base_url),
    app_ws_url: (settings?.app_ws_url ?? "").trim(),
  };
}

export async function getWebSocketUrl(
  settings?: Partial<ConnectionSettings> | null,
  options?: { refreshWsTicket?: boolean },
): Promise<string> {
  const configuredWsUrl = (settings?.app_ws_url ?? runtimeConnectionSettings.app_ws_url).trim();
  const baseUrl = configuredWsUrl.length > 0 ? configuredWsUrl : getBootstrapWebSocketUrl();
  const wsTicket = await ensureLocalWsTicket(Boolean(options?.refreshWsTicket));

  return withWsTicketInUrl(baseUrl, wsTicket);
}

export function getApiUrl(path = ""): string {
  const configuredApiBaseUrl = normalizeConfiguredUrl(runtimeConnectionSettings.app_api_base_url);
  const baseUrl = configuredApiBaseUrl.length > 0 ? configuredApiBaseUrl : getBootstrapApiBaseUrl();
  return `${baseUrl}${path}`;
}

function formatUnknownError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

function withWsTicketInUrl(url: string, wsTicket: string): string {
  if (!wsTicket) {
    return url;
  }

  try {
    const parsed = new URL(url);
    parsed.searchParams.delete("token");
    parsed.searchParams.set("ws_ticket", wsTicket);
    return parsed.toString();
  } catch {
    return url;
  }
}

function createJsonHeaders(initHeaders?: HeadersInit, token?: string | null): Headers {
  const headers = new Headers(initHeaders);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const normalizedToken = (token ?? "").trim();
  if (normalizedToken.length > 0) {
    headers.set(LOCAL_AUTH_HEADER, normalizedToken);
  }
  return headers;
}

async function fetchLocalAuthToken(): Promise<string> {
  const response = await fetch(getApiUrl(API_ENDPOINTS.localAuthToken), {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Failed to obtain local auth token (${response.status})`);
  }

  const data = await response.json() as { token?: string };
  const token = (data?.token ?? "").trim();
  if (!token) {
    throw new Error("Backend local auth token response is missing token.");
  }
  localAuthToken = token;
  writeLocalAuthTokenToStorage(token);
  return token;
}

export async function ensureLocalAuthToken(): Promise<string> {
  if (!localAuthToken) {
    localAuthToken = readLocalAuthTokenFromStorage();
  }

  if (localAuthToken) {
    return localAuthToken;
  }

  if (!localAuthTokenPromise) {
    localAuthTokenPromise = fetchLocalAuthToken().finally(() => {
      localAuthTokenPromise = null;
    });
  }

  return localAuthTokenPromise;
}

async function fetchLocalWsTicket(): Promise<string> {
  const response = await apiFetch(API_ENDPOINTS.localAuthWsTicket, "WebSocket auth ticket", {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Failed to obtain WebSocket auth ticket (${response.status})`);
  }

  const data = await response.json() as { ticket?: string };
  const ticket = (data?.ticket ?? "").trim();
  if (!ticket) {
    throw new Error("Backend ws-ticket response is missing ticket.");
  }

  localWsTicket = ticket;
  return ticket;
}

export async function ensureLocalWsTicket(forceRefresh = false): Promise<string> {
  if (forceRefresh) {
    localWsTicket = null;
  }

  if (localWsTicket) {
    return localWsTicket;
  }

  if (!localWsTicketPromise) {
    localWsTicketPromise = fetchLocalWsTicket().finally(() => {
      localWsTicketPromise = null;
    });
  }

  return localWsTicketPromise;
}

type ApiFetchOptions = RequestInit & {
  timeoutMs?: number;
  skipLocalAuth?: boolean;
};

export type RequestJsonOptions = RequestInit & {
  timeoutMs?: number;
};

export async function apiFetch(path: string, label: string, init?: ApiFetchOptions): Promise<Response> {
  const requestId = ++apiFetchSequence;
  const url = getApiUrl(path);
  const timeoutMs = init?.timeoutMs;
  const skipLocalAuth = Boolean(init?.skipLocalAuth);
  const trace = shouldTraceBootstrapPath(path);
  const requestInit: RequestInit = { ...(init ?? {}) };
  delete (requestInit as { timeoutMs?: number; skipLocalAuth?: boolean }).timeoutMs;
  delete (requestInit as { timeoutMs?: number; skipLocalAuth?: boolean }).skipLocalAuth;

  const token = skipLocalAuth ? null : await ensureLocalAuthToken();
  const headers = createJsonHeaders(requestInit.headers, token);
  const method = (requestInit.method ?? "GET").toString().toUpperCase();

  if (trace) {
    await logStartupNetworkDiagnostic(
      `request_start id=${requestId} label=${label} method=${method} path=${path} url=${url} timeout_ms=${timeoutMs ?? 0} skip_local_auth=${skipLocalAuth} has_local_token=${Boolean((token ?? "").trim())}`
    );
  }

  const abortController = new AbortController();
  const timeoutId = typeof timeoutMs === "number" && timeoutMs > 0
    ? window.setTimeout(() => {
      abortController.abort();
    }, timeoutMs)
    : null;

  try {
    let response = await fetch(url, {
      ...requestInit,
      headers,
      signal: abortController.signal,
    });

    if (trace) {
      await logStartupNetworkDiagnostic(
        `request_response id=${requestId} label=${label} method=${method} path=${path} status=${response.status} ok=${response.ok}`
      );
    }

    if (!skipLocalAuth && response.status === 401) {
      // Token can go stale when renderer windows restart while backend process keeps running.
      // Clear cache and try one fresh bootstrap token fetch.
      clearLocalAuthToken();

      try {
        const refreshedToken = await ensureLocalAuthToken();
        const retryHeaders = createJsonHeaders(requestInit.headers, refreshedToken);
        response = await fetch(url, {
          ...requestInit,
          headers: retryHeaders,
          signal: abortController.signal,
        });
        if (trace) {
          await logStartupNetworkDiagnostic(
            `request_retry_after_401 id=${requestId} label=${label} method=${method} path=${path} status=${response.status} ok=${response.ok}`
          );
        }
      } catch {
        if (trace) {
          await logStartupNetworkDiagnostic(
            `request_retry_after_401_failed id=${requestId} label=${label} method=${method} path=${path}`
          );
        }
        // Keep the original 401 response behavior if refresh fails.
      }
    }

    return response;
  } catch (error) {
    if (trace) {
      const errorName = error instanceof Error ? error.name : "unknown";
      await logStartupNetworkDiagnostic(
        `request_exception id=${requestId} label=${label} method=${method} path=${path} error_name=${errorName} online=${typeof navigator !== "undefined" ? navigator.onLine : false} detail=${formatUnknownError(error)}`
      );
    }

    // In desktop dev, auth rejection can surface as a network-style failure
    // before status code is observable by fetch. Try one forced token refresh.
    if (!skipLocalAuth) {
      clearLocalAuthToken();
      try {
        const refreshedToken = await ensureLocalAuthToken();
        const retryHeaders = createJsonHeaders(requestInit.headers, refreshedToken);
        const retryResponse = await fetch(url, {
          ...requestInit,
          headers: retryHeaders,
          signal: abortController.signal,
        });
        if (trace) {
          await logStartupNetworkDiagnostic(
            `request_retry_after_network_error id=${requestId} label=${label} method=${method} path=${path} status=${retryResponse.status} ok=${retryResponse.ok}`
          );
        }
        return retryResponse;
      } catch (retryError) {
        if (trace) {
          await logStartupNetworkDiagnostic(
            `request_retry_after_network_error_failed id=${requestId} label=${label} method=${method} path=${path} detail=${formatUnknownError(retryError)}`
          );
        }
      }
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`${label} request timed out for ${url} after ${timeoutMs}ms`);
    }
    throw new Error(`${label} request failed for ${url}: ${formatUnknownError(error)}`);
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  }
}

export async function requestJson<T>(path: string, label: string, init?: RequestJsonOptions): Promise<T> {
  const response = await apiFetch(path, label, init);

  if (!response.ok) {
    const url = getApiUrl(path);
    const body = (await response.text()).trim();
    const bodySuffix = body.length > 0 ? `: ${body.slice(0, 240)}` : "";
    throw new Error(
      `${label} request failed for ${url} (${response.status} ${response.statusText})${bodySuffix}`
    );
  }

  try {
    return await response.json() as T;
  } catch (error) {
    const url = getApiUrl(path);
    throw new Error(`${label} returned invalid JSON from ${url}: ${formatUnknownError(error)}`);
  }
}
