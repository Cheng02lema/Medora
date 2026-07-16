import { useState, useEffect } from "react";
import { useWorkbench } from "../../store/workbench";
import { api } from "../../api/client";
import PathInput from "../PathInput";

export default function ExportStage() {
  const patients = useWorkbench((s) => s.patients);
  const projects = useWorkbench((s) => s.projects);
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const exportExcel = useWorkbench((s) => s.exportExcel);
  const addToast = useWorkbench((s) => s.addToast);

  const currentProject = projects.find((p) => p.id === currentProjectId);
  const [outputPath, setOutputPath] = useState("");
  const [exporting, setExporting] = useState(false);
  const [preview, setPreview] = useState<any[]>([]);
  const [range, setRange] = useState<"current" | "reviewed" | "all" | "manual">("all");
  const [manualSelected, setManualSelected] = useState<Set<string>>(new Set());
  const [lastPath, setLastPath] = useState("");

  useEffect(() => {
    // 默认导出路径：项目配置（若有）
    if (!outputPath && currentProjectId) {
      api.getProjectConfig(currentProjectId).then((c) => {
        const p = c.pipeline?.output_excel || "";
        if (p) setOutputPath(p);
      }).catch(() => {});
    }
  }, [currentProjectId]);

  const completedPatients = patients.filter(
    (p) => p.status === "done" || p.status === "review_pending"
  );
  // 已审核：以 preview 的 review_status 为准更准，列表侧用 status===done 近似
  const reviewedPatients = patients.filter((p) => p.status === "done");

  useEffect(() => {
    loadPreview();
  }, [patients, currentProjectId]);

  const loadPreview = async () => {
    try {
      const ids = completedPatients.map((p) => p.id);
      if (ids.length === 0) {
        setPreview([]);
        return;
      }
      const result = await api.exportPreview(ids, currentProjectId || undefined);
      setPreview(result);
    } catch {
      setPreview([]);
    }
  };

  const getExportIds = (): string[] => {
    switch (range) {
      case "current":
        return currentPatientId ? [currentPatientId] : [];
      case "reviewed":
        return reviewedPatients.map((p) => p.id);
      case "all":
        return completedPatients.map((p) => p.id);
      case "manual":
        return Array.from(manualSelected);
    }
  };

  const handleExport = async () => {
    const ids = getExportIds();
    if (ids.length === 0) {
      addToast("warning", "没有可导出的病人");
      return;
    }
    if (!outputPath.trim()) {
      addToast("warning", "请填写输出路径");
      return;
    }
    setExporting(true);
    try {
      await exportExcel(ids, outputPath.trim());
      setLastPath(outputPath.trim());
    } catch (e: any) {
      addToast("error", e.message || "导出失败");
    } finally {
      setExporting(false);
    }
  };

  const copyPath = async () => {
    const p = lastPath || outputPath;
    if (!p) return;
    try {
      await navigator.clipboard.writeText(p);
      addToast("success", "路径已复制");
    } catch {
      addToast("info", p);
    }
  };

  const toggleManual = (id: string) => {
    setManualSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 预览表格列
  const previewColumns = preview.length > 0
    ? Object.keys(preview[0].fields || {}).slice(0, 10)
    : [];

  return (
    <>
      <div className="h2" style={{ marginBottom: 16 }}>导出 Excel</div>

      {/* 导出范围 */}
      <div style={{ marginBottom: 16 }}>
        <div className="form-label">导出范围</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {[
            { key: "current", label: `仅当前病人${currentPatientId ? ` (${patients.find(p => p.id === currentPatientId)?.name || ""})` : ""}`, disabled: !currentPatientId },
            { key: "reviewed", label: `所有已审核 (${reviewedPatients.length} 人)`, disabled: reviewedPatients.length === 0 },
            { key: "all", label: `所有已完成抽取 (${completedPatients.length} 人)`, disabled: completedPatients.length === 0 },
            { key: "manual", label: "手动选择", disabled: completedPatients.length === 0 },
          ].map((opt) => (
            <label
              key={opt.key}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                fontSize: 12, cursor: opt.disabled ? "not-allowed" : "pointer",
                opacity: opt.disabled ? 0.4 : 1,
              }}
            >
              <input
                type="radio"
                checked={range === opt.key}
                onChange={() => setRange(opt.key as any)}
                disabled={opt.disabled}
                style={{ width: "auto" }}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </div>

      {/* 手动选择 */}
      {range === "manual" && (
        <div style={{ marginBottom: 16, padding: 12, borderRadius: 10, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
          <div className="faint" style={{ marginBottom: 8 }}>选择要导出的病人:</div>
          {completedPatients.map((p) => (
            <label key={p.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, marginBottom: 4, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={manualSelected.has(p.id)}
                onChange={() => toggleManual(p.id)}
                style={{ width: "auto" }}
              />
              <span className={`status-dot ${p.status}`} />
              {p.name}
            </label>
          ))}
        </div>
      )}

      {/* 输出路径 */}
      <div className="form-group">
        <label className="form-label">输出路径</label>
        <PathInput value={outputPath} onChange={setOutputPath} mode="save" filters={[{ name: "Excel", extensions: ["xlsx"] }]} placeholder="/path/to/结果.xlsx" />
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 4, alignItems: "center" }}>
        <button
          className="btn btn-primary"
          onClick={handleExport}
          disabled={exporting || getExportIds().length === 0}
        >
          {exporting ? "导出中…" : `导出 Excel (${getExportIds().length} 人)`}
        </button>
        {(lastPath || outputPath) && (
          <button className="btn btn-sm" onClick={copyPath}>复制路径</button>
        )}
        {currentProject && !currentProject.has_template && (
          <span className="faint" style={{ color: "var(--warning)" }}>项目未配模板，导出可能失败</span>
        )}
      </div>

      {/* 预览表格 */}
      {preview.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div className="panel-section-title" style={{ marginBottom: 8 }}>导出预览 ({preview.length} 行)</div>
          <div style={{ maxHeight: 400, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 10 }}>
            <table className="export-table">
              <thead>
                <tr>
                  <th>姓名</th>
                  {previewColumns.map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((row) => (
                  <tr key={row.id}>
                    <td style={{ fontWeight: 600 }}>{row.name}</td>
                    {previewColumns.map((col) => {
                      const val = row.fields?.[col];
                      const display = val === "-1" || val === -1 ? "-" : String(val ?? "");
                      return <td key={col} style={{ color: display === "-" ? "var(--text-3)" : "var(--text)" }}>{display}</td>;
                    })}
                    <td>
                      <span style={{
                        fontSize: 10, padding: "2px 6px", borderRadius: 8,
                        background: row.review_status === "done" ? "var(--success-fade)" : "var(--warning-fade)",
                        color: row.review_status === "done" ? "var(--success)" : "var(--warning)",
                      }}>
                        {row.review_status === "done" ? "✓已审" : "!待审"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {completedPatients.length === 0 && (
        <div className="empty-state" style={{ marginTop: 30 }}>
          <div className="empty-icon">📊</div>
          <div className="empty-title">尚无可导出的病人</div>
          <div className="empty-desc">需要先完成抽取才能导出</div>
        </div>
      )}
    </>
  );
}
