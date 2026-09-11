export type TraceStatus = "unset" | "ok" | "error";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface TraceSummary {
  trace_id: string;
  name: string;
  session_id: string | null;
  status: TraceStatus;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  span_count: number;
  event_count: number;
}

export interface Usage {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cached_tokens?: number | null;
  reasoning_tokens?: number | null;
  attributes?: Record<string, JsonValue>;
}

export interface Span {
  span_id: string;
  trace_id: string;
  parent_span_id: string | null;
  span_type: string;
  name: string;
  started_at: string;
  ended_at: string | null;
  status: TraceStatus;
  input: JsonValue | null;
  output: JsonValue | null;
  attributes: Record<string, JsonValue>;
  usage: Usage | null;
  error: Record<string, JsonValue> | null;
}

export interface TraceDetail {
  schema_version: string;
  trace_id: string;
  project_id: string;
  session_id: string | null;
  name: string;
  started_at: string;
  ended_at: string | null;
  status: TraceStatus;
  attributes: Record<string, JsonValue>;
  spans: Span[];
  events: Array<{
    event_id: string;
    trace_id: string;
    name: string;
    timestamp: string;
    span_id: string | null;
    attributes: Record<string, JsonValue>;
  }>;
}

export interface Finding {
  result_id: string;
  trace_id: string;
  evaluation_type: string;
  code: string;
  severity: "info" | "warning" | "error" | string;
  message: string;
  created_at: string;
}

export interface Overview {
  window: { start: string; end: string };
  traces: { count: number; completed_count: number; error_count: number; error_rate: number | null };
  latency_ms: { p50: number | null; p95: number | null; p99: number | null };
  reported_tokens: {
    spans_with_usage: number;
    input: number | null;
    output: number | null;
    total: number | null;
  };
  evaluations: { count: number; status_counts: Record<string, number> };
  findings: { counts: Record<string, number> };
  recent_traces: TraceSummary[];
  recent_findings: Finding[];
}

export interface TimeseriesPoint {
  bucket_start: string;
  trace_count: number;
  error_count: number;
  completed_count: number;
  average_latency_ms: number | null;
  reported_total_tokens: number | null;
}

export interface EvaluationGroup {
  evaluation_type: string;
  evaluator_name: string;
  evaluator_version: string;
  evaluation_mode: string;
  config_fingerprint: string;
  judge_profile: string | null;
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  result_count: number;
  status_counts: Record<string, number>;
}

export interface EvaluationAnalytics {
  window: { start: string; end: string };
  groups: EvaluationGroup[];
  finding_counts: Record<string, number>;
}

export interface EvaluationResultItem {
  result_id: string;
  trace_id: string;
  evaluation_type: string;
  evaluator_name: string;
  evaluator_version: string;
  evaluation_mode: string;
  result_status: string;
  created_at: string;
}

export interface EvaluationResultList {
  window: { start: string; end: string };
  items: EvaluationResultItem[];
}

export interface EvaluationResultDetail extends EvaluationResultItem {
  result_schema_version: string;
  job_id: string;
  config: Record<string, JsonValue>;
  config_fingerprint: string;
  trace_fingerprint: string;
  metrics: Record<string, JsonValue>;
  findings: Array<{ code: string; severity: string; message: string; evidence: Record<string, JsonValue> }>;
  evidence: Record<string, JsonValue>;
  judge_invocations: Array<{
    invocation_id: string;
    judge_profile: string;
    provider: string;
    model: string;
    adapter_version: string;
    prompt_version: string;
    parameters: Record<string, JsonValue>;
    request_fingerprint: string;
    response_fingerprint: string;
    started_at: string;
    ended_at: string;
    status: string;
    token_usage: Record<string, JsonValue> | null;
  }>;
}

export interface RuntimeSummary {
  job_state_counts: Record<string, number>;
  recent_failures: Array<{
    job_id: string;
    evaluation_type: string;
    state: string;
    error_code: string | null;
    message: string | null;
    updated_at: string;
  }>;
  database: "ok" | "unavailable";
  redis: "ok" | "unavailable";
  worker: string;
  workers: Array<{
    worker_id: string;
    worker_type: string;
    started_at: string;
    last_seen: string;
    state: string;
    health: string;
  }>;
  read_only: true;
}

export interface DatasetCase {
  case_id: string;
  name: string;
  input: JsonValue;
  metadata: Record<string, JsonValue>;
  source: Record<string, JsonValue>;
  ground_truth: JsonValue | null;
  tags: string[];
  position: number;
}

export interface DatasetVersionSummary {
  dataset_version_id: string;
  dataset_id: string;
  version_number: number;
  status: "draft" | "finalized";
  source_metadata: Record<string, JsonValue>;
  case_count: number;
  content_checksum: string | null;
  created_at: string;
  finalized_at: string | null;
}

export interface Dataset {
  dataset_id: string;
  name: string;
  description: string;
  project_id: string;
  updated_at: string;
  created_at: string;
  latest_version: Pick<DatasetVersionSummary, "dataset_version_id" | "version_number" | "status" | "case_count" | "content_checksum"> | null;
  versions?: DatasetVersionSummary[];
}

export interface DatasetVersionDetail extends DatasetVersionSummary {
  cases: DatasetCase[];
}

