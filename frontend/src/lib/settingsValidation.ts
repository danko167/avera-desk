type ValidationOptions = {
  required?: boolean;
};

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TENANT_ALIAS_VALUES = new Set(["common", "organizations", "consumers"]);
const TENANT_DOMAIN_REGEX = /^[a-z0-9][a-z0-9.-]*[a-z0-9]$/i;

export function validateClientId(value: string, options?: ValidationOptions): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return options?.required ? "Client ID is required." : undefined;
  }

  return UUID_REGEX.test(trimmed)
    ? undefined
    : "Must be a valid UUID (e.g., xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).";
}

export function validateTenantId(value: string, options?: ValidationOptions): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return options?.required ? "Tenant ID is required." : undefined;
  }
  const normalized = trimmed.toLowerCase();
  if (TENANT_ALIAS_VALUES.has(normalized)) {
    return undefined;
  }

  if (trimmed.includes("/") || trimmed.includes(" ") || trimmed.includes("?") || trimmed.includes("#")) {
    return "Tenant value cannot contain spaces, '/', '?', or '#'.";
  }

  if (TENANT_DOMAIN_REGEX.test(trimmed)) {
    return undefined;
  }

  return UUID_REGEX.test(trimmed)
    ? undefined
    : "Use a tenant UUID, tenant domain, or one of: common, organizations, consumers.";
}

export function validateRedirectUrl(value: string, options?: ValidationOptions): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return options?.required ? "Redirect URL is required." : undefined;
  }

  try {
    new URL(trimmed);
    return undefined;
  } catch {
    return "Must be a valid URL.";
  }
}

export function validateGmailClientSecret(value: string, options?: ValidationOptions): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return options?.required ? "Gmail client secret is required." : undefined;
  }

  return trimmed.length >= 10 ? undefined : "Looks too short for a client secret.";
}

export function validateApiBaseUrl(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "Use an http:// or https:// URL.";
    }
    return undefined;
  } catch {
    return "Enter a valid http:// or https:// URL.";
  }
}

export function validateWebSocketUrl(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "ws:" && parsed.protocol !== "wss:") {
      return "Use a ws:// or wss:// URL.";
    }
    return undefined;
  } catch {
    return "Enter a valid ws:// or wss:// URL.";
  }
}

export function getApiBaseUrlPolicyHint(value: string): string | undefined {
  if (!value.trim()) {
    return undefined;
  }

  return "Backend validates security policy (for example https:// requirements for non-local hosts) when you save.";
}

export function getWebSocketUrlPolicyHint(value: string): string | undefined {
  if (!value.trim()) {
    return undefined;
  }

  return "Backend validates WebSocket security policy (for example wss:// requirements for non-local hosts) when you save.";
}