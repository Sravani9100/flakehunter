import { CategoryBadge, Empty, Stat, StatusBadge } from "@/components/ui";
import { ApiError, api, type EvalReport } from "@/lib/api";
import { seconds, usd } from "@/lib/format";

export const dynamic = "force-dynamic";

async function loadReport(): Promise<EvalReport | null> {
  try {
    return await api<EvalReport>("/api/evals/latest");
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export default async function EvalsPage() {
  const report = await loadReport();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Evals</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Each case is a small project with a planted flaky test and a known root cause. A fix counts only
          if the test then passes every fresh-process verification run without being skipped, deleted, or
          weakened.
        </p>
      </div>

      {!report ? (
        <Empty title="No eval results yet">
          Run <code className="font-mono">python evals/run_evals.py</code> with an Anthropic API key set.
        </Empty>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat
              label="Verified fixes"
              value={`${report.summary.verified_fixes}/${report.summary.cases}`}
              hint={`${report.verify_runs} runs each`}
            />
            <Stat
              label="Diagnosis accuracy"
              value={`${report.summary.diagnosis_correct}/${report.summary.cases}`}
              hint="root-cause category"
            />
            <Stat label="Cost per case" value={usd(report.summary.mean_cost_usd)} hint={report.model} />
            <Stat label="Time per case" value={seconds(report.summary.mean_duration_s)} hint={`effort: ${report.effort}`} />
          </div>

          <div className="overflow-x-auto rounded-xl border border-border bg-surface">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Case</th>
                  <th className="px-5 py-3 font-medium">Expected</th>
                  <th className="px-5 py-3 font-medium">Diagnosed</th>
                  <th className="px-5 py-3 font-medium">Fix</th>
                  <th className="px-5 py-3 font-medium">Before → after</th>
                  <th className="px-5 py-3 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {report.results.map((row) => {
                  const [baseFail, baseRuns] = row.baseline ?? [null, null];
                  const [verFail, verRuns] = row.verification;
                  return (
                    <tr key={row.case}>
                      <td className="px-5 py-3 font-mono">{row.case}</td>
                      <td className="px-5 py-3">
                        {row.expected_category && <CategoryBadge category={row.expected_category} />}
                      </td>
                      <td className="px-5 py-3">
                        <span className={row.diagnosis_correct ? "text-pass" : "text-fail"}>
                          {row.diagnosis_correct ? "✓" : "✗"}
                        </span>{" "}
                        <span className="font-mono text-xs">{row.diagnosis_category ?? "-"}</span>
                      </td>
                      <td className="px-5 py-3">
                        <StatusBadge status={row.fix_status} />
                      </td>
                      <td className="px-5 py-3 tabular-nums text-muted">
                        {baseRuns ? `${baseFail}/${baseRuns} failed` : "-"} →{" "}
                        {verRuns ? `${verRuns - (verFail ?? 0)}/${verRuns} passed` : "-"}
                      </td>
                      <td className="px-5 py-3 tabular-nums">{usd(row.cost_usd)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">
            Generated {new Date(report.generated_at).toLocaleString()} · total {usd(report.summary.total_cost_usd)}
          </p>
        </>
      )}
    </div>
  );
}
