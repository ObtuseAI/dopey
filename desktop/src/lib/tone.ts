export type StatusTone = "nominal" | "warning" | "critical" | "unknown";
export type DirectionTone = "bullish" | "bearish" | "neutral";

const CRITICAL_MARKERS = [
  "fail", "fault", "block", "error", "missing", "unreadable", "invalid", "reject", "no_eligible", "unavailable",
] as const;
const WARNING_MARKERS = [
  "stale", "warn", "pending", "unknown", "diagnostic", "degraded", "partial", "insufficient",
] as const;
const NOMINAL_MARKERS = [
  "pass", "healthy", "active", "running", "available", "complete", "ready", "parent",
] as const;

const includesAny = (value: string, markers: readonly string[]): boolean =>
  markers.some((marker) => value.includes(marker));

export const statusTone = (status: string | null): StatusTone => {
  const normalized = status?.toLowerCase() ?? "";
  if (includesAny(normalized, CRITICAL_MARKERS)) {
    return "critical";
  }
  if (includesAny(normalized, WARNING_MARKERS)) {
    return "warning";
  }
  if (includesAny(normalized, NOMINAL_MARKERS)) {
    return "nominal";
  }
  return "unknown";
};

export const directionTone = (direction: string): DirectionTone => {
  const normalized = direction.toLowerCase();
  if (normalized.includes("bull") || normalized.includes("positive") || normalized.includes("supported") || normalized.includes("active")) {
    return "bullish";
  }
  if (normalized.includes("bear") || normalized.includes("negative") || normalized.includes("fragile") || normalized.includes("blocked")) {
    return "bearish";
  }
  return "neutral";
};
