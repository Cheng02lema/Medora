import { useState, lazy, Suspense, useRef } from "react";
import { useWorkbench } from "../store/workbench";
import { type DataSourceType } from "../api/client";
import PathInput from "./PathInput";

const CaseOrganizePanel = lazy(() => import("./CaseOrganizePanel"));

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  running: "进行中",
  done: "已完成",
  error: "失败",
  stale: "待更新",
  review_pending: "待审核",
};

export default function ProjectSidebar() {
  const projects = useWorkbench((s) => s.projects);
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const selectProject = useWorkbench((s) => s.selectProject);
  const createProject = useWorkbench((s) => s.createProject);
  const deleteProject = useWorkbench((s) => s.deleteProject);
  const renameProject = useWorkbench((s) => s.renameProject);
  const deletePatient = useWorkbench((s) => s.deletePatient);
  const renamePatient = useWorkbench((s) => s.renamePatient);

  const patients = useWorkbench((s) => s.patients);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const selectPatient = useWorkbench((s) => s.selectPatient);
  const sidebarCollapsed = useWorkbench((s) => s.sidebarCollapsed);
  const runningTasks = useWorkbench((s) => s.runningTasks);

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [showNewProject, setShowNewProject] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importMode, setImportMode] = useState<"menu" | "folder" | "organize">("menu");
  const [importing, setImporting] = useState(false);
  const [showOrganize, setShowOrganize] = useState(false);
  const lastClickIdx = useRef<number>(-1);

  const filtered = patients.filter((p) => {
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (filter === "all") return true;
    if (filter === "pending") return p.status === "pending";
    if (filter === "running") return p.status === "running";
    if (filter === "done") return p.status === "done";
    if (filter === "error") return p.status === "error";
    if (filter === "review") return p.status === "review_pending";
    return true;
  });

  const counts = {
    all: patients.length,
    pending: patients.filter((p) => p.status === "pending").length,
    running: patients.filter((p) => p.status === "running").length,
    done: patients.filter((p) => p.status === "done").length,
    error: patients.filter((p) => p.status === "error").length,
    review: patients.filter((p) => p.status === "review_pending").length,
  };

  const currentProject = projects.find((p) => p.id === currentProjectId);
  const sourceType = currentProject?.source_type || "image";

  if (sidebarCollapsed) {
    return (
      <div className="row-list">
        {patients.map((p, i) => (
          <div
            key={p.id}
            className={`row-item ${selectedIds.includes(p.id) ? "selected" : ""}`}
            style={{ gridTemplateColumns: "1fr", justifyItems: "center", padding: "10px 4px" }}
            onClick={(e) => selectPatient(p.id, e.ctrlKey || e.metaKey || e.shiftKey)}
            title={p.name}
          >
            <span className={`status-dot ${p.status}`} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      {/* ─── 项目区 ─── */}
      <div className="hd">
        <span>项目</span>
        <button className="btn btn-sm" onClick={() => setShowNewProject(!showNewProject)}>+</button>
      </div>

      {showNewProject && <NewProjectForm onCreate={createProject} onCancel={() => setShowNewProject(false)} />}

      <div className="row-list" style={{ maxHeight: 160, flex: "0 0 auto" }}>
        {projects.length === 0 && (
          <div className="faint" style={{ padding: 8, textAlign: "center" }}>无项目，点击 + 创建</div>
        )}
        {projects.map((proj, idx) => (
          <div
            key={proj.id}
            className={`row-item ${currentProjectId === proj.id ? "selected" : ""}`}
            onClick={() => selectProject(proj.id)}
            onDoubleClick={(e) => {
              e.stopPropagation();
              const name = prompt("重命名项目", proj.name);
              if (name && name.trim() && name !== proj.name) renameProject(proj.id, name.trim());
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              if (confirm(`删除项目「${proj.name}」？工作区文件将一并删除。`)) deleteProject(proj.id);
            }}
          >
            <span className="row-idx">{String(idx + 1).padStart(2, "0")}</span>
            <div className="patient-info">
              <div className="patient-name">{proj.name}</div>
              <div className="patient-meta">
                {proj.patient_count} · {proj.source_type === "image" ? "图片" : proj.source_type === "excel" ? "Excel" : "文本"}
                {!proj.has_template ? " · 无模板" : ""}
              </div>
            </div>
            <span className={`status-dot ${proj.has_template ? "done" : "pending"}`} />
          </div>
        ))}
      </div>

      <div className="divider" />

      {/* ─── 病人区 ─── */}
      {currentProject ? (
        <>
          <div className="hd">
            <span>病人</span>
            <b>{counts.all}</b>
          </div>
          {selectedIds.length > 1 && (
            <div className="selection-bar">
              <span>已选 {selectedIds.length}</span>
              <span style={{ color: "var(--mute)" }}>⌘ 多选 · Shift 范围</span>
            </div>
          )}

          <div className="sidebar-search">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索病人…" />
          </div>

          <div className="filter-bar">
            {[
              { key: "all", label: `全部 ${counts.all}` },
              { key: "pending", label: `待处理 ${counts.pending}` },
              { key: "running", label: `进行中 ${counts.running}` },
              { key: "review", label: `待审 ${counts.review}` },
              { key: "done", label: `完成 ${counts.done}` },
              { key: "error", label: `失败 ${counts.error}` },
            ].map((f) => (
              <span
                key={f.key}
                className={`filter-chip ${filter === f.key ? "active" : ""}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
              </span>
            ))}
          </div>

          <div className="sidebar-tools">
            <button
              className="btn btn-sm btn-primary"
              style={{ width: "100%" }}
              disabled={importing}
              onClick={() => {
                if (showImport && importMode === "menu") {
                  setShowImport(false);
                } else {
                  setShowImport(true);
                  setImportMode("menu");
                }
              }}
            >
              {importing ? "导入中…" : "+ 导入病人"}
            </button>
          </div>

          {showImport && importMode === "menu" && (
            <div
              style={{
                padding: 10,
                marginBottom: 10,
                borderRadius: "var(--radius-md)",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
              }}
            >
              {(sourceType as DataSourceType) === "image" ? (
                <>
                  <button
                    className="btn btn-sm"
                    style={{ width: "100%", marginBottom: 6, justifyContent: "flex-start" }}
                    onClick={() => setImportMode("folder")}
                  >
                    从文件夹导入
                    <span className="faint" style={{ marginLeft: 6, fontSize: 10 }}>已整理好</span>
                  </button>
                  <button
                    className="btn btn-sm btn-primary"
                    style={{ width: "100%", marginBottom: 6, justifyContent: "flex-start" }}
                    onClick={() => {
                      setShowImport(false);
                      setShowOrganize(true);
                    }}
                  >
                    病例归档导入
                  </button>
                </>
              ) : (
                <button
                  className="btn btn-sm btn-primary"
                  style={{ width: "100%", marginBottom: 6 }}
                  onClick={() => setImportMode("folder")}
                >
                  选择路径导入
                </button>
              )}
              <button className="btn btn-sm" style={{ width: "100%" }} onClick={() => setShowImport(false)}>
                取消
              </button>
            </div>
          )}

          {showImport && importMode === "folder" && (
            <ImportPanel
              sourceType={sourceType as DataSourceType}
              busy={importing}
              onImportFolder={async (path) => {
                setImporting(true);
                try {
                  await useWorkbench.getState().importPatients(path);
                  setShowImport(false);
                  setImportMode("menu");
                } finally {
                  setImporting(false);
                }
              }}
              onImportText={async (path) => {
                setImporting(true);
                try {
                  await useWorkbench.getState().importText(path);
                  setShowImport(false);
                  setImportMode("menu");
                } finally {
                  setImporting(false);
                }
              }}
              onImportExcel={async (path, cols) => {
                setImporting(true);
                try {
                  await useWorkbench.getState().importExcel(path, cols);
                  setShowImport(false);
                  setImportMode("menu");
                } finally {
                  setImporting(false);
                }
              }}
              onCancel={() => {
                setImportMode("menu");
              }}
            />
          )}

          <div className="patient-list">
            {filtered.length === 0 && (
              <div className="empty-state" style={{ padding: 24 }}>
                <div className="empty-icon">·</div>
                <div className="empty-desc" style={{ marginBottom: 12 }}>
                  {patients.length === 0 ? "还没有病人" : "无匹配病人"}
                </div>
                {patients.length === 0 && (sourceType as DataSourceType) === "image" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
                    <button
                      className="btn btn-sm"
                      onClick={() => {
                        setShowImport(true);
                        setImportMode("folder");
                      }}
                    >
                      从文件夹导入
                    </button>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => setShowOrganize(true)}
                    >
                      病例归档
                    </button>
                  </div>
                )}
                {patients.length === 0 && (sourceType as DataSourceType) !== "image" && (
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={() => {
                      setShowImport(true);
                      setImportMode("folder");
                    }}
                  >
                    导入
                  </button>
                )}
              </div>
            )}
            {filtered.map((p, idx) => {
              const task = runningTasks[p.id];
              const progress = task
                ? (task.total > 0 ? (task.current / task.total) * 100 : 0)
                : (p.stage_progress && p.stage_progress.total > 0
                  ? (p.stage_progress.current / p.stage_progress.total) * 100
                  : 0);
              return (
                <div
                  key={p.id}
                  className={`row-item ${selectedIds.includes(p.id) ? "selected" : ""}`}
                  onClick={(e) => {
                    if (e.shiftKey && lastClickIdx.current >= 0) {
                      const a = Math.min(lastClickIdx.current, idx);
                      const b = Math.max(lastClickIdx.current, idx);
                      const range = filtered.slice(a, b + 1).map((x) => x.id);
                      useWorkbench.setState({
                        selectedIds: range,
                        currentPatientId: p.id,
                      });
                    } else {
                      selectPatient(p.id, e.ctrlKey || e.metaKey);
                      lastClickIdx.current = idx;
                    }
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    const name = prompt("重命名病人", p.name);
                    if (name && name.trim() && name !== p.name) renamePatient(p.id, name.trim());
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (confirm(`删除病人「${p.name}」？工作区文件将一并删除。`)) deletePatient(p.id);
                  }}
                >
                  <span className="row-idx">{String(idx + 1).padStart(2, "0")}</span>
                  <div className="patient-info">
                    <div className="patient-name">{p.name}</div>
                    <div className="patient-meta">
                      {p.status === "error" && p.error
                        ? p.error.slice(0, 28)
                        : task
                        ? task.message
                        : p.stage_progress
                        ? `${p.stage_progress.current}/${p.stage_progress.total}`
                        : `${STATUS_LABELS[p.status] || p.status}`}
                    </div>
                  </div>
                  <div className="row-trail">
                    <span className={`status-dot ${p.status}`} />
                    {(progress > 0 || task) && (
                      <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${Math.min(100, progress)}%` }} />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="empty-state" style={{ padding: 30 }}>
          <div className="empty-icon">·</div>
          <div className="empty-title">选择一个项目</div>
          <div className="empty-desc">或点击 + 创建新项目</div>
        </div>
      )}

      {showOrganize && (
        <div className="modal-overlay" onClick={() => setShowOrganize(false)}>
          <div
            className="modal-panel"
            style={{ maxWidth: 920 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <span className="modal-title">病例归档</span>
              <button className="modal-close" onClick={() => setShowOrganize(false)}>×</button>
            </div>
            <div className="modal-body">
              <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
                <CaseOrganizePanel
                  onClose={() => setShowOrganize(false)}
                  onImported={() => setShowOrganize(false)}
                />
              </Suspense>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── 新建项目表单 ───
function NewProjectForm({ onCreate, onCancel }: { onCreate: (name: string, sourceType: DataSourceType) => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<DataSourceType>("image");

  return (
    <div style={{ padding: 10, marginBottom: 10, borderRadius: "var(--radius-md)", background: "var(--surface-2)", border: "1px solid var(--border)", animation: "content-in 200ms ease-out" }}>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="项目名称" autoFocus style={{ marginBottom: 8 }} />
      <select value={sourceType} onChange={(e) => setSourceType(e.target.value as DataSourceType)} style={{ marginBottom: 8 }}>
        <option value="image">图片病历（拍照/截图）</option>
        <option value="excel">Excel 拆分（每行=1病人）</option>
        <option value="text">文本文件（MD/Word/TXT）</option>
      </select>
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn btn-sm btn-primary" style={{ flex: 1 }} disabled={!name.trim()} onClick={() => onCreate(name.trim(), sourceType)}>创建</button>
        <button className="btn btn-sm" onClick={onCancel}>取消</button>
      </div>
    </div>
  );
}

// ─── 导入面板 ───
function ImportPanel({
  sourceType,
  busy,
  onImportFolder,
  onImportText,
  onImportExcel,
  onCancel,
}: {
  sourceType: DataSourceType;
  busy?: boolean;
  onImportFolder: (path: string) => void | Promise<void>;
  onImportText: (path: string) => void | Promise<void>;
  onImportExcel: (path: string, textColumns: string) => void | Promise<void>;
  onCancel: () => void;
}) {
  const [path, setPath] = useState("");
  const [textColumns, setTextColumns] = useState("");

  const handleImport = () => {
    if (!path.trim() || busy) return;
    if (sourceType === "image") onImportFolder(path.trim());
    else if (sourceType === "text") onImportText(path.trim());
    else if (sourceType === "excel") onImportExcel(path.trim(), textColumns.trim());
  };

  const placeholder = sourceType === "image" ? "粘贴病历图片父目录路径…" : sourceType === "text" ? "粘贴文本文件所在目录路径…" : "粘贴 Excel 文件路径…";

  return (
    <div style={{ padding: 10, marginBottom: 10, borderRadius: "var(--radius-md)", background: "var(--surface-2)", border: "1px solid var(--border)", animation: "content-in 200ms ease-out" }}>
      <PathInput
        value={path}
        onChange={setPath}
        mode={sourceType === "excel" ? "file" : "folder"}
        filters={sourceType === "excel" ? [{ name: "Excel", extensions: ["xlsx", "xls"] }] : undefined}
        placeholder={placeholder}
        style={{ marginBottom: 8 }}
      />
      {sourceType === "excel" && (
        <input value={textColumns} onChange={(e) => setTextColumns(e.target.value)} placeholder="病历文本列名(逗号分隔,空=全部列)" style={{ marginBottom: 8, fontSize: 11 }} />
      )}
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn btn-sm btn-primary" style={{ flex: 1 }} disabled={!path.trim() || busy} onClick={handleImport}>
          {busy ? "导入中…" : "导入"}
        </button>
        <button className="btn btn-sm" onClick={onCancel} disabled={busy}>取消</button>
      </div>
    </div>
  );
}
