import { useWorkbench } from "../store/workbench";
import SourceStage from "./stages/SourceStage";
import OCRStage from "./stages/OCRStage";
import MergeStage from "./stages/MergeStage";
import ExtractStage from "./stages/ExtractStage";
import PreprocessStage from "./stages/PreprocessStage";
import SliceStage from "./stages/SliceStage";
import ReviewStage from "./stages/ReviewStage";
import ExportStage from "./stages/ExportStage";
import BatchView from "./BatchView";

export default function StageContent() {
  const currentStage = useWorkbench((s) => s.currentStage);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const loadingStage = useWorkbench((s) => s.loadingStage);

  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const projects = useWorkbench((s) => s.projects);
  const currentProject = projects.find((p) => p.id === currentProjectId);

  if (!currentProjectId) {
    return (
      <div className="stage-content">
        <div className="empty-state">
          <div className="empty-icon">+</div>
          <div className="empty-title">先创建或选择一个项目</div>
          <div className="empty-desc">左侧点击 + 新建项目，再导入病人</div>
        </div>
      </div>
    );
  }

  if (selectedIds.length === 0) {
    return (
      <div className="stage-content">
        <div className="empty-state">
          <div className="empty-icon">·</div>
          <div className="empty-title">选择一位病人开始</div>
          <div className="empty-desc">
            项目「{currentProject?.name || ""}」· 从左侧导入或选择病人
            <br />
            支持图片文件夹 / Excel 拆分 / 文本文件
          </div>
        </div>
      </div>
    );
  }

  if (selectedIds.length > 1) {
    return (
      <div className="stage-content">
        <div className="stage-content-enter">
          <BatchView />
        </div>
      </div>
    );
  }

  if (!patientDetail) {
    return (
      <div className="stage-content">
        <div style={{ padding: 20 }}>
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line short" />
          <div className="skeleton skeleton-line" />
        </div>
      </div>
    );
  }

  const key = `${currentPatientId}-${currentStage}`;

  return (
    <div className="stage-content" key={key}>
      <div className="stage-content-enter">
        {loadingStage && currentStage !== "source" && (
          <div style={{ marginBottom: 16 }}>
            <div className="skeleton skeleton-line" />
            <div className="skeleton skeleton-line short" />
          </div>
        )}
        {currentStage === "source" && <SourceStage />}
        {currentStage === "preprocess" && <PreprocessStage />}
        {currentStage === "slice" && <SliceStage />}
        {currentStage === "ocr" && <OCRStage />}
        {currentStage === "merge" && <MergeStage />}
        {currentStage === "extract" && <ExtractStage />}
        {currentStage === "review" && <ReviewStage />}
        {currentStage === "export" && <ExportStage />}
      </div>
    </div>
  );
}
