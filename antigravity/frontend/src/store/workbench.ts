import { create } from "zustand";
import {
  api,
  STAGE_ORDER,
  type PatientSummary,
  type PatientDetail,
  type SettingsPayload,
  type LogEntry,
  type StageKey,
  type WSMessage,
  type ProjectSummary,
  type DataSourceType,
} from "../api/client";

// Note: WebSocket connection is now managed by useWebSocket hook in Workbench.tsx

interface RunningTask {
  taskId: string;
  patientId: string;
  stage: string;
  current: number;
  total: number;
  message: string;
}

interface WorkbenchState {
  // 项目
  projects: ProjectSummary[];
  currentProjectId: string | null;

  // 数据
  patients: PatientSummary[];
  selectedIds: string[];
  currentPatientId: string | null;
  currentStage: StageKey;

  // 阶段详情缓存
  patientDetail: PatientDetail | null;
  stageData: Record<string, any>;
  loadingStage: boolean;

  // 运行状态
  runningTasks: Record<string, RunningTask>;
  logs: LogEntry[];
  toasts: { id: string; type: string; message: string }[];

  // 设置
  settings: SettingsPayload | null;

  // UI
  sidebarCollapsed: boolean;
  panelCollapsed: boolean;

  // Actions
  init: () => void;
  loadProjects: () => Promise<void>;
  createProject: (name: string, sourceType: DataSourceType) => Promise<void>;
  selectProject: (id: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  renameProject: (id: string, name: string) => Promise<void>;
  loadPatients: () => Promise<void>;
  importPatients: (path: string) => Promise<void>;
  importText: (path: string) => Promise<void>;
  importExcel: (path: string, textColumns?: string) => Promise<void>;
  deletePatient: (id: string) => Promise<void>;
  renamePatient: (id: string, name: string) => Promise<void>;
  selectPatient: (id: string, multi: boolean) => void;
  setStage: (stage: StageKey) => void;
  loadPatientDetail: (patientId: string) => Promise<void>;
  loadStageData: (patientId: string, stage: string) => Promise<void>;
  runStage: (patientId: string, stage: string, rerun?: boolean) => Promise<void>;
  runBatch: (patientIds: string[], stage: string, rerun?: boolean) => Promise<void>;
  stopTask: (taskId: string) => Promise<void>;
  editOcrPage: (patientId: string, pageName: string, text: string) => Promise<void>;
  editMergeText: (patientId: string, text: string) => Promise<void>;
  editExtractFields: (patientId: string, fields: Record<string, any>) => Promise<void>;
  rerunOcrPage: (patientId: string, pageName: string) => Promise<void>;
  exportExcel: (patientIds: string[], outputPath: string) => Promise<void>;
  updateReview: (patientId: string, reviewedFields: Record<string, any>, allReviewed: boolean) => Promise<void>;
  loadSettings: () => Promise<void>;
  addToast: (type: string, message: string) => void;
  removeToast: (id: string) => void;
  toggleSidebar: () => void;
  togglePanel: () => void;
  onWSMessage: (msg: WSMessage) => void;
  refreshAll: () => void;
}

let toastId = 0;

export const useWorkbench = create<WorkbenchState>((set, get) => ({
  projects: [],
  currentProjectId: null,
  patients: [],
  selectedIds: [],
  currentPatientId: null,
  currentStage: "source",
  patientDetail: null,
  stageData: {},
  loadingStage: false,
  runningTasks: {},
  logs: [],
  toasts: [],
  settings: null,
  sidebarCollapsed: false,
  panelCollapsed: false,

  init: () => {
    get().loadProjects();
    get().loadSettings();
  },

  loadProjects: async () => {
    try {
      const list = await api.listProjects();
      set({ projects: list });
      const savedProjectId = localStorage.getItem("medora:currentProject");
      const targetId = savedProjectId && list.find((p) => p.id === savedProjectId)
        ? savedProjectId
        : list.length > 0 ? list[0].id : null;
      if (targetId && !get().currentProjectId) {
        get().selectProject(targetId);
      }
    } catch (e: any) {
      get().addToast("error", e.message || "加载项目失败");
    }
  },

  createProject: async (name: string, sourceType: DataSourceType) => {
    try {
      const project = await api.createProject(name, sourceType);
      set((s) => ({ projects: [...s.projects, project] }));
      get().addToast("success", `项目「${name}」已创建`);
      await get().selectProject(project.id);
    } catch (e: any) {
      get().addToast("error", e.message || "创建项目失败");
    }
  },

  selectProject: async (id: string) => {
    set({ currentProjectId: id, patients: [], selectedIds: [], currentPatientId: null, patientDetail: null });
    localStorage.setItem("medora:currentProject", id);
    try {
      const patients = await api.listProjectPatients(id);
      set({ patients });
    } catch (e: any) {
      get().addToast("error", e.message || "加载病人失败");
    }
  },

  deleteProject: async (id: string) => {
    try {
      await api.deleteProject(id);
      set((s) => ({
        projects: s.projects.filter((p) => p.id !== id),
        currentProjectId: s.currentProjectId === id ? null : s.currentProjectId,
        patients: s.currentProjectId === id ? [] : s.patients,
        selectedIds: s.currentProjectId === id ? [] : s.selectedIds,
        currentPatientId: s.currentProjectId === id ? null : s.currentPatientId,
        patientDetail: s.currentProjectId === id ? null : s.patientDetail,
      }));
      if (localStorage.getItem("medora:currentProject") === id) {
        localStorage.removeItem("medora:currentProject");
      }
      get().addToast("success", "项目已删除");
    } catch (e: any) {
      get().addToast("error", e.message || "删除项目失败");
    }
  },

  renameProject: async (id: string, name: string) => {
    try {
      const updated = await api.renameProject(id, name);
      set((s) => ({ projects: s.projects.map((p) => (p.id === id ? { ...p, ...updated } : p)) }));
      get().addToast("success", "项目已重命名");
    } catch (e: any) {
      get().addToast("error", e.message || "重命名失败");
    }
  },

  loadPatients: async () => {
    const pid = get().currentProjectId;
    if (!pid) return;
    try {
      const list = await api.listProjectPatients(pid);
      set({ patients: list });
    } catch (e: any) {
      get().addToast("error", e.message || "刷新病人列表失败");
    }
  },

  importPatients: async (path: string) => {
    const pid = get().currentProjectId;
    if (!pid) { get().addToast("error", "请先选择项目"); return; }
    try {
      const added = await api.importFolder(pid, path);
      set((s) => {
        const existingIds = new Set(s.patients.map((p) => p.id));
        return { patients: [...s.patients, ...added.filter((p) => !existingIds.has(p.id))] };
      });
      get().addToast("success", `已导入 ${added.length} 位病人`);
    } catch (e: any) {
      get().addToast("error", e.message || "导入失败");
    }
  },

  importText: async (path: string) => {
    const pid = get().currentProjectId;
    if (!pid) { get().addToast("error", "请先选择项目"); return; }
    try {
      const added = await api.importText(pid, path);
      set((s) => {
        const existingIds = new Set(s.patients.map((p) => p.id));
        return { patients: [...s.patients, ...added.filter((p) => !existingIds.has(p.id))] };
      });
      get().addToast("success", `已导入 ${added.length} 个文本文件`);
    } catch (e: any) {
      get().addToast("error", e.message || "导入失败");
    }
  },

  importExcel: async (path: string, textColumns?: string) => {
    const pid = get().currentProjectId;
    if (!pid) { get().addToast("error", "请先选择项目"); return; }
    try {
      const added = await api.importExcel(pid, path, textColumns || "");
      set((s) => {
        const existingIds = new Set(s.patients.map((p) => p.id));
        return { patients: [...s.patients, ...added.filter((p) => !existingIds.has(p.id))] };
      });
      get().addToast("success", `已从 Excel 拆分 ${added.length} 位病人`);
    } catch (e: any) {
      get().addToast("error", e.message || "导入失败");
    }
  },

  deletePatient: async (id: string) => {
    try {
      await api.deletePatient(id);
      set((s) => ({
        patients: s.patients.filter((p) => p.id !== id),
        selectedIds: s.selectedIds.filter((x) => x !== id),
        currentPatientId: s.currentPatientId === id ? null : s.currentPatientId,
        patientDetail: s.currentPatientId === id ? null : s.patientDetail,
      }));
      get().addToast("success", "病人已删除");
    } catch (e: any) {
      get().addToast("error", e.message || "删除失败");
    }
  },

  renamePatient: async (id: string, name: string) => {
    try {
      const updated = await api.renamePatient(id, name);
      set((s) => ({
        patients: s.patients.map((p) => (p.id === id ? { ...p, ...updated } : p)),
        patientDetail:
          s.patientDetail?.id === id ? { ...s.patientDetail, name: updated.name } : s.patientDetail,
      }));
      get().addToast("success", "已重命名");
    } catch (e: any) {
      get().addToast("error", e.message || "重命名失败");
    }
  },

  selectPatient: (id: string, multi: boolean) => {
    set((s) => {
      if (multi) {
        return {
          selectedIds: s.selectedIds.includes(id)
            ? s.selectedIds.filter((x) => x !== id)
            : [...s.selectedIds, id],
          currentPatientId: id,
        };
      }
      return { selectedIds: [id], currentPatientId: id };
    });
    if (!multi) {
      get().loadPatientDetail(id);
    }
  },

  setStage: (stage: StageKey) => {
    set({ currentStage: stage });
    // 记住上次查看的 stage
    const pid = get().currentPatientId;
    if (pid) {
      localStorage.setItem(`medora:stage:${pid}`, stage);
    }
    if (pid && get().selectedIds.length === 1) {
      get().loadStageData(pid, stage);
    }
  },

  loadPatientDetail: async (patientId: string) => {
    try {
      const detail = await api.getPatient(patientId);
      set({ patientDetail: detail });
      // 恢复上次查看的 stage（不自动跳到活跃阶段，避免刷新回到源图）
      const savedStage = localStorage.getItem(`medora:stage:${patientId}`);
      if (savedStage && STAGE_ORDER.includes(savedStage as StageKey)) {
        set({ currentStage: savedStage as StageKey });
      } else if (!get().currentPatientId) {
        // 首次打开此病人，跳到活跃阶段
        const activeStage = detail.current_stage as StageKey;
        if (STAGE_ORDER.includes(activeStage)) {
          set({ currentStage: activeStage });
        }
      }
      set({ currentPatientId: patientId });
      get().loadStageData(patientId, get().currentStage);
    } catch (e) {
      console.error("loadPatientDetail", e);
    }
  },

  loadStageData: async (patientId: string, stage: string) => {
    if (stage === "source") {
      // source 数据已在 patientDetail 中
      return;
    }
    set({ loadingStage: true });
    try {
      const data = await api.getStage(patientId, stage);
      set((s) => ({
        stageData: { ...s.stageData, [`${patientId}:${stage}`]: data },
        loadingStage: false,
      }));
    } catch (e) {
      console.error("loadStageData", e);
      set({ loadingStage: false });
    }
  },

  runStage: async (patientId: string, stage: string, rerun = false) => {
    try {
      const result = await api.runStage(patientId, stage, rerun);
      if (result.task_id) {
        set((s) => ({
          runningTasks: {
            ...s.runningTasks,
            [patientId]: { taskId: result.task_id, patientId, stage, current: 0, total: 0, message: "启动中…" },
          },
        }));
      }
    } catch (e: any) {
      get().addToast("error", e.message || "执行失败");
    }
  },

  runBatch: async (patientIds: string[], stage: string, rerun = false) => {
    try {
      await api.runBatch(patientIds, stage, rerun);
      get().addToast("info", `开始批量${rerun ? "重新" : ""}执行 ${stage}（${patientIds.length} 人）`);
    } catch (e: any) {
      get().addToast("error", e.message || "批量执行失败");
    }
  },

  stopTask: async (taskId: string) => {
    try {
      await api.stopTask(taskId);
      get().addToast("warning", "已请求停止任务");
    } catch (e: any) {
      get().addToast("error", e.message || "停止失败");
    }
  },

  editOcrPage: async (patientId: string, pageName: string, text: string) => {
    await api.editOcrPage(patientId, pageName, text);
    // 同步内存中的页文本，避免审查模式立刻 reload 闪烁
    const key = `${patientId}:ocr`;
    const stageData = { ...get().stageData };
    const cur = stageData[key];
    if (cur?.pages) {
      stageData[key] = {
        ...cur,
        pages: cur.pages.map((p: any) =>
          p.page === pageName || p.page === `${pageName}_0` || pageName.startsWith(p.page)
            ? { ...p, text, char_count: text.length }
            : p,
        ),
      };
      set({ stageData });
    }
    const detail = get().patientDetail;
    if (detail?.id === patientId && Array.isArray(detail.ocr_pages)) {
      set({
        patientDetail: {
          ...detail,
          ocr_pages: detail.ocr_pages.map((p: any) =>
            p.page === pageName || p.page === `${pageName}_0`
              ? { ...p, text, char_count: text.length }
              : p,
          ),
        },
      });
    }
    get().loadStageData(patientId, "ocr");
  },

  editMergeText: async (patientId: string, text: string) => {
    await api.editMergeText(patientId, text);
    get().loadStageData(patientId, "merge");
    get().addToast("success", "已保存合并文本修改");
  },

  editExtractFields: async (patientId: string, fields: Record<string, any>) => {
    await api.editExtractFields(patientId, fields);
    get().loadStageData(patientId, "extract");
    get().addToast("success", "已保存字段修改");
  },

  rerunOcrPage: async (patientId: string, pageName: string) => {
    try {
      await api.rerunOcrPage(patientId, pageName);
      get().addToast("info", `正在重新识别 ${pageName}…`);
    } catch (e: any) {
      get().addToast("error", e.message || "重新识别失败");
    }
  },

  exportExcel: async (patientIds: string[], outputPath: string) => {
    try {
      const projectId = get().currentProjectId || undefined;
      const result = await api.exportExcel(patientIds, outputPath, projectId);
      get().addToast("success", `已导出 ${result.row_count} 行到 ${result.path}`);
    } catch (e: any) {
      get().addToast("error", e.message || "导出失败");
      throw e;
    }
  },

  updateReview: async (patientId: string, reviewedFields: Record<string, any>, allReviewed: boolean) => {
    try {
      await api.updateReview(patientId, reviewedFields, allReviewed);
      get().loadPatientDetail(patientId);
      if (allReviewed) get().addToast("success", "全部审核完成");
    } catch (e: any) {
      get().addToast("error", e.message || "审核更新失败");
    }
  },

  loadSettings: async () => {
    try {
      const s = await api.getSettings();
      set({ settings: s });
    } catch (e) {
      console.error("loadSettings", e);
    }
  },

  addToast: (type: string, message: string) => {
    const id = `toast-${++toastId}`;
    set((s) => ({ toasts: [...s.toasts, { id, type, message }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, type === "error" ? 5000 : 3500);
  },

  removeToast: (id: string) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
  },

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  togglePanel: () => set((s) => ({ panelCollapsed: !s.panelCollapsed })),

  refreshAll: () => {
    get().loadProjects();
    get().loadSettings();
    const pid = get().currentProjectId;
    if (pid) get().loadPatients();
    const patientId = get().currentPatientId;
    if (patientId) {
      get().loadPatientDetail(patientId);
      get().loadStageData(patientId, get().currentStage);
    }
    // 重连后尝试恢复进行中任务
    api.listActiveTasks().then((r) => {
      if (!r.tasks?.length) return;
      set((s) => {
        const next = { ...s.runningTasks };
        for (const t of r.tasks) {
          if (!t.patient_id) continue;
          next[t.patient_id] = {
            taskId: t.task_id,
            patientId: t.patient_id,
            stage: next[t.patient_id]?.stage || "",
            current: next[t.patient_id]?.current || 0,
            total: next[t.patient_id]?.total || 0,
            message: t.stopped ? "停止中…" : (next[t.patient_id]?.message || "运行中…"),
          };
        }
        return { runningTasks: next };
      });
    }).catch(() => {});
  },

  onWSMessage: (msg: WSMessage) => {
    const state = get();
    switch (msg.type) {
      case "stage_started": {
        set((s) => ({
          runningTasks: {
            ...s.runningTasks,
            [msg.patient_id]: {
              taskId: msg.task_id || s.runningTasks[msg.patient_id]?.taskId || "",
              patientId: msg.patient_id,
              stage: msg.stage,
              current: 0,
              total: 0,
              message: "启动中…",
            },
          },
        }));
        break;
      }
      case "stage_progress": {
        set((s) => ({
          runningTasks: {
            ...s.runningTasks,
            [msg.patient_id]: {
              taskId: s.runningTasks[msg.patient_id]?.taskId || "",
              patientId: msg.patient_id,
              stage: msg.stage,
              current: msg.current,
              total: msg.total,
              message: msg.message,
            },
          },
          // 侧栏进度同步
          patients: s.patients.map((p) =>
            p.id === msg.patient_id
              ? {
                  ...p,
                  stage_progress: {
                    current: msg.current,
                    total: msg.total,
                    message: msg.message,
                  },
                }
              : p
          ),
        }));
        break;
      }
      case "ocr_page_done": {
        // 增量插入/更新 OCR 页卡片
        set((s) => {
          const key = `${msg.patient_id}:ocr`;
          const prev = s.stageData[key] || {};
          const pages: any[] = Array.isArray(prev.pages) ? [...prev.pages] : [];
          const idx = pages.findIndex((pg) => pg.page === msg.page.page);
          const pageEntry = {
            page: msg.page.page,
            text: msg.page.text,
            char_count: msg.page.char_count,
            md_path: msg.page.md_path,
            status: "done",
          };
          if (idx >= 0) pages[idx] = pageEntry;
          else pages.push(pageEntry);

          const nextStageData = {
            ...s.stageData,
            [key]: { ...prev, pages, status: "running" },
          };

          // 若正在查看该病人，同步 patientDetail.ocr_pages
          let patientDetail = s.patientDetail;
          if (patientDetail && patientDetail.id === msg.patient_id) {
            const detailPages = Array.isArray(patientDetail.ocr_pages)
              ? [...patientDetail.ocr_pages]
              : [];
            const di = detailPages.findIndex((pg) => pg.page === msg.page.page);
            if (di >= 0) detailPages[di] = pageEntry;
            else detailPages.push(pageEntry);
            patientDetail = { ...patientDetail, ocr_pages: detailPages };
          }

          return {
            stageData: nextStageData,
            patientDetail,
            runningTasks: {
              ...s.runningTasks,
              [msg.patient_id]: {
                taskId: s.runningTasks[msg.patient_id]?.taskId || "",
                patientId: msg.patient_id,
                stage: "ocr",
                current: msg.current,
                total: msg.total,
                message: `✓ ${msg.page.page}（${msg.page.char_count} 字）`,
              },
            },
            patients: s.patients.map((p) =>
              p.id === msg.patient_id
                ? {
                    ...p,
                    status: "running" as const,
                    stage_progress: {
                      current: msg.current,
                      total: msg.total,
                      message: `OCR ${msg.current}/${msg.total}`,
                    },
                  }
                : p
            ),
          };
        });
        break;
      }
      case "ocr_page_error": {
        set((s) => ({
          runningTasks: {
            ...s.runningTasks,
            [msg.patient_id]: {
              taskId: s.runningTasks[msg.patient_id]?.taskId || "",
              patientId: msg.patient_id,
              stage: "ocr",
              current: msg.current,
              total: msg.total,
              message: `× ${msg.page_name}: ${msg.error}`,
            },
          },
          logs: [
            ...s.logs.slice(-199),
            {
              timestamp: new Date().toISOString(),
              stage: "ocr",
              level: "error" as const,
              message: `${msg.page_name}: ${msg.error}`,
              patient_id: msg.patient_id,
            },
          ],
        }));
        break;
      }
      case "stage_done": {
        set((s) => {
          const tasks = { ...s.runningTasks };
          // 流水线多阶段时不立刻删 running（pipeline 还会继续）
          // 仅当不是 pipeline 任务时清理；简单策略：status done/error 都更新，running 留给 pipeline 事件
          if (!s.runningTasks[msg.patient_id]?.message?.includes("流水线")) {
            delete tasks[msg.patient_id];
          }
          return { runningTasks: tasks };
        });
        if (msg.status === "done") {
          // OCR 每页已 toast 过，整阶段完成再提示一次
          if (msg.stage !== "ocr" || !msg.message.includes("OCR")) {
            state.addToast("success", msg.message);
          } else {
            state.addToast("success", msg.message);
          }
        } else if (msg.status === "error") {
          state.addToast("error", msg.message);
        }
        // 重新加载阶段数据（OCR 增量已有，仍刷新确保一致）
        if (state.currentPatientId === msg.patient_id) {
          state.loadStageData(msg.patient_id, msg.stage);
          if (msg.stage !== "ocr") {
            state.loadPatientDetail(msg.patient_id);
          }
        }
        state.loadPatients();
        break;
      }
      case "patient_update": {
        set((s) => ({
          patients: s.patients.map((p) => (p.id === msg.patient.id ? { ...p, ...msg.patient } : p)),
        }));
        break;
      }
      case "pipeline_started": {
        state.addToast(
          "info",
          `批量流水线启动：${msg.patient_ids.length} 人 · ${msg.stages.join("→")}`,
        );
        break;
      }
      case "pipeline_done": {
        const sum = msg.summary as {
          done_patients?: number;
          error_patients?: number;
          total_patients?: number;
          stopped?: boolean;
        };
        state.addToast(
          sum.error_patients ? "warning" : "success",
          sum.stopped
            ? `流水线已停止：成功 ${sum.done_patients ?? 0}，失败 ${sum.error_patients ?? 0}`
            : `流水线完成：成功 ${sum.done_patients ?? 0}/${sum.total_patients ?? 0}，失败 ${sum.error_patients ?? 0}`,
        );
        state.loadPatients();
        if (state.currentPatientId) {
          state.loadPatientDetail(state.currentPatientId);
        }
        break;
      }
      case "task_done": {
        const summary = msg.summary as { done?: number; error?: number };
        if (summary && (summary.done !== undefined || summary.error !== undefined)) {
          state.addToast("info", `任务完成：成功 ${summary.done ?? 0}，失败 ${summary.error ?? 0}`);
        }
        state.loadPatients();
        break;
      }
      case "log": {
        const entry: LogEntry = {
          timestamp: msg.timestamp || new Date().toISOString(),
          stage: msg.stage,
          level: msg.level as any,
          message: msg.message,
          patient_id: msg.patient_id,
        };
        set((s) => ({ logs: [...s.logs.slice(-199), entry] }));
        break;
      }
    }
  },
}));
