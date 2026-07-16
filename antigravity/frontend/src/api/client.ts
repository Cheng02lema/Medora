// Medora API 客户端 + WebSocket

const BASE_URL = "http://127.0.0.1:8765";

// ============ 类型 ============

export type StageKey =
  | "source" | "preprocess" | "slice" | "ocr"
  | "merge" | "extract" | "review" | "export";

export type PatientStatus =
  | "pending" | "running" | "done" | "error" | "stale" | "review_pending";

export type StageStatus =
  | "pending" | "running" | "done" | "error" | "skipped" | "stale";

export type DataSourceType = "image" | "excel" | "text";

// ============ 项目 ============

export interface ProjectSummary {
  id: string;
  name: string;
  source_type: DataSourceType;
  patient_count: number;
  created_at: string;
  has_template: boolean;
  has_prompt: boolean;
  ocr_token_configured: boolean;
  llm_api_key_configured: boolean;
  llm_provider?: string;
  llm_model?: string;
}

export interface ProjectConfig {
  ocr_use_global: boolean;
  llm_use_global: boolean;
  ocr_override: Record<string, any>;
  llm_override: Record<string, any>;
  global_ocr: {
    url: string; model: string; preset: string;
    custom_params: Record<string, any>;
    token_configured: boolean;
  };
  global_llm: {
    provider: string; model: string; base_url: string;
    temperature: number; max_tokens: number;
    api_key_configured: boolean;
  };
  /** effective 合并结果，用于展示/运行 */
  ocr: {
    url: string; model: string; preset: string;
    custom_params: Record<string, any>;
    token_configured: boolean;
    use_global?: boolean;
  };
  llm: {
    provider: string; model: string; base_url: string;
    temperature: number; max_tokens: number;
    api_key_configured: boolean;
    use_global?: boolean;
  };
  preprocess: {
    contrast: number; sharpness: number; brightness: number;
    denoise: boolean; binarize: boolean; binarize_threshold: number;
    mask_regions: any[];
  };
  slice_regions: any[];
  pipeline: {
    extraction_template: string;
    output_excel: string;
    make_docx: boolean;
  };
}

export interface ProjectDetail extends ProjectSummary {
  workspace: string;
  ocr_config: Record<string, any>;
  llm_config: Record<string, any>;
  preprocess_config: Record<string, any>;
  slice_regions: any[];
  make_docx: boolean;
  extraction_template: string;
  output_excel: string;
  prompt_global: string;
  prompt_fields: Record<string, any>;
  prompt_engineered_md: string;
  patients: PatientSummary[];
}

export interface PatientSummary {
  id: string;
  name: string;
  status: PatientStatus;
  current_stage: string;
  stage_progress: { current: number; total: number; message: string } | null;
  error: string;
  image_count: number;
}

export interface StageState {
  status: StageStatus;
  started_at: string;
  finished_at: string;
  error: string;
  data: Record<string, any>;
}

export interface PatientDetail {
  id: string;
  name: string;
  source_dir: string;
  work_dir: string;
  status: PatientStatus;
  current_stage: string;
  stages: Record<string, StageState>;
  images: { name: string; path: string; size: number }[];
  ocr_pages: { page: string; text: string; char_count: number; md_path: string }[];
  merged_text: string | null;
  extracted_fields: { fields: Record<string, any>; _source: string; _status: string } | null;
  artifacts: string[];
}

export interface OcrParamSchema {
  key: string;
  label: string;
  type: "bool" | "list" | "enum" | string;
  default: any;
  description: string;
  group?: string;
  options?: string[];
}

export interface OcrPresetItem {
  key: string;
  label: string;
  description: string;
  builtin: boolean;
  params: Record<string, any>;
}

export interface SettingsPayload {
  ocr: {
    url: string;
    model: string;
    preset: string;
    custom_params: Record<string, any>;
    user_presets: { key: string; label: string; description: string; params: Record<string, any> }[];
    token_configured: boolean;
  };
  extract_llm: {
    provider: string; model: string; base_url: string;
    api_key_configured: boolean; temperature: number; max_tokens: number;
  };
  agent_llm?: {
    provider: string; model: string; base_url: string;
    api_key_configured: boolean; temperature: number; max_tokens: number;
  };
  pipeline: {
    extraction_template: string;
    output_excel: string;
    make_docx: boolean;
  };
}

