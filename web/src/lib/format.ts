export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function usd(value: number): string {
  return value < 0.01 && value > 0 ? "<$0.01" : `$${value.toFixed(2)}`;
}

export function seconds(value: number | null): string {
  if (value === null) return "-";
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

export function tokens(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value);
}

export function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

export function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const format = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(diff) >= size) return format.format(Math.round(diff / size), unit);
  }
  return "just now";
}

/** "tests.test_jobs::test_export_job_completes" -> ["tests.test_jobs", "test_export_job_completes"] */
export function splitIdentifier(identifier: string): [string, string] {
  const at = identifier.lastIndexOf("::");
  return at === -1 ? ["", identifier] : [identifier.slice(0, at), identifier.slice(at + 2)];
}
