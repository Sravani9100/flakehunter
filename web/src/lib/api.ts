// Types mirror flakehunter/schemas.py.

export type Outcome = "passed" | "failed" | "error" | "skipped";
export type FixStatus = "queued" | "running" | "verified" | "not_fixed" | "rejected" | "error";

export interface Repo {
  full_name: string;
  source: "github" | "local" | "upload";
  flaky_tests: number;
  total_runs: number;
  last_run_at: string | null;
}

export interface FlakyTest {
  id: number;
  identifier: string;
  file: string | null;
  runs: number;
  failures: number;
  fail_rate: number;
  flaky_commits: number;
  last_flake_at: string | null;
}

export interface Result {
  run_id: number;
  commit_sha: string;
  branch: string | null;
  run_attempt: number;
  outcome: Outcome;
  duration_s: number | null;
  message: string | null;
  details: string | null;
  recorded_at: string;
}

export interface Diagnosis {
  id: number;
  category: string;
  confidence: number;
  summary: string;
  explanation: string;
  evidence: string[];
  suggested_fix: string;
  thinking: string | null;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_s: number;
  created_at: string;
}

export interface FixAttemptSummary {
  id: number;
  status: FixStatus;
  commit_sha: string;
  category: string | null;
  baseline_runs: number | null;
  baseline_failures: number | null;
  verification_runs: number | null;
  verification_failures: number | null;
  cost_usd: number;
  duration_s: number | null;
  pr_url: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface AgentStep {
  index: number;
  kind: "thinking" | "text" | "tool";
  tool: string | null;
  input: Record<string, unknown> | null;
  output: string | null;
  is_error: boolean;
  duration_s: number | null;
}

export interface FixAttempt extends FixAttemptSummary {
  test_case_id: number;
  repo: string;
  test_identifier: string;
  explanation: string | null;
  diff: string | null;
  integrity_issues: string[];
  review_notes: string[];
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
  can_open_pr: boolean;
  steps: AgentStep[];
}

export interface TestDetail {
  id: number;
  repo: string;
  identifier: string;
  file: string | null;
  stats: {
    runs: number;
    failures: number;
    fail_rate: number;
    flaky_commits: number;
    last_flake_at: string | null;
  } | null;
  latest_failure: Result | null;
  history: Result[];
  diagnosis: Diagnosis | null;
  fix_attempts: FixAttemptSummary[];
  ai_enabled: boolean;
}

export interface EvalRow {
  case: string;
  expected_category?: string;
  accepted_categories?: string[];
  diagnosis_category: string | null;
  diagnosis_correct: boolean;
  diagnosis_summary?: string;
  fix_status: FixStatus;
  fix_category?: string | null;
  baseline?: [number | null, number | null];
  verification: [number | null, number | null];
  integrity_issues?: string[];
  review_notes?: string[];
  agent_steps?: number;
  explanation?: string | null;
  diff?: string | null;
  error: string | null;
  cost_usd: number;
  duration_s: number;
}

export interface EvalReport {
  generated_at: string;
  model: string;
  effort: string;
  verify_runs: number;
  summary: {
    cases: number;
    verified_fixes: number;
    rejected_fixes: number;
    diagnosis_correct: number;
    total_cost_usd: number;
    mean_cost_usd: number;
    mean_duration_s: number;
  };
  results: EvalRow[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// Server components reach the API directly; the browser uses the public URL.
export const API_URL =
  typeof window === "undefined"
    ? (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, `Can't reach the FlakeHunter API at ${API_URL}. Is it running?`);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function repoPath(fullName: string): string {
  return `/repos/${fullName}`;
}
