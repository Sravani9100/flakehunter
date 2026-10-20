import type { AgentStep } from "@/lib/api";
import { seconds } from "@/lib/format";

function describe(step: AgentStep): string {
  const input = step.input ?? {};
  switch (step.tool) {
    case "run_test":
      return `Ran the test ${input.runs} times`;
    case "read_file":
      return `Read ${input.path}`;
    case "list_files":
      return `Listed ${input.path}`;
    case "edit_file":
      return `Edited ${input.path}`;
    case "submit_fix":
      return input.fixed ? "Submitted a fix" : "Gave up";
    default:
      return step.tool ?? "Tool call";
  }
}

export function Trace({ steps }: { steps: AgentStep[] }) {
  if (steps.length === 0) return <p className="text-sm text-muted">No steps yet.</p>;
  return (
    <ol className="relative space-y-3 border-l border-border pl-5">
      {steps.map((step) => (
        <li key={step.index} className="relative">
          <span
            className={`absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-surface ${
              step.is_error ? "bg-fail" : step.kind === "tool" ? "bg-accent" : "bg-border"
            }`}
          />
          {step.kind === "tool" ? (
            <details>
              <summary className="cursor-pointer text-sm">
                <span className={step.is_error ? "text-fail" : ""}>{describe(step)}</span>
                {step.duration_s !== null && step.duration_s > 0.5 && (
                  <span className="ml-2 text-xs text-muted">{seconds(step.duration_s)}</span>
                )}
                {step.tool === "run_test" && step.output && (
                  <span className="ml-2 text-xs text-muted">{step.output.split("\n")[0]}</span>
                )}
              </summary>
              {step.tool === "edit_file" && step.input ? (
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <pre className="overflow-x-auto rounded-md bg-fail-soft p-2 font-mono text-xs">
                    {String(step.input.old_str) || "(new file)"}
                  </pre>
                  <pre className="overflow-x-auto rounded-md bg-pass-soft p-2 font-mono text-xs">
                    {String(step.input.new_str)}
                  </pre>
                </div>
              ) : (
                <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-surface-2 p-2 font-mono text-xs">
                  {step.output}
                </pre>
              )}
            </details>
          ) : (
            <p
              className={`whitespace-pre-wrap text-sm ${step.kind === "thinking" ? "italic text-muted" : ""}`}
            >
              {step.output}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
