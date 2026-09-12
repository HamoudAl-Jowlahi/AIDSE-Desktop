/**
 * AIDSE Platform — API Client
 * All typed API calls to the FastAPI backend.
 * Handles token refresh on 401 automatically.
 */

import { setSessionNotice } from "./session-notice";

let _apiBase: string | null = null;
let _internalToken: string | null = null;

export function getApiBase(): string {
  if (_apiBase) return _apiBase;

  // In the packaged app the backend serves this page, so the API is always on
  // the same origin — and that is the only answer that survives the port
  // changing. The sidecar falls forward to 8011, 8012 … whenever 8010 is
  // taken, and .env.local bakes NEXT_PUBLIC_API_URL=127.0.0.1:8010 into the
  // bundle at build time. Consulting that first meant every request went to a
  // port nothing was listening on, and the whole app failed with "not found"
  // errors that looked like missing data.
  const origin =
    typeof window !== "undefined" && window.location?.origin
      ? `${window.location.origin}/api/v1`
      : null;

  if (origin && process.env.NODE_ENV !== "development") {
    return origin;
  }

  // `next dev` serves the page on :3000 while the API listens elsewhere, so
  // the explicit override is only meaningful during development.
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  return origin ?? "http://127.0.0.1:8010/api/v1";
}

export function setApiBase(url: string): void {
  _apiBase = url;
}

export function setInternalToken(token: string): void {
  _internalToken = token;
}


// ── Types ──────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface ProjectCreate {
  name: string;
  type?: string;
  description?: string;
}

export interface ProjectOut {
  id: string;
  name: string;
  project_type: string;
  description: string | null;
  owner_id: string;
  created_at: string;
  member_count: number;
}

export interface ProjectListOut {
  items: ProjectOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface MemberInvite {
  email: string;
  role: "viewer" | "editor" | "admin";
}

export interface MemberOut {
  id: string;
  project_id: string;
  user_id: string;
  role: string;
  invited_at: string;
  user_name: string | null;
  user_email: string | null;
}

export interface AuditLogOut {
  id: string;
  project_id: string;
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string | null;
  metadata: Record<string, unknown> | null;
  occurred_at: string;
}

export interface DatasetVersionResponse {
  id: string;
  dataset_id: string;
  version_tag: string;
  s3_key: string;
  profile_data: Record<string, any> | null;
  profile_status?: "pending" | "ready" | "failed" | null;
  parent_version_id?: string | null;
  transformation_history?: Record<string, any>[] | null;
}

export interface DatasetResponse {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  format: string;
  versions: DatasetVersionResponse[];
}

export interface DatasetCreate {
  name: string;
  description?: string;
  format: string;
}

export interface DatasetVersionCreate {
  version_tag: string;
  s3_key: string;
}

export interface GoldenCaseResponse {
  id: string;
  golden_dataset_id: string;
  input_data: string;
  expected_output: string;
  category_tag: string | null;
}

export interface GoldenDatasetResponse {
  id: string;
  project_id: string;
  name: string;
  version: number;
  baseline_run_id: string | null;
  cases: GoldenCaseResponse[];
}

export interface GoldenDatasetCreate {
  name: string;
  version?: number;
}

export interface ApiError {
  error: { code: string; message: string };
}

// ── Token storage ──────────────────────────────────────────────────────────

let _accessToken: string | null = null;

export function setAccessToken(token: string): void {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export function clearTokens(): void {
  _accessToken = null;
}

// ── Core fetch wrapper ─────────────────────────────────────────────────────

let _redirectingToLogin = false;

function redirectToLoginExpired(): void {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "127.0.0.1" || host === "localhost") {
      // In local desktop mode, do not redirect to login
      return;
    }
  }
  if (_redirectingToLogin) return;
  _redirectingToLogin = true;
  setSessionNotice("expired");
  window.location.href = "/login";
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  // Ask the Tauri shell for the backend port and session token before the
  // first call. connectToSidecar() caches, so this costs one await after that,
  // and it is a no-op outside Tauri. Imported dynamically to keep api.ts and
  // sidecar.ts from forming an import cycle.
  if (typeof window !== "undefined") {
    const { connectToSidecar } = await import("./sidecar");
    await connectToSidecar();
  }

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (_internalToken) {
    headers["X-AIDSE-Internal-Token"] = _internalToken;
  }

