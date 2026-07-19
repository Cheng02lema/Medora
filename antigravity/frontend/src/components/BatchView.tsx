import { useWorkbench } from "../store/workbench";
import { STAGE_LABELS, type StageKey } from "../api/client";

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  running: "进行中",
  done: "完成",
  error: "失败",
  stale: "待更新",
  review_pending: "待审核",
  skipped: "跳过",
  "—": "—",
};

export default function BatchView() {
  const patients = useWorkbench((s) => s.patients);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentStage = useWorkbench((s) => s.currentStage);
  const runningTasks = useWorkbench((s) => s.runningTasks);
  const settings = useWorkbench((s) => s.settings);
  const runBatch = useWorkbench((s) => s.runBatch);
  const selectPatient = useWorkbench((s) => s.selectPatient);

  const selectedPatients = patients.filter((p) => selectedIds.includes(p.id));
  const parallel = settings?.execution?.max_parallel_patients ?? 1;

  if (selectedPatients.length === 0) return null;

  const stageStatuses = selectedPatients.map((p) => {
    if (runningTasks[p.id]) return "running";
    if (patientDetail && patientDetail.id === p.id) {
      return patientDetail.stages[currentStage]?.status || "pending";
    }
    if (p.status === "running") return "running";
    if (p.status === "error") return "error";
    if (p.status === "done") return "done";
    return p.status || "pending";
  });

  const doneCount = stageStatuses.filter((s) => s === "done").length;
  const errorCount = stageStatuses.filter((s) => s === "error").length;
  const runningCount = stageStatuses.filter((s) => s === "running").length;
  const pendingCount = selectedPatients.length - doneCount - errorCount - runningCount;

  const stageLabel = STAGE_LABELS[currentStage as StageKey] || currentStage;

  return (
    <>
      <div className="hd" style={{ margin: "-12px -12px 12px", borderLeft: "none", borderRight: "none", borderTop: "none" }}>
        <span>批量 · {stageLabel}</span>
        <b>{selectedPatients.length} 人</b>
      </div>

      <div className="kv" style={{ marginBottom: 12 }}>
        <div className="cell">
          <label>待处理</label>
          <strong>{pendingCount}</strong>
        </div>
        <div className="cell">
          <label>进行中</label>
          <strong style={{ color: runningCount ? "var(--amber)" : undefined }}>{runningCount}</strong>
        </div>
        <div className="cell">
          <label>完成</label>
          <strong style={{ color: doneCount ? "var(--mint)" : undefined }}>{doneCount}</strong>
        </div>
        <div className="cell">
          <label>失败</label>
          <strong style={{ color: errorCount ? "var(--red)" : undefined }}>{errorCount}</strong>
        </div>
      </div>

      <div className="faint mono" style={{ marginBottom: 12, lineHeight: 1.6 }}>
        右侧执行将对 {selectedPatients.length} 人批量跑「{stageLabel}」
        · 同时处理 {parallel} 人
      </div>

      {currentStage !== "source" && currentStage !== "export" && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button
            className="btn btn-primary"
            onClick={() => runBatch(selectedIds, currentStage)}
          >
            对 {selectedIds.length} 人执行{stageLabel}
          </button>
          <button
            className="btn"
            onClick={() => runBatch(selectedIds, currentStage, true)}
          >
            重新执行
          </button>
        </div>
      )}

      <div style={{ border: "1px solid var(--line)", overflow: "hidden" }}>
        <table className="batch-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>病人</th>
              <th>整体</th>
              <th>{stageLabel}</th>
              <th>进度</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {selectedPatients.map((p, idx) => {
              const stageStatus = stageStatuses[idx];
              const task = runningTasks[p.id];
              const prog =
                task && task.total > 0
                  ? Math.round((task.current / task.total) * 100)
                  : p.stage_progress && p.stage_progress.total > 0
                  ? Math.round((p.stage_progress.current / p.stage_progress.total) * 100)
                  : stageStatus === "done"
                  ? 100
                  : 0;
              return (
                <tr
                  key={p.id}
                  className={selectedIds[0] === p.id && selectedIds.length === 1 ? "sel" : ""}
                  onClick={() => selectPatient(p.id, false)}
                >
                  <td className="mono" style={{ color: "var(--mute)", fontSize: 11 }}>
                    {p.id.slice(0, 6).toUpperCase()}
                  </td>
                  <td style={{ fontWeight: 500 }}>{p.name}</td>
                  <td>
                    <span className={`st ${p.status === "running" ? "run" : p.status === "done" ? "done" : p.status === "error" ? "err" : "wait"}`}>
                      <i />
                      {STATUS_LABELS[p.status] || p.status}
                    </span>
                  </td>
                  <td>
                    <span className={`st ${stageStatus === "running" ? "run" : stageStatus === "done" ? "done" : stageStatus === "error" ? "err" : "wait"}`}>
                      <i />
                      {STATUS_LABELS[stageStatus] || stageStatus}
                    </span>
                  </td>
                  <td>
                    <span className="bar" style={{ marginRight: 8 }}>
                      <span style={{ display: "block", height: "100%", width: `${prog}%`, background: "var(--violet)" }} />
                    </span>
                    <span className="mono" style={{ fontSize: 11 }}>{prog}%</span>
                  </td>
                  <td>
                    <button
                      className="btn btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        selectPatient(p.id, false);
                      }}
                    >
                      查看
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
