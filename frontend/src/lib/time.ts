const TIMEZONE_SUFFIX = /([zZ]|[+\-]\d{2}:\d{2})$/;

function normalizeTimestamp(raw: string): string {
  const value = raw.trim();
  if (!value) {
    return value;
  }
  // Backend can emit naive timestamps from SQLite; treat them as UTC.
  return TIMEZONE_SUFFIX.test(value) ? value : `${value}Z`;
}

export function timestampToMs(raw: string): number {
  const parsed = new Date(normalizeTimestamp(raw));
  const ms = parsed.getTime();
  return Number.isNaN(ms) ? 0 : ms;
}

export function formatDateTime(raw: string): string {
  const parsed = new Date(normalizeTimestamp(raw));
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleString();
}

export function formatTime(raw: string): string {
  const parsed = new Date(normalizeTimestamp(raw));
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleTimeString();
}
