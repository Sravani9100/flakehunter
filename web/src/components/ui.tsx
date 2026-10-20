import type { FixStatus } from "@/lib/api";

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-border bg-surface ${className}`}>
      {title && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
          <h2 className="font-semibold">{title}</h2>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const STATUS_STYLES: Record<FixStatus, [string, string]> = {
  queued: ["Queued", "bg-surface-2 text-muted"],
  running: ["Running", "bg-accent-soft text-accent"],
  verified: ["Verified fix", "bg-pass-soft text-pass"],
  not_fixed: ["Not fixed", "bg-warn-soft text-warn"],
  rejected: ["Rejected", "bg-fail-soft text-fail"],
  error: ["Error", "bg-fail-soft text-fail"],
};

export function StatusBadge({ status }: { status: FixStatus }) {
  const [label, style] = STATUS_STYLES[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status === "running" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />}
      {label}
    </span>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  return (
    <span className="rounded-full border border-border bg-surface-2 px-2.5 py-0.5 font-mono text-xs">
      {category.replace("_", " ")}
    </span>
  );
}

export function FailRateBar({ rate }: { rate: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-fail" style={{ width: `${Math.max(rate * 100, 3)}%` }} />
      </div>
      <span className="tabular-nums text-sm">{Math.round(rate * 100)}%</span>
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" }) {
  const styles =
    variant === "primary"
      ? "bg-accent text-white hover:opacity-90"
      : "border border-border bg-surface hover:bg-surface-2";
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}
    >
      {children}
    </button>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-fail/30 bg-fail-soft px-4 py-3 text-sm text-fail">{message}</div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-lg text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg bg-surface-2 p-4 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  );
}
