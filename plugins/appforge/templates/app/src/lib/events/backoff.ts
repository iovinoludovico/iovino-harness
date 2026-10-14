// Retry schedule after the Nth failed attempt (1-based): 1m, 5m, 30m, 2h, 12h, then 24h.
const SCHEDULE_SECONDS = [60, 300, 1800, 7200, 43200, 86400];

/** Delay before the next attempt, with ±10% jitter to avoid thundering herds. */
export function retryDelaySeconds(failedAttempts: number, random = Math.random): number {
  const base = SCHEDULE_SECONDS[Math.min(Math.max(failedAttempts, 1), SCHEDULE_SECONDS.length) - 1];
  return Math.round(base * (0.9 + random() * 0.2));
}
