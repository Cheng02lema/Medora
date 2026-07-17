import { useWorkbench } from "../store/workbench";

export default function StatusBar({
  isReconnecting = false,
  isDisconnected = false,
}: {
  isReconnecting?: boolean;
  isDisconnected?: boolean;
}) {
  const patients = useWorkbench((s) => s.patients);
  const runningTasks = useWorkbench((s) => s.runningTasks);

  const counts = {
    total: patients.length,
    pending: patients.filter((p) => p.status === "pending").length,
    running: patients.filter((p) => p.status === "running").length,
    done: patients.filter((p) => p.status === "done").length,
    error: patients.filter((p) => p.status === "error").length,
    review: patients.filter((p) => p.status === "review_pending").length,
    stale: patients.filter((p) => p.status === "stale").length,
  };
  const activeTasks = Object.keys(runningTasks).length;

  return (
    <div className="statusbar">
      <span>共 {counts.total} 人</span>
      <span style={{ color: "var(--pending)" }}>· 待处理 {counts.pending}</span>
      <span style={{ color: "var(--primary)" }}>· 进行中 {counts.running}</span>
      <span style={{ color: "var(--warning)" }}>· 待审核 {counts.review}</span>
      <span style={{ color: "var(--warning)" }}>· 待更新 {counts.stale}</span>
      <span style={{ color: "var(--success)" }}>· 完成 {counts.done}</span>
      <span style={{ color: "var(--error)" }}>· 失败 {counts.error}</span>
      {activeTasks > 0 && (
        <span style={{ color: "var(--primary)" }}>· 活跃任务 {activeTasks}</span>
      )}
      <div style={{ flex: 1 }} />
      {isReconnecting && (
        <span style={{ color: "var(--warning)" }}>重连中…</span>
      )}
      {isDisconnected && (
        <span style={{ color: "var(--error)" }}>已断开</span>
      )}
      {!isReconnecting && !isDisconnected && (
        <span style={{ color: "var(--success)" }}>已连接</span>
      )}
      <span style={{ marginLeft: 12 }}>澄诺 Clarinora v1.0</span>
    </div>
  );
}
