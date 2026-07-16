import { useState } from "react";
import { useWorkbench } from "../store/workbench";

const STATUS_COLORS: Record<string, string> = {
  pending: "var(--pending)",
  running: "var(--primary)",
  done: "var(--success)",
  error: "var(--error)",
  stale: "var(--warning)",
  review_pending: "var(--warning)",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  running: "进行中",
  done: "已完成",
  error: "失败",
  stale: "待更新",
  review_pending: "待审核",
};

function colorForName(name: string): string {
  const palette = ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#06b6d4", "#ef4444", "#3b82f6"];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return palette[hash % palette.length];
}

export default function PatientSidebar() {
  const patients = useWorkbench((s) => s.patients);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const selectPatient = useWorkbench((s) => s.selectPatient);
  const sidebarCollapsed = useWorkbench((s) => s.sidebarCollapsed);
  const runningTasks = useWorkbench((s) => s.runningTasks);

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");

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

  if (sidebarCollapsed) {
    return (
      <>
        {patients.map((p) => (
          <div
            key={p.id}
            className={`patient-card ${selectedIds.includes(p.id) ? "selected" : ""}`}
            style={{ padding: 8, justifyContent: "center" }}
            onClick={(e) => selectPatient(p.id, e.ctrlKey || e.metaKey || e.shiftKey)}
            title={p.name}
          >
            <div className="patient-avatar" style={{ width: 28, height: 28, fontSize: 12, background: colorForName(p.name) }}>
              {p.name.slice(0, 1).toUpperCase()}
            </div>
          </div>
        ))}
      </>
    );
  }

  return (
    <>
      <div className="sidebar-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span className="h2">病人实例</span>
          <span className="faint">{counts.all} 位</span>
        </div>
      </div>

      <div className="sidebar-search">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索病人…"
        />
      </div>

      <div className="filter-bar">
        {[
          { key: "all", label: `全部 ${counts.all}` },
          { key: "pending", label: `待处理 ${counts.pending}` },
          { key: "running", label: `进行中 ${counts.running}` },
          { key: "review", label: `待审核 ${counts.review}` },
          { key: "done", label: `已完成 ${counts.done}` },
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

      <div className="patient-list">
        {filtered.length === 0 && (
          <div className="empty-state" style={{ padding: 30 }}>
            <div className="empty-icon">📋</div>
            <div className="empty-desc">
              {patients.length === 0 ? "尚未录入病人，点击上方「导入病人」" : "无匹配病人"}
            </div>
          </div>
        )}
        {filtered.map((p) => {
          const task = runningTasks[p.id];
          const progress = task ? (task.total > 0 ? (task.current / task.total) * 100 : 0) : (p.stage_progress && p.stage_progress.total > 0 ? (p.stage_progress.current / p.stage_progress.total) * 100 : 0);
          return (
            <div
              key={p.id}
              className={`patient-card ${selectedIds.includes(p.id) ? "selected" : ""}`}
              onClick={(e) => selectPatient(p.id, e.ctrlKey || e.metaKey || e.shiftKey)}
            >
              <div className="patient-avatar" style={{ background: colorForName(p.name) }}>
                {p.name.slice(0, 1).toUpperCase()}
              </div>
              <div className="patient-info">
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="patient-name">{p.name}</span>
                  <span className={`status-dot ${p.status}`} />
                </div>
                <div className="patient-meta">
                  {p.status === "error" && p.error
                    ? `! ${p.error.slice(0, 30)}`
                    : task
                    ? `${task.message}`
                    : p.stage_progress
                    ? `${p.stage_progress.message} · ${p.stage_progress.current}/${p.stage_progress.total}`
                    : `${STATUS_LABELS[p.status] || p.status} · ${p.image_count} 张图`}
                </div>
                {(progress > 0 || task) && (
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${progress}%` }} />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