  if (_accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  }

  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });

  if (res.status === 401 && retry) {
    // Attempt refresh
    const refreshed = await attemptTokenRefresh();
    if (refreshed) {
      return request<T>(path, options, false);
    }
    // Refresh failed → session truly over. Tell the user, then redirect.
    redirectToLoginExpired();
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const errorData = (await res.json().catch(() => ({}))) as any;
    let errorMsg = res.statusText;
    
    if (Array.isArray(errorData?.detail)) {
      errorMsg = errorData.detail.map((err: any) => err.msg).join(", ");
    } else {
      errorMsg = errorData?.detail?.error?.message || errorData?.error?.message || (typeof errorData?.detail === 'string' ? errorData.detail : null) || res.statusText;
    }
    
    throw Object.assign(new Error(errorMsg), {
      status: res.status,
      data: errorData,
    });
  }

  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

async function attemptTokenRefresh(): Promise<boolean> {
  try {
    const refreshToken = document.cookie
      .split("; ")
      .find((c) => c.startsWith("refresh_token="))
      ?.split("=")[1];

    if (!refreshToken) return false;

    const res = await fetch(`${getApiBase()}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) return false;

    const data = (await res.json()) as AccessTokenResponse;
    setAccessToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}

// ── Auth API ───────────────────────────────────────────────────────────────

export const auth = {
  register: (name: string, email: string, password: string) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<UserOut>("/auth/me"),

  /** Whether a master password is configured, i.e. whether to show the lock. */
  hasPassword: () => request<{ has_password: boolean }>("/auth/has-password"),

  /** Check the master password. Rejects on a wrong password or rate limit. */
  verifyPassword: (password: string) =>
    request<{ valid: boolean; message: string }>("/auth/verify-password", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
};

// ── Projects API ───────────────────────────────────────────────────────────

export const projects = {
  list: (page = 1, pageSize = 20) =>
    request<ProjectListOut>(`/projects?page=${page}&page_size=${pageSize}`),

  create: (payload: ProjectCreate) =>
    request<ProjectOut>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  get: (id: string) => request<ProjectOut>(`/projects/${id}`),

  delete: (id: string) =>
    request<void>(`/projects/${id}`, {
      method: "DELETE",
    }),

  inviteMember: (projectId: string, payload: MemberInvite) =>
    request<MemberOut>(`/projects/${projectId}/members`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  auditLogs: (projectId: string, page = 1) =>
    request<AuditLogOut[]>(`/projects/${projectId}/audit-logs?page=${page}`),
};

// ── Datasets API ───────────────────────────────────────────────────────────

export const datasets = {
  list: (projectId: string) =>
    request<DatasetResponse[]>(`/projects/${projectId}/datasets`),

  delete: (projectId: string, datasetId: string) =>
    request<void>(`/projects/${projectId}/datasets/${datasetId}`, { method: "DELETE" }),

  create: (projectId: string, payload: DatasetCreate) =>
    request<DatasetResponse>(`/projects/${projectId}/datasets`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createVersion: (projectId: string, datasetId: string, payload: DatasetVersionCreate) =>
    request<DatasetVersionResponse>(`/projects/${projectId}/datasets/${datasetId}/versions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  get: (projectId: string, datasetId: string) =>
    request<DatasetResponse>(`/projects/${projectId}/datasets/${datasetId}`),

  uploadFile: (projectId: string, datasetId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<DatasetVersionResponse>(`/projects/${projectId}/datasets/${datasetId}/upload`, {
      method: "POST",
      body: formData,
    });
  },

  transform: (projectId: string, datasetId: string, versionId: string, payload: { steps: any[] }) =>
    request<DatasetVersionResponse>(`/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/transform`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  downloadVersion: async (projectId: string, datasetId: string, versionId: string, filename: string) => {
    const headers: Record<string, string> = {};
    if (_accessToken) {
      headers["Authorization"] = `Bearer ${_accessToken}`;
    }
    const res = await fetch(`${_apiBase}/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/download`, {
      method: "GET",
      headers,
    });
    if (!res.ok) {
      throw new Error(`Failed to download dataset. Status: ${res.status}`);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || `dataset_version_${versionId}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  listGolden: (projectId: string) =>
    request<GoldenDatasetResponse[]>(`/projects/${projectId}/datasets/golden-datasets`),

  createGolden: (projectId: string, payload: GoldenDatasetCreate) =>
    request<GoldenDatasetResponse>(`/projects/${projectId}/datasets/golden-datasets`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// ── Data Quality API ───────────────────────────────────────────────────────

export interface QualityRecommendation {
  technique: string;
  alternatives: string[];
  reason: string;
  risk: string;
}

export interface QualityIssue {
  id: string;
  severity: "critical" | "warning" | "info";
  category: string;
  title: string;
  columns: string[];
  affected_count: number | null;
  affected_pct: number | null;
  detection_method: string;
  why_it_matters: string;
  recommendation: QualityRecommendation;
}

export interface QualitySummary {
  critical: number;
  warning: number;
  info: number;
  available: boolean;
  pending_profiling?: boolean;
}

export interface QualityReport {
  issues: QualityIssue[];
  summary: QualitySummary;
}

export const quality = {
  getVersionReport: (projectId: string, datasetId: string, versionId: string) =>
    request<QualityReport>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/quality`
    ),
};

// ── Outlier Intelligence API ───────────────────────────────────────────────

export interface OutlierScanItem {
  column: string;
  count: number;
  share_pct: number;
  lower_fence: number | null;
  upper_fence: number | null;
  recommendation: QualityRecommendation;
}

export interface OutlierScanResponse {
  scanned_columns: number;
  items: OutlierScanItem[];
}

export interface OutlierMethodResult {
  method: string;
  count: number;
  params: Record<string, any>;
}

export interface OutlierDetailResponse {
  column: string;
  num_rows: number;
  methods: OutlierMethodResult[];
  histogram: { bin_edges: number[]; counts: number[] } | null;
  fences: Record<string, any> | null;
  recommendation: QualityRecommendation;
}

export const outliers = {
  scan: (projectId: string, datasetId: string, versionId: string, mlTask?: string) =>
    request<OutlierScanResponse>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/outliers` +
      (mlTask ? `?ml_task=${mlTask}` : "")
    ),

  detail: (
    projectId: string,
    datasetId: string,
    versionId: string,
    column: string,
    method: string = "iqr"
  ) =>
    request<OutlierDetailResponse>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/outliers/detail` +
      `?column=${encodeURIComponent(column)}&method=${method}`
    ),
};

// ── Preparation Workbench API ──────────────────────────────────────────────

export interface HistoryStep {
  step_no: number;
  action: string;
  column: string | null;
  params: Record<string, any> | null;
  note?: string | null;
}

export interface PreviewResponse {
  ok: boolean;
  error: string | null;
  truncated_for_preview: boolean;
  rows_before: number;
  rows_after: number;
  columns_before: number;
  columns_after: number;
  applied_steps: HistoryStep[];
  sample_before: Record<string, any>[];
  sample_after: Record<string, any>[];
  changed_columns: { column: string; change: string; before?: any; after?: any }[];
}

export interface VersionHistoryEntry {
  version_id: string;
  version_tag: string;
  parent_version_id: string | null;
  steps: HistoryStep[];
}

export interface CompareColumnChange {
  column: string;
  change: string;
  before?: any;
  after?: any;
}

export interface CompareResponse {
  from_version_id: string;
  to_version_id: string;
  rows_before: number;
  rows_after: number;
  duplicate_rows_before: number;
  duplicate_rows_after: number;
  missing_cells_before: number;
  missing_cells_after: number;
  columns_added: string[];
  columns_removed: string[];
  columns_changed: CompareColumnChange[];
}

export interface TransformStepInput {
  action: string;
  column: string;
  params?: Record<string, any>;
}

export const preparation = {
  preview: (projectId: string, datasetId: string, versionId: string, steps: TransformStepInput[]) =>
    request<PreviewResponse>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/preview-transform`,
      { method: "POST", body: JSON.stringify({ steps }) }
    ),

  history: (projectId: string, datasetId: string, versionId: string) =>
    request<VersionHistoryEntry[]>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/history`
    ),

  revert: (projectId: string, datasetId: string, versionId: string) =>
    request<DatasetVersionResponse>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/revert`,
      { method: "POST" }
    ),

  compare: (projectId: string, datasetId: string, fromVersionId: string, toVersionId: string) =>
    request<CompareResponse>(
      `/projects/${projectId}/datasets/${datasetId}/compare` +
      `?from_version=${fromVersionId}&to_version=${toVersionId}`
    ),
};

export interface ModelTrialResponse {
  id: string;
  experiment_id: string;
  algorithm_name: string;
  hyperparameters: Record<string, any>;
  metrics: Record<string, number>;
  primary_metric_score: number | null;
  mlflow_run_id: string | null;
  is_best: boolean;
  status: string;
  created_at: string;
}

export interface ExperimentCreate {
  target_column: string;
  problem_type: string;
  primary_metric: string;
  // Phase 8: focused model ids; omitted → task-appropriate defaults
  algorithms?: string[];
}

export interface ExperimentResponse {
  id: string;
  project_id: string;
  dataset_id: string;
  target_column: string;
  problem_type: string;
  primary_metric: string;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  trials: ModelTrialResponse[];
}

// ── ML Task Detection API ──────────────────────────────────────────────────

export interface MetricRecommendation {
  metric: string;
  primary: boolean;
  explanation: string;
}

export interface ModelRecommendation {
  id: string;
  name: string;
  why: string;
}

export interface SuggestedTarget {
  column: string;
  task_type: string;
  confidence: "high" | "medium" | "low";
  reason: string;
  rank: number;
}

export interface TaskDetectionResponse {
  target_column: string | null;
  task_type: "classification" | "regression" | "unsupervised" | null;
  confidence: string | null;
  needs_confirmation: boolean;
  question?: string | null;
  alternative_task?: string | null;
  suggested_target?: string | null;
  suggested_targets?: SuggestedTarget[];
  notes: string[];
  class_balance?: { status: string; minority_pct?: number } | null;
  recommended_metrics: MetricRecommendation[];
  recommended_models: ModelRecommendation[];
}

export const taskDetection = {
  detect: (
    projectId: string,
    datasetId: string,
    versionId: string,
    targetColumn?: string
  ) =>
    request<TaskDetectionResponse>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/task-detection` +
      (targetColumn ? `?target_column=${encodeURIComponent(targetColumn)}` : "")
    ),
};

// ── Model Evaluation API (Phase 9) ─────────────────────────────────────────

export interface MetricEvaluation {
  metric: string;
  value: number;
  explanation: string;
  interpretation: string;
  higher_is_better: boolean;
  is_primary: boolean;
}

export interface ConfusionMatrix {
  labels: string[];
  matrix: number[][];
}

export interface PerClassStat {
  class_name: string;
  precision: number;
  recall: number;
  f1_score: number;
  support: number;
}

export interface EvaluationResponse {
  experiment_id: string;
  problem_type: string;
  primary_metric: string;
  target_column: string;
  status: string;
  trials_evaluated: number;
  metrics: MetricEvaluation[];
  confusion_matrix: ConfusionMatrix | null;
  confusion_matrix_reading_guide?: string | null;
  per_class: PerClassStat[] | null;
  trial_comparisons: { trial_id: string; algorithm: string; primary_score: number | null; is_best: boolean }[];
}

export const evaluation = {
  getExperimentEvaluation: (projectId: string, experimentId: string) =>
    request<EvaluationResponse>(
      `/projects/${projectId}/automl/experiments/${experimentId}/evaluation`
    ),
};

// ── AI Data Analyst API (Phase 11) ─────────────────────────────────────────

export interface ToolUsage {
  tool: string;
  args: Record<string, any>;
  key_numbers?: Record<string, any> | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  tools_used: ToolUsage[] | null;
  generated_by: string | null;
  created_at: string;
}

export interface ChatHistoryResponse {
  conversation_id: string | null;
  dataset_id: string | null;
  messages: ChatMessage[];
}

export interface ChatResponse {
  answer: string;
  tools_used: ToolUsage[];
  generated_by: string;
  conversation_id: string;
}

export const chat = {
  send: (projectId: string, message: string, datasetId?: string) =>
    request<ChatResponse>(`/projects/${projectId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message, dataset_id: datasetId }),
    }),

  history: (projectId: string, datasetId?: string) =>
    request<ChatHistoryResponse>(
      `/projects/${projectId}/chat/history` +
      (datasetId ? `?dataset_id=${datasetId}` : "")
    ),
};

// ── AI Evaluation API (Phases 12-14) ───────────────────────────────────────

export interface GoldenCaseInput {
  input_data: string;
  expected_output: string;
  category_tag?: string | null;
}

export const golden = {
  updateDataset: (projectId: string, gid: string, payload: { name?: string; version?: number }) =>
    request<GoldenDatasetResponse>(`/projects/${projectId}/datasets/golden-datasets/${gid}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteDataset: (projectId: string, gid: string) =>
    request<void>(`/projects/${projectId}/datasets/golden-datasets/${gid}`, { method: "DELETE" }),

  bulkCases: (projectId: string, gid: string, cases: GoldenCaseInput[]) =>
    request<GoldenCaseResponse[]>(`/projects/${projectId}/datasets/golden-datasets/${gid}/cases/bulk`, {
      method: "POST",
      body: JSON.stringify({ cases }),
    }),

  deleteCase: (projectId: string, gid: string, caseId: string) =>
    request<void>(`/projects/${projectId}/datasets/golden-datasets/${gid}/cases/${caseId}`, {
      method: "DELETE",
    }),
};

export type ScoringStrategy = "exact" | "regex" | "semantic" | "llm_judge";

export interface EvaluationRunSummary {
  id: string;
  golden_dataset_id: string;
  provider: string;
  scoring_strategy: string | null;
  status: string;
  aggregate_results: Record<string, any> | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface EvaluationRunFull extends EvaluationRunSummary {
  results: {
    id: string;
    golden_case_id: string;
    actual_output: string;
    score: number;
    status: string;
    scoring_detail: Record<string, any> | null;
  }[];
}

export interface RegressionCase {
  golden_case_id: string;
  category_tag?: string | null;
  status_transition: string;
  baseline_score?: number | null;
  new_score: number;
}

export interface RegressionVerdict {
  evaluation_run_id: string;
  baseline_run_id: string;
  total_cases: number;
  regressed_cases: number;
  newly_passing_cases: number;
  stable_cases: number;
  critical_regressions: number;
  cases: RegressionCase[];
  verdict: "PASS" | "WARN" | "FAIL";
  verdict_reason: string;
  score_changed_cases: number;
  flaky_cases: { golden_case_id: string; category_tag?: string | null; observed_statuses: string[]; note: string }[];
}

export const evaluations = {
  createRun: (
    projectId: string,
    payload: {
      golden_dataset_id: string;
      provider: string;
      scoring_strategy: ScoringStrategy;
      scoring_params?: Record<string, any>;
      actual_outputs?: Record<string, string>;
    }
  ) =>
    request<EvaluationRunFull>(`/projects/${projectId}/evaluations/runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listRuns: (projectId: string, goldenDatasetId?: string) =>
    request<EvaluationRunSummary[]>(
      `/projects/${projectId}/evaluations/runs` +
      (goldenDatasetId ? `?golden_dataset_id=${goldenDatasetId}` : "")
    ),

  getRun: (projectId: string, runId: string) =>
    request<EvaluationRunFull>(`/projects/${projectId}/evaluations/runs/${runId}`),

  getRegressionReport: (projectId: string, runId: string) =>
    request<RegressionVerdict>(`/projects/${projectId}/evaluations/runs/${runId}/regression-report`),

  setBaselineViaGolden: (projectId: string, gid: string, runId: string) =>
    request<GoldenDatasetResponse>(
      `/projects/${projectId}/datasets/golden-datasets/${gid}/baseline`,
      { method: "POST", body: JSON.stringify({ run_id: runId }) }
    ),
};

// ── Reports API (Phase 15) ─────────────────────────────────────────────────

export interface ProjectReport {
  project_id: string;
  generated_at: string;
  summary: {
    datasets: number;
    experiments: number;
    golden_datasets: number;
    evaluation_runs: number;
    data_quality_totals: { critical: number; warning: number; info: number };
  };
  datasets: {
    dataset_id: string;
    name: string;
    format: string;
    versions: number;
    profile_status?: string | null;
    latest_version?: string;
    num_rows?: number;
    num_columns?: number;
    duplicate_rows?: number;
    quality?: { critical: number; warning: number; info: number };
  }[];
  ml_results: {
    experiment_id: string;
    target_column: string;
    problem_type: string;
    primary_metric: string;
    status: string;
    trials_completed: number;
    best_model: { algorithm: string; score: number | null } | null;
  }[];
  ai_evaluation: {
    golden_dataset_id: string;
    name: string;
    version: number;
    case_count: number;
    baseline_designated: boolean;
    total_runs: number;
    latest_run: {
      run_id: string;
      status: string;
      scoring_strategy: string | null;
      pass_rate: number | null;
      critical_failures: number | null;
    } | null;
  }[];
}

export const reports = {
  getProjectReport: (projectId: string) =>
    request<ProjectReport>(`/projects/${projectId}/report`),
};

// ── AI Recommendation Engine API ───────────────────────────────────────────

export interface PlanStep {
  order: number;
  action: string;
  column: string | null;
  params: Record<string, any>;
  problem: string;
  rationale: string;
  expected_effect: string;
  alternatives: string[];
  confidence: "high" | "medium" | "low";
}

export interface RecommendationResponse {
  steps: PlanStep[];
  notes: string[];
  stats_summary: { total_steps: number; columns_affected: number; target_column_hint?: string };
  narrative: string;
  generated_by: "rules" | "rules+llm";
  requires_approval: boolean;
}

export const recommendations = {
  getPlan: (projectId: string, datasetId: string, versionId: string) =>
    request<RecommendationResponse>(
      `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/recommendations`
    ),
};

export const automl = {
  createExperiment: (projectId: string, datasetId: string, payload: ExperimentCreate) =>
    request<ExperimentResponse>(`/projects/${projectId}/datasets/${datasetId}/automl/experiments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getExperiment: (projectId: string, experimentId: string) =>
    request<ExperimentResponse>(`/projects/${projectId}/automl/experiments/${experimentId}`),
    
  listExperiments: (projectId: string) =>
    request<ExperimentResponse[]>(`/projects/${projectId}/automl/experiments`),
};

// ── Explainability API ─────────────────────────────────────────────────────

export interface ShapGlobalResponse {
  summary_plot_base64: string;
  feature_importances: Record<string, number>;
  insight: string;
}

export interface ShapLocalResponse {
  force_plot_base64: string;
  row_values: Record<string, any>;
  shap_values: Record<string, number>;
  base_value: number;
  prediction: number;
}

export const explainability = {
  getGlobalExplanation: (projectId: string, trialId: string) =>
    request<ShapGlobalResponse>(`/projects/${projectId}/automl/trials/${trialId}/explain/global`),

  getLocalExplanation: (projectId: string, trialId: string, rowIndex: number) =>
    request<ShapLocalResponse>(`/projects/${projectId}/automl/trials/${trialId}/explain/local?row_index=${rowIndex}`),
};

// ── Desktop System & Diagnostics API ────────────────────────────────────────

export interface SystemStorageInfo {
  data_dir: string;
  storage_dir: string;
  disk_total_gb: number;
  disk_free_gb: number;
  disk_used_percent: number;
  db_size_mb: number;
  datasets_size_mb: number;
  models_size_mb: number;
  cache_size_mb: number;
  total_storage_used_mb: number;
}

export interface SystemHardwareInfo {
  cpu_cores: number;
  total_ram_gb: number;
  available_ram_gb: number;
}

export interface SystemInfoResponse {
  app_name: string;
  app_version: string;
  edition: string;
  backend_port: number;
  environment: {
    os: string;
    arch: string;
    python_version: string;
  };
  hardware: SystemHardwareInfo;
  storage: SystemStorageInfo;
  ml_libraries: Record<string, string>;
}

export interface DesktopSettings {
  max_training_threads: number;
  performance_mode: "balanced" | "max";
  theme: "dark" | "light" | "system";
  auto_cleanup_cache: boolean;
  launch_on_startup: boolean;
}

export const desktopSystem = {
  getInfo: () => request<SystemInfoResponse>("/system/info"),
  getSettings: () => request<DesktopSettings>("/system/settings"),
  updateSettings: (payload: DesktopSettings) =>
    request<{ status: string; settings: DesktopSettings }>("/system/settings", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  openStorage: () =>
    request<{ status: string; path: string }>("/system/open-storage", {
      method: "POST",
    }),
  clearCache: () =>
    request<{ status: string; freed_bytes: number; freed_mb: number; message: string }>("/system/clear-cache", {
      method: "POST",
    }),
  changePassword: (payload: { current_password?: string; new_password: string }) =>
    request<{ status: string; message: string }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

