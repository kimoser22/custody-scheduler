/** Human-readable expiry line for pending override requests (UTC). */

export function formatExpiryLabel(
  expiresAt: string,
  now: Date = new Date(),
): string {
  const expires = new Date(
    expiresAt.endsWith("Z") || expiresAt.includes("+")
      ? expiresAt
      : `${expiresAt}Z`,
  );
  if (Number.isNaN(expires.getTime())) {
    return `Expires ${expiresAt}`;
  }

  const absolute = expires.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
  const ms = expires.getTime() - now.getTime();
  if (ms <= 0) {
    return `Expired · ${absolute}`;
  }

  const hours = Math.floor(ms / (1000 * 60 * 60));
  const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
  let relative: string;
  if (hours >= 48) {
    const days = Math.floor(hours / 24);
    relative = `Expires in ${days} day${days === 1 ? "" : "s"}`;
  } else if (hours >= 1) {
    relative = `Expires in ${hours} hour${hours === 1 ? "" : "s"}`;
  } else {
    relative = `Expires in ${Math.max(1, minutes)} minute${minutes === 1 ? "" : "s"}`;
  }
  return `${relative} · ${absolute}`;
}
