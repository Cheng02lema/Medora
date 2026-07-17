import { useEffect, useMemo, useState } from "react";
import { useWorkbench } from "../store/workbench";
import { api, STAGE_LABELS, type StageKey } from "../api/client";

const DEFAULT_STAGES = ["preprocess", "ocr", "merge", "extract"];

/**
 * 项目级批量流水线：勾选步骤 + 病人范围 + 实时状态。
 */
export default function ProjectBatchPanel({ onClose }: { onClose?: () => void }) {
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const projects = useWorkbench((s) => s.projects);
  const patients = useWorkbench((s) => s.patients);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const runningTasks = useWorkbench((s) => s.runningTasks);
  const addToast = useWorkbench((s) => s.addToast);
  const loadPatients = useWorkbench((s) => s.loadPatients);

  const [stageOptions, setStageOptions] = useState<{ key: string; label: string }[]>([]);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [scope, setScope] = useState<"all" | "pending" | "selected">("all");
  const [failPolicy, setFailPolicy] = useState<"continue" | "stop">("continue");
  const [rerun, setRerun] = useState(false);
  const [running, setRunning] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [parallelHint, setParallelHint] = useState(1);

  const project = projects.find((p) => p.id === currentProjectId);

  useEffect(() => {
    if (!currentProjectId) return;
    api.getProjectConfig(currentProjectId).then((cfg) => {
      setParallelHint(cfg.effective_max_parallel_patients ?? cfg.global_max_parallel_patients ?? 1);
    }).catch(() => {});
  }, [currentProjectId]);

  useEffect(() => {
    api.listPipelineStages().then((r) => {
      setStageOptions(r.stages);
      const init: Record<string, boolean> = {};
      for (const s of r.stages) {
        init[s.key] = DEFAULT_STAGES.includes(s.key);
      }
      setChecked(init);
    }).catch(() => {
      // 回退
      const fallback = [
        { key: "preprocess", label: "预处理" },
        { key: "slice", label: "切片" },
        { key: "ocr", label: "OCR" },
        { key: "merge", label: "合并" },
        { key: "extract", label: "抽取" },
        { key: "export", label: "导出" },
      ];
      setStageOptions(fallback);
      const init: Record<string, boolean> = {};
      for (const s of fallback) init[s.key] = DEFAULT_STAGES.includes(s.key);
      setChecked(init);
    });
  }, []);

  const targetPatients = useMemo(() => {
    if (scope === "selected") return patients.filter((p) => selectedIds.includes(p.id));
    if (scope === "pending") {
      return patients.filter((p) => ["pending", "error", "stale"].includes(p.status));
    }
    return patients;
  }, [patients, selectedIds, scope]);

  const selectedStages = stageOptions.filter((s) => checked[s.key]).map((s) => s.key);

  const handleStart = async () => {
    if (!currentProjectId) {
      addToast("warning", "请先选择项目");
      return;
    }
    if (selectedStages.length === 0) {
      addToast("warning", "请至少勾选一个步骤");
      return;
    }
    if (targetPatients.length === 0) {
      addToast("warning", "没有可执行的病人");
      return;
    }
    setRunning(true);
    try {
      const result = await api.runProjectPipeline(currentProjectId, {
        patient_ids: scope === "all" ? null : targetPatients.map((p) => p.id),
        stages: selectedStages,
        fail_policy: failPolicy,
        only_pending: scope === "pending",
        rerun,
      });
      setTaskId(result.task_id);
      const n = result.parallel || parallelHint || 1;
      setParallelHint(n);
      addToast(
        "info",
        `已开始 · 同时处理 ${n} 人 · 共 ${result.patient_count} 人 · ${result.stages.map((s) => STAGE_LABELS[s as StageKey] || s).join("→")}`,
      );
    } catch (e: any) {
      addToast("error", e.message || "启动失败");
      setRunning(false);
    }
  };

  const handleStop = async () => {
    if (!currentProjectId) return;
    try {
      const r = await api.stopProjectPipeline(currentProjectId, taskId);
      addToast(
        "warning",
        r.message || "正在停止：已在处理的病人会做完当前阶段",
      );
      setRunning(false);
    } catch (e: any) {
      addToast("error", e.message || "停止失败");
    }
  };

  // 有任务完成时刷新
  useEffect(() => {
    const anyRunning = Object.values(runningTasks).some((t) => t.stage);
    if (!anyRunning && running && taskId) {
      // 可能刚结束
      loadPatients();
    }
  }, [runningTasks]);

  if (!currentProjectId || !project) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📦</div>
        <div className="empty-title">请先选择项目</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div className="h1">批量启动</div>
        <span className="sub">
          {project.name} · 共 {patients.length} 人 · 本次 {targetPatients.length} 人
          · 同时处理 {parallelHint} 人
        </span>
        {onClose && (
          <button className="btn btn-sm" style={{ marginLeft: "auto" }} onClick={onClose}>
            关闭
          </button>
        )}
      </div>

      <Section title="1. 勾选步骤（按顺序执行）">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {stageOptions.map((s) => (
            <label
              key={s.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 12px",
                borderRadius: 10,
                border: `1px solid ${checked[s.key] ? "var(--primary)" : "var(--border)"}`,
                background: checked[s.key] ? "var(--primary-fade)" : "var(--surface-2)",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              <input
                type="checkbox"
                checked={!!checked[s.key]}
                onChange={(e) => setChecked((c) => ({ ...c, [s.key]: e.target.checked }))}
                style={{ width: "auto" }}
              />
              {s.label}
            </label>
          ))}
        </div>
        <div className="faint" style={{ marginTop: 8 }}>
          默认：预处理 → OCR → 合并 → 抽取。文本/Excel 病人会自动跳过图像步骤。
        </div>
      </Section>

      <Section title="2. 病人范围">
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {(
            [
              { key: "all", label: `全部（${patients.length}）` },
              {
                key: "pending",
                label: `仅待处理/失败（${patients.filter((p) => ["pending", "error", "stale"].includes(p.status)).length}）`,
              },
              { key: "selected", label: `仅已选中（${selectedIds.length}）` },
            ] as const
          ).map((opt) => (
            <label key={opt.key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
              <input
                type="radio"
                name="scope"
                checked={scope === opt.key}
                onChange={() => setScope(opt.key)}
                style={{ width: "auto" }}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </Section>

      <Section title="3. 失败策略">
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 10 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
            <input type="radio" checked={failPolicy === "continue"} onChange={() => setFailPolicy("continue")} style={{ width: "auto" }} />
            跳过失败病人，继续下一位
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
            <input type="radio" checked={failPolicy === "stop"} onChange={() => setFailPolicy("stop")} style={{ width: "auto" }} />
            遇失败立即停止整批
          </label>
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={rerun} onChange={(e) => setRerun(e.target.checked)} style={{ width: "auto" }} />
          强制重跑（清除旧产物后执行）
        </label>
      </Section>

      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        <button className="btn btn-primary" onClick={handleStart} disabled={running && !!taskId}>
          ▶ 开始流水线（{targetPatients.length} 人 · {selectedStages.length} 步）
        </button>
        <button className="btn" onClick={handleStop} disabled={!taskId}>
          ⏹ 停止
        </button>
      </div>

      <Section title="实时状态">
        <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
          <table className="batch-table">
            <thead>
              <tr>
                <th>病人</th>
                <th>状态</th>
                <th>进度</th>
                <th>当前</th>
              </tr>
            </thead>
            <tbody>
              {targetPatients.map((p) => {
                const task = runningTasks[p.id];
                return (
                  <tr key={p.id}>
                    <td style={{ fontWeight: 600 }}>{p.name}</td>
                    <td>
                      <span className={`status-dot ${p.status}`} style={{ marginRight: 6 }} />
                      {p.status}
                    </td>
                    <td className="faint">
                      {task
                        ? `${task.current}/${task.total || "?"} · ${task.message}`
                        : p.stage_progress
                        ? `${p.stage_progress.current}/${p.stage_progress.total} · ${p.stage_progress.message}`
                        : "—"}
                    </td>
                    <td className="faint">{task?.stage || p.current_stage || "—"}</td>
                  </tr>
                );
              })}
              {targetPatients.length === 0 && (
                <tr>
                  <td colSpan={4} className="faint" style={{ textAlign: "center", padding: 20 }}>
                    当前范围没有病人
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel" style={{ padding: 16, marginBottom: 14 }}>
      <div className="h2" style={{ marginBottom: 12 }}>{title}</div>
      {children}
    </div>
  );
}
