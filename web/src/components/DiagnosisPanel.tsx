"use client";

import { useState } from "react";

import { Markdown } from "@/components/Markdown";
import { Button, Card, CategoryBadge, ErrorNotice } from "@/components/ui";
import { API_URL, type Diagnosis } from "@/lib/api";
import { percent, seconds, timeAgo, tokens, usd } from "@/lib/format";
import { readEvents } from "@/lib/sse";

export function DiagnosisPanel({
  diagnoseUrl,
  initial,
  aiEnabled,
}: {
  diagnoseUrl: string;
  initial: Diagnosis | null;
  aiEnabled: boolean;
}) {
  const [diagnosis, setDiagnosis] = useState(initial);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [thinking, setThinking] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function diagnose() {
    setRunning(true);
    setError(null);
    setThinking("");
    setStatus("Starting");
    try {
      const response = await fetch(`${API_URL}${diagnoseUrl}`, { method: "POST" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail ?? response.statusText);
      }
      for await (const { event, data } of readEvents(response)) {
        const payload = data as Record<string, string>;
        if (event === "status") setStatus(payload.message);
        else if (event === "thinking") setThinking((t) => t + payload.text);
        else if (event === "result") setDiagnosis(data as Diagnosis);
        else if (event === "error") setError(payload.message);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const action = aiEnabled && (
    <Button variant={diagnosis ? "secondary" : "primary"} onClick={diagnose} disabled={running}>
      {running ? "Diagnosing…" : diagnosis ? "Diagnose again" : "Diagnose with AI"}
    </Button>
  );

  return (
    <Card title="Root cause" action={action}>
      {error && <ErrorNotice message={error} />}

      {running && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm text-muted">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
            {status}
          </div>
          {thinking && (
            <p className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs text-muted">
              {thinking}
            </p>
          )}
        </div>
      )}

      {!running && !diagnosis && !error && (
        <p className="text-sm text-muted">
          {aiEnabled
            ? "Not diagnosed yet. The model reads the failure output, the test, and the code it imports."
            : "AI features are disabled on this server."}
        </p>
      )}

      {!running && diagnosis && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <CategoryBadge category={diagnosis.category} />
            <span className="text-xs text-muted">{percent(diagnosis.confidence)} confidence</span>
          </div>
          <p className="font-medium">{diagnosis.summary}</p>
          <Markdown>{diagnosis.explanation}</Markdown>
          {diagnosis.evidence.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Evidence</h3>
              <ul className="space-y-1.5">
                {diagnosis.evidence.map((item, i) => (
                  <li key={i} className="rounded-md bg-surface-2 px-3 py-1.5 font-mono text-xs">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Suggested fix</h3>
            <Markdown>{diagnosis.suggested_fix}</Markdown>
          </div>
          {diagnosis.thinking && (
            <details className="text-sm">
              <summary className="cursor-pointer text-muted">Model reasoning (summary)</summary>
              <p className="mt-2 whitespace-pre-wrap text-xs text-muted">{diagnosis.thinking}</p>
            </details>
          )}
          <p className="text-xs text-muted">
            {diagnosis.model} · {tokens(diagnosis.input_tokens)} in / {tokens(diagnosis.output_tokens)} out ·{" "}
            {usd(diagnosis.cost_usd)} · {seconds(diagnosis.duration_s)} · {timeAgo(diagnosis.created_at)}
          </p>
        </div>
      )}
    </Card>
  );
}