export interface ReplayExecution {
  execution_id: string;
  replay_run_id: string;
  case_id: string;
  position: number;
  status: string;
  attempt_count: number;
  started_at: string | null;
  finished_at: string | null;
  target_request_fingerprint: string | null;
  target_response_fingerprint: string | null;
  output: JsonValue | null;
  safe_error: Record<string, JsonValue> | null;
  generated_trace_id: string | null;
}

export interface ReplayRun {
  replay_run_id: string;
  dataset_id: string;
  dataset_version_id: string;
  dataset_checksum: string;
  target_profile_id: string;
  target_name: string;
  target_type: string;
  target_version: string;
  replay_mode: string;
  reproducibility_status: string;
  status: string;
  manifest: Record<string, JsonValue>;
  max_concurrency: number;
  timeout_seconds: number;
  max_attempts: number;
  case_count: number;
  completed_count: number;
  succeeded_count: number;
  failed_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  executions?: ReplayExecution[];
}

export interface ReplayTargetProfile {
  profile_id: string;
  name: string;
  target_type: string;
  version: string;
  safety_class: string;
  configuration_reference: string;
}

export interface RegressionMetricRule {
  rule_id: string;
  metric_id: string;
  direction?: "higher_is_better" | "lower_is_better";
  absolute_tolerance: number | null;
  relative_tolerance: number | null;
  candidate_minimum: number | null;
  candidate_maximum: number | null;
  minimum_samples: number;
  required: boolean;
  informational: boolean;
  severity: string;
}

export interface RegressionPolicy {
  schema: string;
  policy_id: string;
  project_id: string;
  name: string;
  description: string;
  version: number;
  rules: RegressionMetricRule[];
  created_at: string;
}

export interface RegressionRun {
  regression_run_id: string;
  report_schema_version: string;
  baseline_replay_run_id: string;
  candidate_replay_run_id: string;
  dataset_id: string;
  dataset_version_id: string;
  dataset_checksum: string;
  policy_id: string;
  policy_version: number;
  evaluation_plan: Array<Record<string, JsonValue>>;
  baseline_manifest: Record<string, JsonValue>;
  candidate_manifest: Record<string, JsonValue>;
  changed_dimensions: string[];
  status: string;
  comparison_engine_version: string;
  regression_count: number;
  improvement_count: number;
  unchanged_count: number;
  insufficient_data_count: number;
  incompatible_count: number;
  has_regressions: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  policy?: RegressionPolicy;
}

export interface RegressionMetric {
  comparison_id: string;
  metric_id: string;
  rule_id: string;
  baseline_value: number | null;
  candidate_value: number | null;
  absolute_delta: number | null;
  relative_delta: number | null;
  direction: string | null;
  baseline_samples: number;
  candidate_samples: number;
  paired_samples: number;
  classification: string;
  candidate_limit_status: string;
  provenance: Record<string, JsonValue>;
  details: Record<string, JsonValue>;
}

export interface RegressionCase {
  case_comparison_id: string;
  case_id: string;
  position: number;
  baseline_execution_id: string | null;
  candidate_execution_id: string | null;
  baseline_trace_id: string | null;
  candidate_trace_id: string | null;
  status: string;
  metric_comparisons: Array<Record<string, JsonValue>>;
  introduced_findings: string[];
  resolved_findings: string[];
  details: Record<string, JsonValue>;
}

export interface QualityGateRule {
  gate_rule_id: string;
  name: string;
  source_type: string;
  metric_id: string | null;
  classification: string[];
  candidate_limit_status: string | null;
  metric_ids: string[];
  maximum_regressions: number | null;
  require_replay_modes: Record<string, string[]>;
  require_candidate_limit_ok: boolean;
  blocking: boolean;
  on_missing: string;
  on_incompatible: string;
  description: string;
}

export interface QualityGatePolicy {
  schema: string;
  gate_policy_id: string;
  project_id: string;
  name: string;
  description: string;
  version: number;
  rules: QualityGateRule[];
  created_at: string;
  content_fingerprint: string;
}

export interface QualityGateRuleResult {
  rule_id: string;
  rule_name: string;
  blocking: boolean;
  status: "passed" | "failed" | "indeterminate" | "not_applicable" | string;
  source_reference: Record<string, JsonValue>;
  expected_condition: Record<string, JsonValue>;
  actual_condition: Record<string, JsonValue>;
  message: string;
}

export interface QualityGateDecision {
  decision_id: string;
  gate_decision_id: string;
  project_id: string;
  regression_run_id: string;
  gate_policy_id: string;
  gate_policy_version: number;
  gate_policy_fingerprint: string;
  decision_schema_version: string;
  status: "passed" | "failed" | "indeterminate" | "error" | string;
  created_at: string;
  completed_at: string;
  blocking_failure_count: number;
  advisory_failure_count: number;
  indeterminate_count: number;
  rule_results: QualityGateRuleResult[];
  dataset_id: string;
  dataset_version_id: string;
  dataset_checksum: string;
  baseline_replay_run_id: string;
  candidate_replay_run_id: string;
  regression_report_schema: string;
  regression_report_fingerprint: string;
  comparison_engine_version: string;
  quality_gate_engine_version: string;
  evaluation_fingerprint: string;
}

export interface ApiErrorBody {
  code?: string;
  message?: string;
  request_id?: string;
}
