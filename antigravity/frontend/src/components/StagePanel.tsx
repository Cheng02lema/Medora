import { useState, useEffect } from "react";
import { useWorkbench } from "../store/workbench";
import { STAGE_LABELS, api, type StageKey } from "../api/client";

export default function StagePanel() {
  const currentStage = useWorkbench((s) => s.currentStage);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const runningTasks = useWorkbench((s) => s.runningTasks);
  const logs = useWorkbench((s) => s.logs);
  const settings = useWorkbench((s) => s.settings);
  const projects = useWorkbench((s) => s.projects);
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const addToast = useWorkbench((s) => s.addToast);

  const runStage = useWorkbench((s) => s.runStage);
  const runBatch = useWorkbench((s) => s.runBatch);
  const stopTask = useWorkbench((s) => s.stopTask);

  const [preConfig, setPreConfig] = useState<any>(null);

  useEffect(() => {
    if (currentPatientId && currentStage === "preprocess") {
      api.getPreprocessConfig(currentPatientId).then(setPreConfig).catch(() => setPreConfig(null));
    }
  }, [currentPatientId, currentStage]);

  const task = currentPatientId ? runningTasks[currentPatientId] : null;
  const anyRunning = Object.keys(runningTasks).length > 0;
  const isRunning = !!task || (selectedIds.length > 1 && anyRunning);
  const dataSource = patientDetail?.stages?.source?.data?.data_source || "image";
  const skipStagesForText = ["preprocess", "slice", "ocr"];
  const isSkipStage =
    (dataSource === "text" || dataSource === "excel") &&
    skipStagesForText.includes(currentStage);

  const stageLabel = STAGE_LABELS[currentStage as StageKey] || currentStage;
  const project = projects.find((p) => p.id === currentProjectId);
  const noTemplate = project && !project.has_template && currentStage === "extract";
  const noSelection = selectedIds.length === 0;
  const canRun =
    !isRunning &&
    !noSelection &&
    !isSkipStage &&
    currentStage !== "source" &&
    currentStage !== "export" &&
    !noTemplate;

  let disableReason = "";
  if (noSelection) disableReason = "请先选择病人";
  else if (isSkipStage) disableReason = "文本/Excel 源自动跳过此阶段";
  else if (noTemplate) disableReason = "项目未配模板";
  else if (currentStage === "source" || currentStage === "export") disableReason = "此阶段无需从此处执行";

  const runLabel =
    selectedIds.length > 1
      ? `对 ${selectedIds.length} 人执行${stageLabel}`
      : `执行${stageLabel}`;

  const handleRun = () => {
    if (isSkipStage) {
      addToast("info", `数据源为 ${dataSource === "excel" ? "Excel" : "文本"}，此阶段会自动跳过`);
      return;
    }
    if (noTemplate) {
      addToast("warning", "请先在项目设置中配置抽取模板");
      return;
    }
    if (selectedIds.length === 1 && currentPatientId) {
      runStage(currentPatientId, currentStage);
    } else if (selectedIds.length > 1) {
      runBatch(selectedIds, currentStage);
    }
  };

  const handleRerun = () => {
    if (isSkipStage) {
      addToast("info", `数据源为 ${dataSource === "excel" ? "Excel" : "文本"}，此阶段无需重跑`);
      return;
    }
    if (selectedIds.length === 1 && currentPatientId) {
      runStage(currentPatientId, currentStage, true);
    } else if (selectedIds.length > 1) {
      runBatch(selectedIds, currentStage, true);
    }
  };

  const handleStop = () => {
    const tid =
      task?.taskId ||
      Object.values(runningTasks).find((t) => t.taskId)?.taskId;
    if (tid) stopTask(tid);
    else addToast("warning", "暂无任务 ID，请稍候再停");
  };

  const patientLogs = logs
    .filter((l) => !l.patient_id || l.patient_id === currentPatientId || selectedIds.includes(l.patient_id || ""))
    .slice(-50);

  const targetLabel =
    selectedIds.length === 0
      ? "未选病人"
      : selectedIds.length === 1
      ? patientDetail?.name || "…"
      : `已选 ${selectedIds.length} 人`;

  const showActions = currentStage !== "source" && currentStage !== "export";

  return (
    <div className="stage-panel-inner">
      <div className="hd">
        <span>操作</span>
        <b>{stageLabel}</b>
      </div>

      <div className="stage-panel-scroll">
        <div style={{ marginBottom: 12 }}>
          <div className="patient-name" style={{ color: "var(--fg)" }}>{targetLabel}</div>
          {selectedIds.length === 1 && dataSource !== "image" && (
            <div className="faint" style={{ marginTop: 4 }}>
              数据源 {dataSource === "excel" ? "Excel" : "文本"}
            </div>
          )}
          {disableReason && !isRunning && (
            <div className="faint" style={{ marginTop: 6, color: "var(--amber)" }}>
              {disableReason}
            </div>
          )}
        </div>

        {isRunning && task && (
          <div className="panel-section">
            <div className="panel-section-title">进度</div>
            <div className="progress-bar" style={{ width: "100%", height: 4 }}>
              <div
                className="progress-fill"
                style={{
                  width: `${task.total > 0 ? (task.current / task.total) * 100 : 0}%`,
                }}
              />
            </div>
            <div className="faint mono" style={{ marginTop: 6 }}>
              {task.message}
              {task.total > 0 && ` · ${task.current}/${task.total}`}
            </div>
          </div>
        )}

        {patientDetail && selectedIds.length === 1 && (
          <div className="panel-section">
            <div className="panel-section-title">阶段统计</div>
            {currentStage === "source" && (
              <div className="stat-row">
                <span className="stat-label">图片</span>
                <span className="stat-value">{patientDetail.images.length}</span>
              </div>
            )}
            {currentStage === "ocr" && (
              <>
                <div className="stat-row">
                  <span className="stat-label">已识别</span>
                  <span className="stat-value">{patientDetail.ocr_pages.length}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">字数</span>
                  <span className="stat-value">
                    {patientDetail.ocr_pages.reduce((sum, p) => sum + p.char_count, 0)}
                  </span>
                </div>
              </>
            )}
            {currentStage === "merge" && (
              <div className="stat-row">
                <span className="stat-label">合并字数</span>
                <span className="stat-value">{patientDetail.merged_text?.length || 0}</span>
              </div>
            )}
            {currentStage === "extract" && patientDetail.extracted_fields && (
              <div className="stat-row">
                <span className="stat-label">字段</span>
                <span className="stat-value">
                  {Object.keys(patientDetail.extracted_fields.fields || {}).length}
                </span>
              </div>
            )}
          </div>
        )}

        {settings && (currentStage === "ocr" || currentStage === "extract") && (
          <div className="panel-section">
            <div className="panel-section-title">
              {currentStage === "ocr" ? "OCR 配置" : "抽取配置"}
            </div>
            {currentStage === "ocr" && (
              <>
                <div className="stat-row">
                  <span className="stat-label">模型</span>
                  <span className="stat-value">{settings.ocr.model || "未配置"}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">预设</span>
                  <span className="stat-value">{settings.ocr.preset}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Token</span>
                  <span className="stat-value" style={{ color: settings.ocr.token_configured ? "var(--mint)" : "var(--red)" }}>
                    {settings.ocr.token_configured ? "已配置" : "未配置"}
                  </span>
                </div>
              </>
            )}
            {currentStage === "extract" && (
              <>
                <div className="stat-row">
                  <span className="stat-label">Provider</span>
                  <span className="stat-value">{settings.extract_llm.provider || "未配置"}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">模型</span>
                  <span className="stat-value">{settings.extract_llm.model || "未配置"}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">API Key</span>
                  <span className="stat-value" style={{ color: settings.extract_llm.api_key_configured ? "var(--mint)" : "var(--red)" }}>
                    {settings.extract_llm.api_key_configured ? "已配置" : "未配置"}
                  </span>
                </div>
              </>
            )}
          </div>
        )}

        {currentStage === "preprocess" && currentPatientId && preConfig && (
          <div className="panel-section">
            <div className="panel-section-title">预处理</div>
            <div className="stat-row">
              <span className="stat-label">预设</span>
              <span className="stat-value">{preConfig.preset || "paper_photo"}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">遮罩</span>
              <span className="stat-value">{preConfig.mask_regions?.length || 0}</span>
            </div>
            <div className="faint" style={{ marginBottom: 6, lineHeight: 1.5 }}>
              在主区调参、试跑与框选遮罩。
            </div>
            <button
              className="btn btn-sm"
              style={{ width: "100%" }}
              onClick={() => api.getPreprocessConfig(currentPatientId).then(setPreConfig).catch(() => {})}
            >
              刷新摘要
            </button>
          </div>
        )}

        {currentStage === "slice" && currentPatientId && (
          <div className="panel-section">
            <div className="panel-section-title">切片</div>
            <div className="faint" style={{ lineHeight: 1.6 }}>
              在主区拖拽框选；保存后执行批量裁剪，供 OCR 使用。
            </div>
          </div>
        )}

        {patientDetail && selectedIds.length === 1 && (() => {
          const stageState = patientDetail.stages[currentStage];
          if (stageState?.status === "error" && stageState.error) {
            return (
              <div
                style={{
                  padding: 10,
                  marginBottom: 12,
                  background: "var(--red-fade)",
                  border: "1px solid rgba(244,63,94,.4)",
                }}
              >
                <div style={{ fontSize: 11, color: "var(--red)", fontFamily: "var(--mono)", marginBottom: 4 }}>
                  执行失败
                </div>
                <div style={{ fontSize: 11, color: "var(--text-2)", wordBreak: "break-all" }}>
                  {stageState.error}
                </div>
              </div>
            );
          }
          return null;
        })()}

        <div className="panel-section" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 80 }}>
          <div className="panel-section-title">实时日志</div>
          <div className="log-stream">
            {patientLogs.length === 0 ? (
              <div style={{ color: "var(--mute)" }}>暂无日志</div>
            ) : (
              patientLogs.map((log, i) => (
                <div key={i} className={`log-line ${log.level}`}>
                  <span className="log-time">{log.timestamp.slice(11, 19)}</span>
                  {log.message}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {showActions && (
        <div className="stage-panel-actions">
          {isRunning ? (
            <button type="button" className="span-2" onClick={handleStop}>
              停止
            </button>
          ) : (
            <>
              <button
                type="button"
                className="pri"
                disabled={!canRun}
                onClick={handleRun}
              >
                {isSkipStage ? "自动跳过" : runLabel}
              </button>
              <button
                type="button"
                disabled={!canRun}
                onClick={handleRerun}
              >
                重新执行
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
