"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Card, ErrorNotice, StatusBadge } from "@/components/ui";
import { api, type FixAttemptSummary } from "@/lib/api";
import { seconds, timeAgo, usd } from "@/lib/format";

export function FixPanel({
  fixUrl,
  attempts,
  aiEnabled,
}: {
  fixUrl: string;
  attempts: FixAttemptSummary[];
  aiEnabled: boolean;
}) {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = attempts.some((a) => a.status === "queued" || a.status === "running");

  async function startFix() {
    setStarting(true);
    setError(null);
    try {
      const attempt = await api<FixAttemptSummary>(fixUrl, { method: "POST" });
      router.push(`/fixes/${attempt.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStarting(false);
    }
  }

  const action = aiEnabled && (
    <Button onClick={startFix} disabled={starting || busy}>
      {starting ? "Starting…" : "Fix with AI"}
    </Button>
  );

  return (
    <Card title="Fix attempts" action={action}>
      {error && <ErrorNotice message={error} />}
      {attempts.length === 0 ? (
        <p className="text-sm text-muted">
          The agent reproduces the flake, edits the code, and reruns the test. A fix only counts if it
          passes every verification run and doesn&apos;t skip or weaken the test.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {attempts.map((attempt) => (
            <li key={attempt.id}>
              <Link
                href={`/fixes/${attempt.id}`}
                className="flex flex-wrap items-center justify-between gap-3 py-3 hover:opacity-80"
              >
                <div className="flex items-center gap-3">
                  <StatusBadge status={attempt.status} />
                  <span className="text-sm">Attempt #{attempt.id}</span>
                </div>
                <div className="flex gap-4 text-xs text-muted tabular-nums">
                  {attempt.verification_runs !== null && (
                    <span>
                      {attempt.verification_runs - (attempt.verification_failures ?? 0)}/
                      {attempt.verification_runs} passed
                    </span>
                  )}
                  <span>{usd(attempt.cost_usd)}</span>
                  <span>{seconds(attempt.duration_s)}</span>
                  <span>{timeAgo(attempt.created_at)}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
