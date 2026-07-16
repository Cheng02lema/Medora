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
  const addToast = useWorkbench((s) => s.addToast);

  const runStage = useWorkbench((s) => s.runStage);
  const runBatch = useWorkbench((s) => s.runBatch);
  const stopTask = useWorkbench((s) => s.stopTask);

  // 预处理配置本地状态
  const [preConfig, setPreConfig] = useState<any>(null);

  useEffect(() => {
    if (currentPatientId && currentStage === "preprocess") {
      api.getPreprocessConfig(currentPatientId).then(setPreConfig).catch(() => setPreConfig(null));
    }
  }, [currentPatientId, currentStage]);

  const task = currentPatientId ? runningTasks[currentPatientId] : null;
  const isRunning = !!task;
  const dataSource = patientDetail?.stages?.source?.data?.data_source || "image";
  const skipStagesForText = ["preprocess", "slice", "ocr"];
  const isSkipStage =
    (dataSource === "text" || dataSource === "excel") &&
    skipStagesForText.includes(currentStage);

  const handleRun = () => {
    if (isSkipStage) {
      addToast("info", `数据源为 ${dataSource === "excel" ? "Excel" : "文本"}，此阶段会自动跳过`);
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
    const tid = task?.taskId || Object.values(runningTasks).find((t) => t.taskId)?.taskId;
    if (tid) stopTask(tid);
    else addToast("warning", "暂无任务 ID，请稍候再停或刷新");
  };

  const patientLogs = logs.filter(
    (l) => !l.patient_id || l.patient_id === currentPatientId
  ).slice(-50);

  return (
    <>
      {/* 当前阶段标题 */}
      <div style={{ marginBottom: 16 }}>
        <div className="h1">{STAGE_LABELS[currentStage]}</div>
        <div className="sub" style={{ marginTop: 4 }}>
          {selectedIds.length === 0
            ? "请先选择病人"
            : selectedIds.length === 1
            ? patientDetail?.name || ""
            : `已选 ${selectedIds.length} 位病人`}
        </div>
        {selectedIds.length === 1 && dataSource !== "image" && (
          <div className="faint" style={{ marginTop: 6 }}>
            数据源: {dataSource === "excel" ? "Excel 拆分" : "文本文件"} · 预处理/切片/OCR 可跳过
          </div>
        )}
      </div>

      {/* 执行按钮 */}
      {currentStage !== "source" && currentStage !== "export" && (
        <div className="panel-section">
          {isSkipStage && (
            <div
              style={{
                marginBottom: 10,
                padding: 10,
                borderRadius: 8,
                background: "var(--warning-fade)",
                border: "1px solid var(--warning)",
                color: "var(--warning)",
                fontSize: 12,
              }}
            >
              文本/Excel 数据源无需此阶段，可直接进入合并或抽取
            </div>
          )}
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <button
              className="btn btn-primary"
              style={{ flex: 1 }}
              disabled={isRunning || selectedIds.length === 0 || isSkipStage}
              onClick={handleRun}
            >
              {isRunning
                ? "执行中…"
                : isSkipStage
                ? "自动跳过"
                : `执行${selectedIds.length > 1 ? `(${selectedIds.length}人)` : ""}`}
            </button>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn-sm"
              disabled={isRunning || selectedIds.length === 0 || isSkipStage}
              onClick={handleRerun}
            >
              重新执行
            </button>
            {isRunning && (
              <button className="btn btn-sm" onClick={handleStop} disabled={!task?.taskId}>
                停止
              </button>
            )}
          </div>
          {isRunning && task && (
            <div style={{ marginTop: 10 }}>
              <div className="progress-bar" style={{ height: 4 }}>
                <div
                  className="progress-fill"
                  style={{
                    width: `${task.total > 0 ? (task.current / task.total) * 100 : 0}%`,
                  }}
                />
              </div>
              <div className="faint" style={{ marginTop: 4 }}>
                {task.message}
                {task.total > 0 && ` · ${task.current}/${task.total}`}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 阶段统计 */}
      {patientDetail && selectedIds.length === 1 && (
        <div className="panel-section">
          <div className="panel-section-title">阶段统计</div>
          {currentStage === "source" && (
            <div className="stat-row">
              <span className="stat-label">图片数量</span>
              <span className="stat-value">{patientDetail.images.length}</span>
            </div>
          )}
          {currentStage === "ocr" && (
            <>
              <div className="stat-row">
                <span className="stat-label">已识别页数</span>
                <span className="stat-value">{patientDetail.ocr_pages.length}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">总字数</span>
                <span className="stat-value">
                  {patientDetail.ocr_pages.reduce((sum, p) => sum + p.char_count, 0)}
                </span>
              </div>
            </>
          )}
          {currentStage === "merge" && (
            <div className="stat-row">
              <span className="stat-label">合并字数</span>
              <span className="stat-value">
                {patientDetail.merged_text?.length || 0}
              </span>
            </div>
          )}
          {currentStage === "extract" && patientDetail.extracted_fields && (
            <div className="stat-row">
              <span className="stat-label">字段数</span>
              <span className="stat-value">
                {Object.keys(patientDetail.extracted_fields.fields || {}).length}
              </span>
            </div>
          )}
        </div>
      )}

      {/* 配置摘要 */}
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
                <span className="stat-value" style={{ color: settings.ocr.token_configured ? "var(--success)" : "var(--error)" }}>
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
                <span className="stat-value" style={{ color: settings.extract_llm.api_key_configured ? "var(--success)" : "var(--error)" }}>
                  {settings.extract_llm.api_key_configured ? "已配置" : "未配置"}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {/* 预处理：场景预设摘要（详细配置在主区） */}
      {currentStage === "preprocess" && currentPatientId && preConfig && (
        <div className="panel-section">
          <div className="panel-section-title">预处理</div>
          <div className="stat-row">
            <span className="stat-label">场景预设</span>
            <span className="stat-value">{preConfig.preset || "paper_photo"}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">遮罩</span>
            <span className="stat-value">{preConfig.mask_regions?.length || 0} 个</span>
          </div>
          {(preConfig.metrics_score?.better != null) && (
            <div className="stat-row">
              <span className="stat-label">上次指标</span>
              <span className="stat-value">
                ↑{preConfig.metrics_score.better || 0} / ~{preConfig.metrics_score.worse_or_same || 0}
              </span>
            </div>
          )}
          <div className="faint" style={{ marginBottom: 6, lineHeight: 1.5 }}>
            在主区选场景预设、试跑对比、框选遮罩；此处仅显示当前配置摘要。
          </div>
          <button className="btn btn-sm" style={{ width: "100%" }}
            onClick={() => api.getPreprocessConfig(currentPatientId).then(setPreConfig).catch(() => {})}>
            刷新摘要
          </button>
        </div>
      )}

      {/* 切片说明 */}
      {currentStage === "slice" && currentPatientId && (
        <div className="panel-section">
          <div className="panel-section-title">切片操作</div>
          <div className="faint" style={{ lineHeight: 1.6 }}>
            在主区图片上拖拽框选区域，可拖动/缩放。
            保存后点「执行」批量裁剪；结果用于后续 OCR。
          </div>
        </div>
      )}

      {/* 错误信息 */}
      {patientDetail && selectedIds.length === 1 && (() => {
        const stageState = patientDetail.stages[currentStage];
        if (stageState?.status === "error" && stageState.error) {
          return (
            <div style={{
              padding: 12, borderRadius: 10, marginBottom: 14,
              background: "var(--error-fade)", border: "1px solid var(--error)",
            }}>
              <div style={{ fontSize: 12, color: "var(--error)", fontWeight: 600, marginBottom: 4 }}>
                × 执行失败
              </div>
              <div style={{ fontSize: 11, color: "var(--text-2)", wordBreak: "break-all" }}>
                {stageState.error}
              </div>
              <button className="btn btn-sm" style={{ marginTop: 8 }}
                disabled={isRunning}
                onClick={handleRerun}>
                ↻ 重试
              </button>
            </div>
          );
        }
        return null;
      })()}

      {/* 实时日志 */}
      <div className="panel-section" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div className="panel-section-title">实时日志</div>
        <div className="log-stream">
          {patientLogs.length === 0 ? (
            <div style={{ color: "var(--text-3)" }}>暂无日志</div>
          ) : (
            patientLogs.map((log, i) => (
              <div key={i} className={`log-line ${log.level}`}>
                <span className="log-time">
                  {log.timestamp.slice(11, 19)}
                </span>
                {log.message}
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
