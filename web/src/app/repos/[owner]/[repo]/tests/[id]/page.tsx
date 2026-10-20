import Link from "next/link";

import { DiagnosisPanel } from "@/components/DiagnosisPanel";
import { FixPanel } from "@/components/FixPanel";
import { HistoryStrip } from "@/components/HistoryStrip";
import { Card, Code, Stat } from "@/components/ui";
import { api, repoPath, type TestDetail } from "@/lib/api";
import { percent, shortSha, splitIdentifier, timeAgo } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function TestPage({
  params,
}: {
  params: Promise<{ owner: string; repo: string; id: string }>;
}) {
  const { owner, repo, id } = await params;
  const base = `/api/repos/${owner}/${repo}/tests/${id}`;
  const test = await api<TestDetail>(base);
  const [module, name] = splitIdentifier(test.identifier);
  const failure = test.latest_failure;

  return (
    <div className="space-y-6">
      <div>
        <Link href={repoPath(test.repo)} className="text-sm text-muted hover:text-text">
          ← {test.repo}
        </Link>
        <h1 className="mt-2 break-all font-mono text-2xl font-semibold">{name}</h1>
        <p className="mt-1 font-mono text-sm text-muted">{test.file ?? module}</p>
      </div>

      {test.stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Fail rate" value={percent(test.stats.fail_rate)} />
          <Stat label="Failures" value={`${test.stats.failures}/${test.stats.runs}`} hint="runs" />
          <Stat label="Flaky commits" value={test.stats.flaky_commits} hint="passed and failed" />
          <Stat label="Last flake" value={timeAgo(test.stats.last_flake_at)} />
        </div>
      )}

      <Card title="History">
        <HistoryStrip history={test.history} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <DiagnosisPanel diagnoseUrl={`${base}/diagnose`} initial={test.diagnosis} aiEnabled={test.ai_enabled} />
        <div className="space-y-6">
          <FixPanel fixUrl={`${base}/fix`} attempts={test.fix_attempts} aiEnabled={test.ai_enabled} />
          {failure && (
            <Card title="Latest failure">
              <p className="mb-3 text-xs text-muted">
                Commit {shortSha(failure.commit_sha)} · {failure.branch ?? "unknown branch"} ·{" "}
                {timeAgo(failure.recorded_at)}
              </p>
              <Code>{[failure.message, failure.details].filter(Boolean).join("\n\n")}</Code>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
