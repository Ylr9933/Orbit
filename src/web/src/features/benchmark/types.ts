export interface Annotation {
  name?: string;
  notes?: string;
  project?: string;
  tags?: string;
  revision?: number;
}
export interface BenchmarkRun {
  run_id: string | null;
  attempt_id: string | null;
  unit_id: string;
  state: string;
  candidate_id: string;
  model: string;
  agent: string;
  benchmark: string;
  execution: string | null;
  evaluation: string | null;
  protocol: string | null;
  score_valid: boolean;
  metrics: Record<string, number>;
  failure_reason: string | null;
  elapsed_seconds: number | null;
  budget_seconds: number | null;
  created_at: string;
  updated_at: string;
  cleanup_complete: boolean | null;
  cancel_requested: boolean;
  has_evidence: boolean;
  config: Record<string, unknown>;
  resources: Record<string, unknown>;
  annotation: Annotation;
}
export interface Batch {
  id: string;
  name: string;
  annotation: Annotation;
  models: string[];
  benchmarks: string[];
  total: number;
  finished: number;
  scored: number;
  failed: number;
  states: Record<string, number>;
  metrics: Record<string, { mean: number; count: number }>;
  cohort: string;
  duplicate_tasks: boolean;
  created_at: string;
  updated_at: string;
}
export interface BatchDetail extends Batch {
  runs: BenchmarkRun[];
}
export interface Overview {
  batches: Batch[];
  errors: { id: string; message: string }[];
  settings: { baseline?: string; revision?: number };
}
export interface ComparisonRow {
  unit_id: string;
  left: BenchmarkRun | null;
  right: BenchmarkRun | null;
  delta: number | null;
  reason: string | null;
}
export interface Comparison {
  metric: string;
  rows: ComparisonRow[];
  paired: number;
  total: number;
  left_mean: number | null;
  right_mean: number | null;
  mean_delta: number | null;
  aggregation: string;
}
export interface Step {
  step_index: number;
  timestamp_ms: number | null;
  step_type: string;
  content: string;
  content_truncated?: boolean;
  metadata: Record<string, string | number | boolean>;
}
export interface Trajectory {
  run_id: string;
  capture_status: string;
  trajectory: { capture_status: string; total_steps?: number; origin?: string };
  calls: { last_reported_usage?: Record<string, number> };
  steps: Step[];
  matched_steps: number;
  next_cursor: number | null;
  search_scope: string | null;
}
