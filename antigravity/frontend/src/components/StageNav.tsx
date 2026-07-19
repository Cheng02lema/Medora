import { useWorkbench } from "../store/workbench";
import { STAGE_ORDER, STAGE_LABELS, type StageKey } from "../api/client";

const STATUS_BADGE: Record<string, string> = {
  pending: "",
  running: "进行",
  done: "完成",
  error: "失败",
  skipped: "跳过",
  stale: "待更新",
  review_pending: "待审",
};

export default function StageNav() {
  const currentStage = useWorkbench((s) => s.currentStage);
  const setStage = useWorkbench((s) => s.setStage);
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const selectedIds = useWorkbench((s) => s.selectedIds);

  const dataSource =
    (patientDetail?.stages?.source?.data?.data_source as string) || "image";
  const skipForText = new Set(["preprocess", "slice", "ocr"]);

  const getStageStatus = (stage: StageKey): string => {
    if (!patientDetail || selectedIds.length !== 1) return "pending";
    const st = patientDetail.stages[stage]?.status || "pending";
    if (
      selectedIds.length === 1 &&
      (dataSource === "text" || dataSource === "excel") &&
      skipForText.has(stage) &&
      (st === "pending" || st === "skipped")
    ) {
      return "skipped";
    }
    return st;
  };

  return (
    <div className="stage-nav">
      {STAGE_ORDER.map((stage, idx) => {
        const status = getStageStatus(stage);
        const isCurrent = currentStage === stage;
        const badge = STATUS_BADGE[status] || "";
        const num = String(idx + 1).padStart(2, "0");
        return (
          <div
            key={stage}
            className={`stage-pill ${isCurrent ? "current" : ""} ${status}`}
            onClick={() => setStage(stage)}
            title={STAGE_LABELS[stage]}
          >
            <span className="stage-num">{num}</span>
            <span>{STAGE_LABELS[stage]}</span>
            {badge && <span className="stage-badge">{badge}</span>}
          </div>
        );
      })}
    </div>
  );
}
