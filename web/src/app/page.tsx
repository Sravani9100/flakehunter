import Link from "next/link";

import { Empty } from "@/components/ui";
import { api, repoPath, type Repo } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export const dynamic = "force-dynamic";

const SOURCE_LABEL: Record<Repo["source"], string> = {
  github: "GitHub App",
  local: "Local checkout",
  upload: "CI upload",
};

export default async function ReposPage() {
  const repos = await api<Repo[]>("/api/repos");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Repositories</h1>
        <p className="mt-1 text-sm text-muted">
          A test is flaky when it passes and fails on the same commit.
        </p>
      </div>

      {repos.length === 0 ? (
        <Empty title="No test results yet">
          Upload JUnit reports from CI, install the GitHub App, or run{" "}
          <code className="font-mono">python scripts/seed_demo.py</code> for demo data.
        </Empty>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {repos.map((repo) => (
            <Link
              key={repo.full_name}
              href={repoPath(repo.full_name)}
              className="rounded-xl border border-border bg-surface p-5 transition hover:border-accent"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="font-mono text-sm font-medium">{repo.full_name}</span>
                <span className="shrink-0 text-xs text-muted">{SOURCE_LABEL[repo.source]}</span>
              </div>
              <div className="mt-4 flex items-baseline gap-2">
                <span
                  className={`text-3xl font-semibold tabular-nums ${repo.flaky_tests ? "text-fail" : "text-pass"}`}
                >
                  {repo.flaky_tests}
                </span>
                <span className="text-sm text-muted">flaky {repo.flaky_tests === 1 ? "test" : "tests"}</span>
              </div>
              <div className="mt-3 text-xs text-muted">
                {repo.total_runs} CI runs · last {timeAgo(repo.last_run_at)}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
