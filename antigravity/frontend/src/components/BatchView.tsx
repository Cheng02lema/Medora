import { useWorkbench } from "../store/workbench";
import { STAGE_LABELS, type StageKey } from "../api/client";

export default function BatchView() {
  const patients = useWorkbench((s) => s.patients);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentStage = useWorkbench((s) => s.currentStage);
  const runBatch = useWorkbench((s) => s.runBatch);
  const selectPatient = useWorkbench((s) => s.selectPatient);

  const selectedPatients = patients.filter((p) => selectedIds.includes(p.id));

  if (selectedPatients.length === 0) return null;

  // 统计当前阶段状态
  const stageStatuses = selectedPatients.map((p) => {
    // 从 patientDetail 或 patients 列表获取阶段状态
    if (patientDetail && patientDetail.id === p.id) {
      return patientDetail.stages[currentStage]?.status || "pending";
    }
    return "—";
  });

  const doneCount = stageStatuses.filter((s) => s === "done").length;
  const errorCount = stageStatuses.filter((s) => s === "error").length;
  const pendingCount = stageStatuses.filter((s) => s === "pending" || s === "—").length;

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <div className="h1">批量操作</div>
        <span className="sub">已选 {selectedPatients.length} 位病人 · 当前阶段: {STAGE_LABELS[currentStage]}</span>
      </div>

      {/* 统计 */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        <div className="panel" style={{ padding: 16, flex: 1, textAlign: "center" }}>
          <div className="faint">已完成</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--success)" }}>{doneCount}</div>
        </div>
        <div className="panel" style={{ padding: 16, flex: 1, textAlign: "center" }}>
          <div className="faint">待处理</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--pending)" }}>{pendingCount}</div>
        </div>
        <div className="panel" style={{ padding: 16, flex: 1, textAlign: "center" }}>
          <div className="faint">失败</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--error)" }}>{errorCount}</div>
        </div>
      </div>

      {/* 操作按钮 */}
      {currentStage !== "source" && currentStage !== "export" && (
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          <button
            className="btn btn-primary"
            onClick={() => runBatch(selectedIds, currentStage)}
          >
            对选中 {selectedIds.length} 人执行 {STAGE_LABELS[currentStage]}
          </button>
          <button
            className="btn"
            onClick={() => runBatch(selectedIds, currentStage, true)}
          >
            ↻ 重新执行
          </button>
        </div>
      )}

      {/* 病人表格 */}
      <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
        <table className="batch-table">
          <thead>
            <tr>
              <th>病人</th>
              <th>整体状态</th>
              <th>{STAGE_LABELS[currentStage]} 状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {selectedPatients.map((p, idx) => {
              const stageStatus = stageStatuses[idx];
              return (
                <tr key={p.id}>
                  <td style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className={`status-dot ${p.status}`} />
                    <span style={{ fontWeight: 600 }}>{p.name}</span>
                  </td>
                  <td>
                    <span style={{ fontSize: 11, color: "var(--text-2)" }}>{p.status}</span>
                  </td>
                  <td>
                    {stageStatus === "done" && <span style={{ color: "var(--success)" }}>✓ 完成</span>}
                    {stageStatus === "error" && <span style={{ color: "var(--error)" }}>× 失败</span>}
                    {stageStatus === "running" && <span style={{ color: "var(--primary)" }}>进行中</span>}
                    {(stageStatus === "pending" || stageStatus === "—" || stageStatus === "skipped") && (
                      <span style={{ color: "var(--text-3)" }}>{stageStatus === "skipped" ? "已跳过" : "待处理"}</span>
                    )}
                    {stageStatus === "stale" && <span style={{ color: "var(--warning)" }}>! 待更新</span>}
                  </td>
                  <td>
                    <button
                      className="btn btn-sm"
                      onClick={() => selectPatient(p.id, false)}
                    >
                      查看详情
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
