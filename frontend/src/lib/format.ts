const fmt = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-GB", opts);

export const formatDate = (iso: string) => fmt({ day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
export const formatShort = (iso: string) => fmt({ day: "numeric", month: "short" }).format(new Date(iso));
export const formatDateTime = (iso: string) =>
  fmt({ day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

export function addDays(iso: string, days: number) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
