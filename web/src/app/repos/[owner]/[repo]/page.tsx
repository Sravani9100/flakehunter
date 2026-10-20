import Link from "next/link";

import { Empty, FailRateBar } from "@/components/ui";
import { api, repoPath, type FlakyTest } from "@/lib/api";
import { splitIdentifier, timeAgo } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function RepoPage({ params }: { params: Promise<{ owner: string; repo: string }> }) {
  const { owner, repo } = await params;
  const fullName = `${owner}/${repo}`;
  const tests = await api<FlakyTest[]>(`/api/repos/${fullName}/flaky-tests`);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-muted hover:text-text">
          ← Repositories
        </Link>
        <h1 className="mt-2 font-mono text-2xl font-semibold">{fullName}</h1>
        <p className="mt-1 text-sm text-muted">
          Flaky tests from the last 14 days, most disruptive first.
        </p>
      </div>

      {tests.length === 0 ? (
        <Empty title="No flaky tests">Every test had a consistent outcome on every commit.</Empty>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-3 font-medium">Test</th>
                <th className="px-5 py-3 font-medium">Fail rate</th>
                <th className="px-5 py-3 font-medium">Flaky commits</th>
                <th className="px-5 py-3 font-medium">Runs</th>
                <th className="px-5 py-3 font-medium">Last flake</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tests.map((test) => {
                const [module, name] = splitIdentifier(test.identifier);
                return (
                  <tr key={test.id} className="hover:bg-surface-2">
                    <td className="px-5 py-3">
                      <Link href={`${repoPath(fullName)}/tests/${test.id}`} className="block">
                        <div className="font-mono font-medium">{name}</div>
                        <div className="font-mono text-xs text-muted">{test.file ?? module}</div>
                      </Link>
                    </td>
                    <td className="px-5 py-3">
                      <FailRateBar rate={test.fail_rate} />
                    </td>
                    <td className="px-5 py-3 tabular-nums">{test.flaky_commits}</td>
                    <td className="px-5 py-3 tabular-nums text-muted">
                      {test.failures}/{test.runs} failed
                    </td>
                    <td className="px-5 py-3 text-muted">{timeAgo(test.last_flake_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
