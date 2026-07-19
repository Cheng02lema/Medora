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
  const settings = useWorkbench((s) => s.settings);

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
  const parallel = settings?.execution?.max_parallel_patients ?? 1;

  let conn = "已连接";
  let connColor = "var(--mint)";
  if (isReconnecting) {
    conn = "重连中";
    connColor = "var(--amber)";
  } else if (isDisconnected) {
    conn = "已断开";
    connColor = "var(--red)";
  }

  return (
    <div className="statusbar">
      <span>共 {counts.total}</span>
      <span className="sep" />
      <span>待处理 {counts.pending}</span>
      <span className="sep" />
      <span style={{ color: counts.running ? "var(--amber)" : undefined }}>
        进行中 {counts.running}
      </span>
      <span className="sep" />
      <span style={{ color: counts.review || counts.stale ? "var(--amber)" : undefined }}>
        待审核 {counts.review}
      </span>
      <span className="sep" />
      <span style={{ color: counts.done ? "var(--mint)" : undefined }}>
        完成 {counts.done}
      </span>
      <span className="sep" />
      <span style={{ color: counts.error ? "var(--red)" : undefined }}>
        失败 {counts.error}
      </span>
      {activeTasks > 0 && (
        <>
          <span className="sep" />
          <span style={{ color: "var(--violet-2)" }}>活跃 {activeTasks}</span>
        </>
      )}
      <div className="grow" />
      <span>同时处理 {parallel}</span>
      <span className="sep" />
      <span style={{ color: connColor }}>{conn}</span>
      <span className="sep" />
      <span>Clarinora</span>
    </div>
  );
}
