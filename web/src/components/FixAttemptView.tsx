"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { DiffView } from "@/components/DiffView";
import { Markdown } from "@/components/Markdown";
import { Trace } from "@/components/Trace";
import { Button, Card, CategoryBadge, ErrorNotice, Stat, StatusBadge } from "@/components/ui";
import { api, repoPath, type FixAttempt } from "@/lib/api";
import { seconds, shortSha, splitIdentifier, tokens, usd } from "@/lib/format";

const POLL_MS = 1500;

export function FixAttemptView({ id }: { id: number }) {
  const [attempt, setAttempt] = useState<FixAttempt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  const load = useCallback(async () => {
    try {
      setAttempt(await api<FixAttempt>(`/api/fix-attempts/${id}`));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  const active = !attempt || attempt.status === "queued" || attempt.status === "running";
  useEffect(() => {
    load();
    if (!active) return;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load, active]);

  async function openPullRequest() {
    setOpening(true);
    try {
      setAttempt(await api<FixAttempt>(`/api/fix-attempts/${id}/pull-request`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpening(false);
    }
  }

  if (!attempt) return error ? <ErrorNotice message={error} /> : <p className="text-muted">Loading…</p>;

  const [, name] = splitIdentifier(attempt.test_identifier);
  const passed =
    attempt.verification_runs !== null ? attempt.verification_runs - (attempt.verification_failures ?? 0) : null;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href={`${repoPath(attempt.repo)}/tests/${attempt.test_case_id}`}
          className="text-sm text-muted hover:text-text"
        >
          ← {name}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">Fix attempt #{attempt.id}</h1>
          <StatusBadge status={attempt.status} />
          {attempt.category && <CategoryBadge category={attempt.category} />}
        </div>
        <p className="mt-1 text-sm text-muted">
          {attempt.repo} at {shortSha(attempt.commit_sha)}
        </p>
      </div>

      {error && <ErrorNotice message={error} />}
      {attempt.error && <ErrorNotice message={attempt.error} />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Before"
          value={attempt.baseline_runs ? `${attempt.baseline_failures}/${attempt.baseline_runs}` : "-"}
          hint="runs failed"
        />
        <Stat
          label="After"
          value={passed !== null ? `${passed}/${attempt.verification_runs}` : "-"}
          hint="verification runs passed"
        />
        <Stat
          label="Cost"
          value={usd(attempt.cost_usd)}
          hint={`${tokens(attempt.input_tokens)} in / ${tokens(attempt.output_tokens)} out`}
        />
        <Stat label="Time" value={seconds(attempt.duration_s)} hint={attempt.model ?? undefined} />
      </div>

      {attempt.integrity_issues.length > 0 && (
        <ErrorNotice message={`Rejected: ${attempt.integrity_issues.join(" ")}`} />
      )}
      {attempt.review_notes.length > 0 && (
        <div className="rounded-lg border border-warn/30 bg-warn-soft px-4 py-3 text-sm text-warn">
          {attempt.review_notes.join(" ")}
        </div>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          {attempt.explanation && (
            <Card
              title="What the agent found"
              action={
                attempt.pr_url ? (
                  <a href={attempt.pr_url} target="_blank" rel="noreferrer" className="text-sm text-accent underline">
                    View pull request
                  </a>
                ) : (
                  attempt.can_open_pr && (
                    <Button onClick={openPullRequest} disabled={opening}>
                      {opening ? "Opening…" : "Open pull request"}
                    </Button>
                  )
                )
              }
            >
              <Markdown>{attempt.explanation}</Markdown>
            </Card>
          )}
          {attempt.diff && (
            <Card title="Change">
              <DiffView diff={attempt.diff} />
            </Card>
          )}
        </div>
        <Card title={`Agent trace (${attempt.steps.length} steps)`} className="lg:col-span-2">
          <Trace steps={attempt.steps} />
          {active && (
            <p className="mt-4 flex items-center gap-2 text-xs text-muted">
              <span className="h-2 w-2 animate-pulse rounded-full bg-accent" /> Working…
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
