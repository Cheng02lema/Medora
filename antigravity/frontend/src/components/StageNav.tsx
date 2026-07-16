import { useWorkbench } from "../store/workbench";
import { STAGE_ORDER, STAGE_LABELS, type StageKey } from "../api/client";

export default function StageNav() {
  const currentStage = useWorkbench((s) => s.currentStage);
  const setStage = useWorkbench((s) => s.setStage);
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const selectedIds = useWorkbench((s) => s.selectedIds);

  const getStageStatus = (stage: StageKey): string => {
    if (!patientDetail || selectedIds.length !== 1) return "pending";
    return patientDetail.stages[stage]?.status || "pending";
  };

  const getStageIcon = (status: string): string => {
    switch (status) {
      case "done": return "✓";
      case "running": return "·";
      case "error": return "×";
      case "skipped": return "–";
      case "stale": return "!";
      default: return "";
    }
  };

  return (
    <div className="stage-nav">
      {STAGE_ORDER.map((stage) => {
        const status = getStageStatus(stage);
        const isCurrent = currentStage === stage;
        const icon = getStageIcon(status);
        return (
          <div
            key={stage}
            className={`stage-pill ${isCurrent ? "current" : status}`}
            onClick={() => setStage(stage)}
          >
            {icon && <span className="stage-pill-icon">{icon}</span>}
            <span>{STAGE_LABELS[stage]}</span>
          </div>
        );
      })}
    </div>
  );
}