export interface LogEntry {
  timestamp: string;
  stage: string;
  level: "info" | "warn" | "error";
  message: string;
  patient_id?: string;
}

export type WSMessage =
  | { type: "stage_started"; patient_id: string; stage: string; task_id?: string }
  | { type: "stage_progress"; patient_id: string; stage: string; current: number; total: number; message: string }
  | { type: "stage_done"; patient_id: string; stage: string; status: string; message: string }
  | { type: "patient_update"; patient: PatientSummary }
  | { type: "task_done"; task_id: string; summary: Record<string, unknown> }
  | { type: "log"; patient_id: string; stage: string; level: string; message: string; timestamp: string | null }
  | {
      type: "ocr_page_done";
      patient_id: string;
      page: { page: string; text: string; char_count: number; md_path: string; status?: string };
      current: number;
      total: number;
    }
  | {
      type: "ocr_page_error";
      patient_id: string;
      page_name: string;
      error: string;
      current: number;
      total: number;
    }
  | {
      type: "pipeline_started";
      project_id: string;
      task_id: string;
      patient_ids: string[];
      stages: string[];
    }
  | {
      type: "pipeline_done";
      project_id: string;
      task_id: string;
      summary: Record<string, unknown>;
    };

// ============ fetch 封装 ============

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败：${resp.status}`);
  }
  return resp.json();
}

// ============ API ============

export const api = {
  // ─── 项目 ───
  listProjects: () => request<ProjectSummary[]>("/projects"),
  createProject: (name: string, sourceType: DataSourceType = "image") =>
    request<ProjectSummary>("/projects", { method: "POST", body: JSON.stringify({ name, source_type: sourceType }) }),
  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  deleteProject: (id: string) => request<{ ok: boolean }>(`/projects/${id}`, { method: "DELETE" }),
  renameProject: (id: string, name: string) =>
    request<ProjectSummary>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  getProjectConfig: (id: string) => request<ProjectConfig>(`/projects/${id}/config`),
  updateProjectOCR: (id: string, body: {
    use_global?: boolean;
    url?: string;
    model?: string;
    preset?: string;
    custom_params?: Record<string, any>;
  }) =>
    request(`/projects/${id}/config/ocr`, { method: "PUT", body: JSON.stringify(body) }),
  updateProjectLLM: (id: string, body: {
    use_global?: boolean;
    provider?: string;
    model?: string;
    base_url?: string;
    temperature?: number;
    max_tokens?: number;
  }) =>
    request(`/projects/${id}/config/llm`, { method: "PUT", body: JSON.stringify(body) }),
  updateProjectPreprocess: (id: string, body: any) =>
    request(`/projects/${id}/config/preprocess`, { method: "PUT", body: JSON.stringify(body) }),
  updateProjectPipeline: (id: string, body: any) =>
    request(`/projects/${id}/config/pipeline`, { method: "PUT", body: JSON.stringify(body) }),
  updateProjectSliceRegions: (id: string, regions: any[]) =>
    request(`/projects/${id}/config/slice-regions`, { method: "PUT", body: JSON.stringify({ regions }) }),
  listProjectPatients: (id: string) => request<PatientSummary[]>(`/projects/${id}/patients`),
  importFolder: (projectId: string, path: string) =>
    request<PatientSummary[]>(`/projects/${projectId}/patients/import-folder`, {
      method: "POST", body: JSON.stringify({ path }),
    }),
  importText: (projectId: string, path: string) =>
    request<PatientSummary[]>(`/projects/${projectId}/patients/import-text`, {
      method: "POST", body: JSON.stringify({ path }),
    }),
  importExcel: (projectId: string, path: string, textColumns: string = "") =>
    request<PatientSummary[]>(`/projects/${projectId}/patients/import-excel`, {
      method: "POST", body: JSON.stringify({ path, text_columns: textColumns }),
    }),

  // ─── 项目批量流水线 ───
  runProjectPipeline: (
    projectId: string,
    body: {
      patient_ids?: string[] | null;
      stages: string[];
      fail_policy?: "continue" | "stop";
      only_pending?: boolean;
      rerun?: boolean;
    },
  ) =>
    request<{ task_id: string; patient_count: number; stages: string[] }>(
      `/projects/${projectId}/pipeline/run`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  stopProjectPipeline: (projectId: string, taskId: string = "") =>
    request<{ ok: boolean }>(
      `/projects/${projectId}/pipeline/stop?task_id=${encodeURIComponent(taskId)}`,
      { method: "POST" },
    ),
  listPipelineStages: () =>
    request<{ stages: { key: string; label: string }[] }>("/projects/pipeline-meta/stages"),

  // ─── 预处理版本 ───
  listPreprocessVersions: (patientId: string) =>
    request<{ versions: { version: string; file_count: number; path: string }[]; current_backup: string }>(
      `/stages/${patientId}/preprocess/versions`,
    ),
  restorePreprocess: (patientId: string, version: string) =>
    request<{ ok: boolean; version: string; file_count: number }>(
      `/stages/${patientId}/preprocess/restore`,
      { method: "POST", body: JSON.stringify({ version }) },
    ),

  // ─── 提示词工程 ───
  getPrompt: (projectId: string) =>
    request<{ global: string; fields: Record<string, any>; engineered_md_path: string; has_engineered_md: boolean }>(
      `/projects/${projectId}/prompt`,
    ),
  updatePromptGlobal: (projectId: string, globalPrompt: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/prompt/global`, {
      method: "PUT", body: JSON.stringify({ global_prompt: globalPrompt }),
    }),
  updatePromptFields: (projectId: string, fields: Record<string, any>) =>
    request<{ ok: boolean }>(`/projects/${projectId}/prompt/fields`, {
      method: "PUT", body: JSON.stringify({ fields }),
    }),
  generatePrompt: (projectId: string, useLlm: boolean, llmProvider: string = "") =>
    request<{
      ok: boolean;
      field_count: number;
      fields: Record<string, any>;
      categories: string[];
      llm_used?: boolean;
      llm_error?: string;
      message?: string;
    }>(
      `/projects/${projectId}/prompt/generate`,
      { method: "POST", body: JSON.stringify({ use_llm: useLlm, llm_provider: llmProvider }) },
    ),
  renderPromptMd: (projectId: string, title: string = "", version: string = "1.0", description: string = "") =>
    request<{ ok: boolean; path: string; char_count: number }>(
      `/projects/${projectId}/prompt/render`,
      { method: "POST", body: JSON.stringify({ project_title: title, project_version: version, project_description: description }) },
    ),
  getPromptMd: (projectId: string) =>
    request<{ text: string; path: string; exists: boolean }>(`/projects/${projectId}/prompt/md`),
  updatePromptMd: (projectId: string, text: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/prompt/md`, {
      method: "PUT", body: JSON.stringify({ text }),
    }),

  // ─── 病人 ───
  importPatients: (path: string) =>
    request<PatientSummary[]>("/patients/import", { method: "POST", body: JSON.stringify({ path }) }),
  getPatient: (id: string) => request<PatientDetail>(`/patients/${id}`),
  deletePatient: (id: string) => request<{ ok: boolean }>(`/patients/${id}`, { method: "DELETE" }),
  renamePatient: (id: string, name: string) =>
    request<PatientSummary>(`/patients/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),

  // 阶段
  getStage: (patientId: string, stage: string) =>
    request<any>(`/stages/${patientId}/${stage}`),
  runStage: (patientId: string, stage: string, rerun = false) =>
    request<{ task_id: string }>(`/stages/${patientId}/${stage}/run`, {
      method: "POST",
      body: JSON.stringify({ rerun }),
    }),
  runBatch: (patientIds: string[], stage: string, rerun = false) =>
    request<{ task_id: string; patient_count: number }>(`/stages/batch/${stage}/run`, {
      method: "POST",
      body: JSON.stringify({ patient_ids: patientIds, rerun }),
    }),
  stopTask: (taskId: string) =>
    request<{ ok: boolean }>(`/stages/tasks/${taskId}/stop`, { method: "POST" }),
  listActiveTasks: () =>
    request<{ tasks: { task_id: string; patient_id: string; stopped: boolean }[] }>(`/stages/tasks/active`),

  // 阶段产物编辑
  editOcrPage: (patientId: string, pageName: string, text: string) =>
    request<{ ok: boolean }>(`/stages/${patientId}/ocr/page/${pageName}`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  editMergeText: (patientId: string, text: string) =>
    request<{ ok: boolean }>(`/stages/${patientId}/merge/text`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  editExtractFields: (patientId: string, fields: Record<string, any>) =>
    request<{ ok: boolean }>(`/stages/${patientId}/extract/fields`, {
      method: "PUT",
      body: JSON.stringify({ fields }),
    }),
  rerunOcrPage: (patientId: string, pageName: string) =>
    request<{ task_id: string; message: string }>(`/stages/${patientId}/ocr/page/${pageName}/rerun`, {
      method: "POST",
    }),
  searchOcr: (patientId: string, query: string) =>
    request<{ results: { page: string; snippet: string; match_index: number }[]; query: string }>(
      `/stages/${patientId}/ocr/search`,
      { method: "POST", body: JSON.stringify({ query }) },
    ),
  getRawResponse: (patientId: string) =>
    request<{ text: string }>(`/stages/${patientId}/extract/raw-response`),
  getPatientPrompt: (patientId: string) =>
    request<{ text: string }>(`/stages/${patientId}/extract/prompt`),

  // 预处理配置
  getPreprocessConfig: (patientId: string) =>
    request<any>(`/stages/${patientId}/preprocess/config`),
  setPreprocessConfig: (patientId: string, config: any) =>
    request<{ ok: boolean }>(`/stages/${patientId}/preprocess/config`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  getPreprocessCatalog: () =>
    request<{
      presets: { key: string; label: string; description: string; ops: any[] }[];
      ops: { id: string; label: string; group: string; risk: string }[];
      default_preset: string;
    }>(`/stages/preprocess/catalog`),
  previewPreprocess: (patientId: string, body: {
    image_name?: string;
    preset?: string;
    ops?: any[];
    mask_regions?: any[];
    roi_regions?: any[];
  }) =>
    request<{
      image_name: string;
      preview_relative: string;
      ms: number;
      metrics_before: any;
      metrics_after: any;
      compare: any;
      trace: any[];
    }>(`/stages/${patientId}/preprocess/preview`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  benchPreprocess: (patientId: string, body?: {
    image_names?: string[];
    presets?: string[];
    limit?: number;
    mask_regions?: any[];
  }) =>
    request<{
      images: string[];
      presets: string[];
      rows: any[];
      winners: Record<string, { preset: string; score?: number; ms?: number }>;
      bench_dir: string;
    }>(`/stages/${patientId}/preprocess/bench`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  getPreprocessImages: (patientId: string) =>
    request<{ images: any[]; has_preprocessed: boolean }>(`/stages/${patientId}/preprocess/images`),

  // 切片区域
  getSliceRegions: (patientId: string) =>
    request<{ regions: any[] }>(`/stages/${patientId}/slice/regions`),
  setSliceRegions: (patientId: string, regions: any[]) =>
    request<{ ok: boolean }>(`/stages/${patientId}/slice/regions`, {
      method: "PUT",
      body: JSON.stringify({ regions }),
    }),
  getSlicePreview: (patientId: string, imageName: string) =>
    request<{ slices: any[]; has_slices: boolean }>(`/stages/${patientId}/slice/preview/${imageName}`),
  getSliceBaseImage: (patientId: string) =>
    request<{
      stage: "source" | "preprocess";
      images: { name: string; relative: string; stage: string }[];
      count: number;
      hint: string;
    }>(`/stages/${patientId}/slice/base-image`),
  getOcrInputs: (patientId: string) =>
    request<{
      requested_mode: string;
      effective_mode: string;
      image_source_requested?: string;
      image_source_effective?: string;
      image_source_label?: string;
      structure_label?: string;
      count: number;
      message: string;
      warning: string;
      error?: string;
      has_slices: boolean;
      has_preprocess?: boolean;
      has_source?: boolean;
      preprocess_count?: number;
      source_count?: number;
      slice_region_count: number;
      slice_status: string;
      slice_base_stage?: string;
      items: {
        name: string;
        relative: string;
        stage: string;
        page_key: string;
        parent_page: string;
        region_name: string;
        display_label: string;
        image_source?: string;
        slice_base_stage?: string;
      }[];
    }>(`/stages/${patientId}/ocr/inputs`),
  setOcrInputMode: (
    patientId: string,
    mode?: "auto" | "slices" | "full",
    imageSource?: "auto" | "preprocess" | "source",
  ) =>
    request<{
      ok: boolean;
      mode: string;
      image_source?: string;
      effective_mode: string;
      image_source_effective?: string;
      image_source_label?: string;
      count: number;
      message: string;
      warning: string;
      error?: string;
      has_preprocess?: boolean;
      has_source?: boolean;
      has_slices?: boolean;
    }>(`/stages/${patientId}/ocr/input-mode`, {
      method: "PUT",
      body: JSON.stringify({
        ...(mode != null ? { mode } : {}),
        ...(imageSource != null ? { image_source: imageSource } : {}),
      }),
    }),
  getOcrPageLayout: (patientId: string, pageName: string) =>
    request<{
      ok: boolean;
      has_layout: boolean;
      page: string;
      message?: string;
      image: {
        stage?: string;
        relative?: string;
        name?: string;
        width?: number;
        height?: number;
      };
      blocks: {
        id: number;
        label: string;
        text: string;
        bbox: number[];
        polygon?: number[][];
        order?: number | null;
        noise?: boolean;
        empty?: boolean;
      }[];
      stats?: Record<string, number>;
    }>(`/stages/${patientId}/ocr/pages/${encodeURIComponent(pageName)}/layout`),
  hitOcrLayout: (patientId: string, pageName: string, q: string) =>
    request<{ hits: any[]; has_layout: boolean }>(
      `/stages/${patientId}/ocr/pages/${encodeURIComponent(pageName)}/layout/hit?q=${encodeURIComponent(q)}`,
    ),

  updateReview: (patientId: string, reviewedFields: Record<string, any>, allReviewed: boolean) =>
    request<{ ok: boolean }>(`/stages/${patientId}/review`, {
      method: "PUT",
      body: JSON.stringify({ reviewed_fields: reviewedFields, all_reviewed: allReviewed }),
    }),

  // 导出
  exportExcel: (patientIds: string[], outputPath: string, projectId?: string) =>
    request<{ path: string; row_count: number }>(`/export/excel`, {
      method: "POST",
      body: JSON.stringify({
        patient_ids: patientIds,
        output_path: outputPath,
        project_id: projectId || null,
      }),
    }),
  exportPreview: (patientIds?: string[], projectId?: string) => {
    const qs = new URLSearchParams();
    if (patientIds?.length) qs.set("patient_ids", patientIds.join(","));
    if (projectId) qs.set("project_id", projectId);
    const q = qs.toString();
    return request<any[]>(`/export/preview${q ? `?${q}` : ""}`);
  },

  // 设置
  getSettings: () => request<SettingsPayload>("/settings"),
  getOcrPresets: () =>
    request<{ presets: OcrPresetItem[]; models: { id: string; label: string }[] }>("/settings/ocr/presets"),
  getOcrParamSchema: () =>
    request<{ params: OcrParamSchema[]; defaults: Record<string, any> }>("/settings/ocr/params"),
  getPresetDetails: (presetKey: string) =>
    request<{ key: string; payload: Record<string, any> }>(`/settings/ocr/preset/${presetKey}`),
  createOcrPreset: (body: { key?: string; label: string; description?: string; params: Record<string, any> }) =>
    request<{ ok: boolean; preset: OcrPresetItem }>("/settings/ocr/presets", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateOcrPreset: (key: string, body: { label: string; description?: string; params: Record<string, any> }) =>
    request<{ ok: boolean; preset: OcrPresetItem }>(`/settings/ocr/presets/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteOcrPreset: (key: string) =>
    request<{ ok: boolean }>(`/settings/ocr/presets/${encodeURIComponent(key)}`, { method: "DELETE" }),
  getLlmProviders: () =>
    request<{ name: string; default_url: string }[]>("/settings/extract_llm/providers"),
  updateOcr: (body: {
    url?: string;
    model?: string;
    preset?: string;
    custom_params?: Record<string, any>;
    token?: string;
  }) => request("/settings/ocr", { method: "PUT", body: JSON.stringify(body) }),
  testOcr: (body: { url?: string; token?: string; model?: string }) =>
    request<{ ok: boolean; message: string }>("/settings/ocr/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateExtractLLM: (body: {
    provider?: string; model?: string; base_url?: string;
    api_key?: string; temperature?: number; max_tokens?: number;
  }) =>
    request("/settings/extract_llm", { method: "PUT", body: JSON.stringify(body) }),
  testLLM: (body: { provider?: string; model?: string; base_url?: string; api_key?: string }) =>
    request<{ ok: boolean; message: string }>("/settings/extract_llm/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateAgentLLM: (body: {
    provider?: string; model?: string; base_url?: string;
    api_key?: string; temperature?: number; max_tokens?: number;
  }) =>
    request("/settings/agent_llm", { method: "PUT", body: JSON.stringify(body) }),
  testAgentLLM: (body: { provider?: string; model?: string; base_url?: string; api_key?: string }) =>
    request<{ ok: boolean; message: string }>("/settings/agent_llm/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  copyAgentLLMFromExtract: () =>
    request<{ ok: boolean; message: string }>("/settings/agent_llm/copy-from-extract", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  updatePipeline: (body: { extraction_template?: string; output_excel?: string; make_docx?: boolean }) =>
    request("/settings/pipeline", { method: "PUT", body: JSON.stringify(body) }),

  // 病例归档 Agent
  createOrganizeSession: (body: { work_path: string; out_path?: string; project_id?: string }) =>
    request<{
      session: {
        id: string;
        work_path: string;
        out_path: string;
        project_id: string;
        status: string;
        has_plan: boolean;
        plan_summary: any;
      };
      llm_configured: boolean;
      llm?: { provider: string; model: string; configured: boolean };
      tools: { name: string; description: string }[];
    }>("/agent/organize/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getOrganizeSession: (sessionId: string) =>
    request<{
      session: any;
      messages: { role: string; content: string; ts?: number }[];
      tool_log: any[];
      plan: any;
    }>(`/agent/organize/sessions/${sessionId}`),
  chatOrganize: (
    sessionId: string,
    body: { message: string; confirm_apply?: boolean; extra_prompt?: string },
  ) =>
    request<{
      reply: string;
      tools: any[];
      session: any;
      mode?: string;
    }>(`/agent/organize/sessions/${sessionId}/chat`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getOrganizeTree: (sessionId: string, which: "work" | "out" = "out") =>
    request<{ tree: { path: string; tree: string }; validate: any }>(
      `/agent/organize/sessions/${sessionId}/tree?which=${which}`,
    ),
  importOrganizeSession: (sessionId: string, projectId: string) =>
    request<{ ok: boolean; imported: number; message: string; patients: any[] }>(
      `/agent/organize/sessions/${sessionId}/import`,
      {
        method: "POST",
        body: JSON.stringify({ project_id: projectId }),
      },
    ),
  getOrganizePrompt: () => request<{ text: string; path: string }>("/agent/organize/prompt"),

  // 文件
  imageUrl: (patientId: string, stage: string, filename: string) =>
    `${BASE_URL}/files/image/${patientId}/${stage}/${encodeURIComponent(filename)}`,
  thumbUrl: (patientId: string, stage: string, filename: string) =>
    `${BASE_URL}/files/thumb/${patientId}/${stage}/${encodeURIComponent(filename)}`,
};

// ============ WebSocket ============

export function connectProgressSocket(onMessage: (msg: WSMessage) => void): WebSocket {
  const ws = new WebSocket(`ws://127.0.0.1:8765/ws/progress`);
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      // 忽略无法解析的消息
    }
  };
  return ws;
}

// ============ 常量 ============

export const STAGE_ORDER: StageKey[] = [
  "source", "preprocess", "slice", "ocr", "merge", "extract", "review", "export",
];

export const STAGE_LABELS: Record<StageKey, string> = {
  source: "源图",
  preprocess: "预处理",
  slice: "切片",
  ocr: "OCR",
  merge: "合并",
  extract: "抽取",
  review: "审核",
  export: "导出",
};

export const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  running: "进行中",
  done: "已完成",
  error: "失败",
  stale: "待更新",
  review_pending: "待审核",
};

export const STAGE_STATUS_LABELS: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  done: "已完成",
  error: "失败",
  skipped: "已跳过",
  stale: "待更新",
};
