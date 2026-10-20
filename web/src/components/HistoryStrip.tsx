import type { Result } from "@/lib/api";
import { shortSha } from "@/lib/format";

const COLORS: Record<Result["outcome"], string> = {
  passed: "bg-pass",
  failed: "bg-fail",
  error: "bg-fail",
  skipped: "bg-border",
};

/** One square per run, oldest on the left. Gaps separate commits. */
export function HistoryStrip({ history }: { history: Result[] }) {
  const runs = [...history].reverse();
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1">
        {runs.map((run, i) => {
          const newCommit = i > 0 && runs[i - 1].commit_sha !== run.commit_sha;
          return (
            <span
              key={`${run.run_id}`}
              title={`${run.outcome} · ${shortSha(run.commit_sha)} · ${new Date(run.recorded_at).toLocaleString()}`}
              className={`h-5 w-2.5 rounded-sm ${COLORS[run.outcome]} ${newCommit ? "ml-2" : ""}`}
            />
          );
        })}
      </div>
      <div className="mt-2 flex gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-pass" /> passed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-fail" /> failed
        </span>
        <span>Gaps separate commits. Oldest first.</span>
      </div>
    </div>
  );
}
