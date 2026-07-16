import { useState, useEffect, useRef, useCallback } from "react";
import { useWorkbench } from "../../store/workbench";
import { api } from "../../api/client";

type CompareMode = "side" | "slider" | "toggle";
type Tab = "compare" | "mask";

type MaskRegion = { x: number; y: number; width: number; height: number; color?: string };

export default function PreprocessStage() {
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const runStage = useWorkbench((s) => s.runStage);
  const runningTasks = useWorkbench((s) => s.runningTasks);
  const addToast = useWorkbench((s) => s.addToast);

  const [tab, setTab] = useState<Tab>("compare");
  const [config, setConfig] = useState<any>(null);
  const [presets, setPresets] = useState<{ key: string; label: string; description: string }[]>([]);
  const [preImages, setPreImages] = useState<any[]>([]);
  const [hasPreprocessed, setHasPreprocessed] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [compareMode, setCompareMode] = useState<CompareMode>("side");
  const [sliderPos, setSliderPos] = useState(50);
  const [toggleShowOriginal, setToggleShowOriginal] = useState(true);
  const [zoom, setZoom] = useState(100);
  const [versions, setVersions] = useState<{ version: string; file_count: number }[]>([]);
  const [restoring, setRestoring] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewMetrics, setPreviewMetrics] = useState<any>(null);
  const [benchRows, setBenchRows] = useState<any[] | null>(null);
  const [benchWinners, setBenchWinners] = useState<Record<string, any>>({});
  const [benching, setBenching] = useState(false);
  const sliderRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getPreprocessCatalog().then((c) => setPresets(c.presets || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (currentPatientId) {
      loadConfig();
      loadImages();
      loadVersions();
    }
  }, [currentPatientId, patientDetail?.stages?.preprocess?.status]);

  const loadConfig = async () => {
    if (!currentPatientId) return;
    try {
      const cfg = await api.getPreprocessConfig(currentPatientId);
      setConfig({
        preset: cfg.preset || "paper_photo",
        ops: cfg.ops,
        mask_regions: cfg.mask_regions || [],
        roi_regions: cfg.roi_regions || [],
        metrics_summary: cfg.metrics_summary || [],
        metrics_score: cfg.metrics_score || {},
      });
    } catch {
      setConfig({
        preset: "paper_photo",
        ops: null,
        mask_regions: [],
        roi_regions: [],
        metrics_summary: [],
        metrics_score: {},
      });
    }
  };

  const loadImages = async () => {
    if (!currentPatientId) return;
    try {
      const result = await api.getPreprocessImages(currentPatientId);
      setPreImages(result.images);
      setHasPreprocessed(result.has_preprocessed);
    } catch {
      setPreImages([]);
      setHasPreprocessed(false);
    }
  };

  const loadVersions = async () => {
    if (!currentPatientId) return;
    try {
      const result = await api.listPreprocessVersions(currentPatientId);
      setVersions(result.versions || []);
    } catch {
      setVersions([]);
    }
  };

  const handleRestore = async (version: string) => {
    if (!currentPatientId) return;
    if (!confirm(`恢复预处理版本 ${version}？当前结果会先自动备份。`)) return;
    setRestoring(true);
    try {
      const r = await api.restorePreprocess(currentPatientId, version);
      addToast("success", `已恢复 ${r.version}（${r.file_count} 个文件）`);
      await loadImages();
      await loadVersions();
    } catch (e: any) {
      addToast("error", e.message || "恢复失败");
    } finally {
      setRestoring(false);
    }
  };

  if (!patientDetail || !currentPatientId) return null;

  const sourceImages = patientDetail.images || [];
  const stageStatus = patientDetail.stages["preprocess"]?.status;
  const isStale = stageStatus === "stale";
  const dataSource = patientDetail.stages?.source?.data?.data_source || "image";
  const task = runningTasks[currentPatientId];
  const isRunning = task?.stage === "preprocess";

  if (dataSource === "text" || dataSource === "excel") {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">此病人无需预处理</div>
        <div className="empty-desc">数据源为文本/Excel，请直接进入合并或抽取。</div>
      </div>
    );
  }

  const handleSaveConfig = async (silent = false) => {
    if (!currentPatientId || !config) return;
    setSaving(true);
    try {
      await api.setPreprocessConfig(currentPatientId, config);
      if (!silent) addToast("success", "预处理配置已保存");
    } catch (e: any) {
      addToast("error", e.message || "保存失败");
      throw e;
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndRun = async () => {
    try {
      await handleSaveConfig(true);
      runStage(currentPatientId, "preprocess");
    } catch { /* toast already */ }
  };

  const handlePreviewOne = async () => {
    if (!currentPatientId || !config) return;
    const name = sourceImages[currentIdx]?.name;
    setPreviewing(true);
    try {
      const r = await api.previewPreprocess(currentPatientId, {
        image_name: name,
        preset: config.preset || "paper_photo",
        ops: config.ops,
        mask_regions: config.mask_regions || [],
      });
      setPreviewMetrics(r);
      addToast(
        r.compare?.verdict === "better" ? "success" : "info",
        `试跑 ${Math.round(r.ms || 0)}ms · ${r.compare?.verdict === "better" ? "指标提升" : r.compare?.verdict === "mixed" ? "有升有降" : "变化不大"}`
      );
    } catch (e: any) {
      addToast("error", e.message || "试跑失败");
    } finally {
      setPreviewing(false);
    }
  };

  const handleBench = async () => {
    if (!currentPatientId) return;
    setBenching(true);
    try {
      const name = sourceImages[currentIdx]?.name;
      const r = await api.benchPreprocess(currentPatientId, {
        image_names: name ? [name] : undefined,
        limit: name ? 1 : 3,
        presets: ["skip", "legacy", "screenshot", "screen_photo", "paper_photo", "handwritten", "watermark_heavy"],
        mask_regions: config?.mask_regions || [],
      });
      setBenchRows(r.rows || []);
      setBenchWinners(r.winners || {});
      const w = name && r.winners?.[name];
      addToast("success", w ? `A/B 完成 · 推荐 ${w.preset} (score ${w.score})` : "A/B 完成");
    } catch (e: any) {
      addToast("error", e.message || "A/B 失败");
    } finally {
      setBenching(false);
    }
  };

  const applyWinnerPreset = () => {
    const name = sourceImages[currentIdx]?.name;
    const w = name ? benchWinners[name] : Object.values(benchWinners)[0];
    if (w?.preset) {
      setConfig((c: any) => ({ ...c, preset: w.preset, ops: null }));
      addToast("info", `已切换预设为 ${w.preset}`);
    }
  };

  const currentSourceImg = sourceImages[currentIdx];
  const currentPreImg = preImages[currentIdx];
  const zoomStyle = { transform: `scale(${zoom / 100})`, transformOrigin: "top center" as const };

  const handleSliderMove = (e: React.MouseEvent | React.TouchEvent) => {
    if (!sliderRef.current) return;
    const rect = sliderRef.current.getBoundingClientRect();
    const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
    const pos = ((clientX - rect.left) / rect.width) * 100;
    setSliderPos(Math.max(0, Math.min(100, pos)));
  };

  const masks: MaskRegion[] = config?.mask_regions || [];
  const score = config?.metrics_score || {};
  const currentPresetMeta = presets.find((p) => p.key === (config?.preset || "paper_photo"));

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <div className="h2">预处理</div>
        {isStale && (
          <span style={{ fontSize: 11, color: "var(--warning)", padding: "2px 8px", borderRadius: 4, background: "var(--warning-fade)" }}>
            源图已变更
          </span>
        )}
        {isRunning && <span style={{ fontSize: 11, color: "var(--primary)" }}>处理中…</span>}
        {(score.better != null) && (
          <span className="faint" style={{ fontSize: 11 }}>
            上次：提升 {score.better || 0} · 持平/变差 {score.worse_or_same || 0}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 4 }}>
          <button className={`btn btn-sm ${tab === "compare" ? "btn-primary" : ""}`} onClick={() => setTab("compare")}>对比</button>
          <button className={`btn btn-sm ${tab === "mask" ? "btn-primary" : ""}`} onClick={() => setTab("mask")}>
            遮罩 ({masks.length})
          </button>
        </div>
        <button className="btn btn-sm" onClick={handlePreviewOne} disabled={previewing || !config || !sourceImages.length}>
          {previewing ? "试跑中…" : "试跑当前页"}
        </button>
        <button className="btn btn-sm" onClick={handleBench} disabled={benching || !sourceImages.length}>
          {benching ? "A/B 中…" : "多预设 A/B"}
        </button>
        <button className="btn btn-sm" onClick={() => handleSaveConfig()} disabled={saving || !config}>
          {saving ? "保存中…" : "保存配置"}
        </button>
        <button className="btn btn-sm btn-primary" onClick={handleSaveAndRun} disabled={isRunning || !config}>
          {isRunning ? "执行中…" : hasPreprocessed ? "重新预处理" : "保存并执行"}
        </button>
      </div>

      {/* 场景预设 */}
      {config && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {(presets.length ? presets : [
            { key: "paper_photo", label: "纸质病历拍照", description: "" },
            { key: "screen_photo", label: "拍摄电子屏", description: "" },
            { key: "screenshot", label: "屏幕截图", description: "" },
            { key: "handwritten", label: "手写病历", description: "" },
            { key: "watermark_heavy", label: "水印较重", description: "" },
            { key: "skip", label: "跳过", description: "" },
          ]).map((p) => (
            <button
              key={p.key}
              className={`btn btn-sm ${config.preset === p.key ? "btn-primary" : ""}`}
              title={p.description}
              onClick={() => setConfig((c: any) => ({ ...c, preset: p.key, ops: null }))}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      {currentPresetMeta && (
        <div className="faint" style={{ marginBottom: 10, fontSize: 12 }}>{currentPresetMeta.description}</div>
      )}
      {config && (
        <div
          className="faint"
          style={{
            marginBottom: 10,
            fontSize: 11,
            padding: "6px 10px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            background: "var(--surface-2)",
            lineHeight: 1.5,
          }}
        >
          OCR 协同：
          {["paper_photo", "handwritten", "watermark_heavy"].includes(config.preset || "")
            ? "本地已做几何/光照增强时，建议 OCR 关闭「文档展平」(useDocUnwarping)，避免双重校正。"
            : config.preset === "skip"
              ? "跳过本地预处理时，纸质拍照可在 OCR 预设中开启展平/朝向。"
              : "截图/拍屏场景一般保持 OCR 展平关闭；版面检测建议开启。"}
        </div>
      )}

      {/* 试跑指标卡 */}
      {previewMetrics && (
        <div
          style={{
            marginBottom: 12,
            padding: 10,
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--surface-2)",
            fontSize: 12,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            试跑 · {previewMetrics.image_name} · {Math.round(previewMetrics.ms || 0)} ms · {previewMetrics.compare?.verdict || "—"}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 6 }}>
            {(["sharpness", "contrast", "brightness", "noise", "skew_deg"] as const).map((k) => {
              const before = previewMetrics.metrics_before?.[k];
              const after = previewMetrics.metrics_after?.[k];
              const d = previewMetrics.compare?.delta?.[k];
              return (
                <span key={k} className="faint">
                  {k}: {before != null ? Number(before).toFixed(1) : "—"}
                  {" → "}
                  {after != null ? Number(after).toFixed(1) : "—"}
                  {d != null && (
                    <span style={{ color: Number(d) > 0 ? "var(--success)" : Number(d) < 0 ? "var(--warning)" : "var(--text-3)" }}>
                      {" "}({Number(d) > 0 ? "+" : ""}{Number(d).toFixed(1)})
                    </span>
                  )}
                </span>
              );
            })}
          </div>
          {previewMetrics.trace?.length > 0 && (
            <div className="faint" style={{ marginBottom: 6 }}>
              算子: {previewMetrics.trace.map((t: any) => `${t.id}${t.ok ? "" : "×"} ${t.ms}ms`).join(" · ")}
            </div>
          )}
          {previewMetrics.preview_relative && currentPatientId && (
            <div style={{ marginTop: 8, maxHeight: 160, overflow: "hidden", display: "flex", gap: 8 }}>
              <img
                src={api.imageUrl(currentPatientId, "preprocess_preview", previewMetrics.preview_relative) + `?t=${Date.now()}`}
                alt="preview"
                style={{ maxHeight: 160, borderRadius: 6, border: "1px solid var(--border)" }}
              />
            </div>
          )}
        </div>
      )}

      {/* 多预设 A/B 表 */}
      {benchRows && benchRows.length > 0 && (
        <div
          style={{
            marginBottom: 12,
            padding: 10,
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--surface-2)",
            fontSize: 12,
            overflowX: "auto",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <div style={{ fontWeight: 600 }}>多预设 A/B</div>
            <div style={{ flex: 1 }} />
            {Object.keys(benchWinners).length > 0 && (
              <button className="btn btn-sm btn-primary" onClick={applyWinnerPreset}>采用推荐预设</button>
            )}
            <button className="btn btn-sm" onClick={() => { setBenchRows(null); setBenchWinners({}); }}>关闭</button>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr className="faint">
                <th style={{ textAlign: "left", padding: "4px 6px" }}>图</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>预设</th>
                <th style={{ textAlign: "right", padding: "4px 6px" }}>ms</th>
                <th style={{ textAlign: "right", padding: "4px 6px" }}>score</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>verdict</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Δ清晰</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Δ噪声</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Δ倾斜</th>
              </tr>
            </thead>
            <tbody>
              {benchRows.map((r, i) => {
                const isWin = r.ok && benchWinners[r.image]?.preset === r.preset;
                return (
                  <tr
                    key={i}
                    style={{
                      background: isWin ? "var(--success-fade, rgba(34,197,94,0.12))" : "transparent",
                      cursor: r.ok ? "pointer" : "default",
                    }}
                    onClick={() => {
                      if (r.ok) setConfig((c: any) => ({ ...c, preset: r.preset, ops: null }));
                    }}
                    title={r.ok ? "点击采用该预设" : r.error}
                  >
                    <td style={{ padding: "4px 6px" }}>{r.image}</td>
                    <td style={{ padding: "4px 6px" }}>{r.preset}{isWin ? " ★" : ""}</td>
                    <td style={{ padding: "4px 6px", textAlign: "right" }}>{r.ok ? Math.round(r.ms || 0) : "—"}</td>
                    <td style={{ padding: "4px 6px", textAlign: "right" }}>{r.ok ? r.score : "—"}</td>
                    <td style={{ padding: "4px 6px" }}>{r.ok ? r.verdict : r.error || "fail"}</td>
                    <td style={{ padding: "4px 6px" }}>{r.delta?.sharpness != null ? (r.delta.sharpness > 0 ? "+" : "") + r.delta.sharpness : "—"}</td>
                    <td style={{ padding: "4px 6px" }}>{r.delta?.noise != null ? (r.delta.noise > 0 ? "+" : "") + r.delta.noise : "—"}</td>
                    <td style={{ padding: "4px 6px" }}>{r.delta?.skew_deg != null ? (r.delta.skew_deg > 0 ? "+" : "") + r.delta.skew_deg : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 上次批量指标摘要 */}
      {config?.metrics_summary?.length > 0 && !benchRows && (
        <div className="faint" style={{ marginBottom: 10, fontSize: 11 }}>
          上次执行样例：
          {config.metrics_summary.slice(0, 3).map((m: any, i: number) => (
            <span key={i} style={{ marginLeft: 8 }}>
              {m.file} · {m.verdict || "—"} · {m.ms != null ? `${Math.round(m.ms)}ms` : ""}
            </span>
          ))}
        </div>
      )}

      {tab === "mask" ? (
        <MaskCanvas
          patientId={currentPatientId}
          imageName={currentSourceImg?.name || ""}
          images={sourceImages}
          currentIdx={currentIdx}
          onIdx={setCurrentIdx}
          regions={masks}
          onChange={(regions) => setConfig((c: any) => ({ ...c, mask_regions: regions }))}
          onSave={() => handleSaveConfig()}
        />
      ) : !hasPreprocessed ? (
        <div className="empty-state">
          <div className="empty-icon">·</div>
          <div className="empty-title">尚未预处理</div>
          <div className="empty-desc">选场景预设 → 可先「试跑当前页」看指标 → 再「保存并执行」</div>
          {config && (
            <div style={{ marginTop: 16, fontSize: 12, color: "var(--text-2)", textAlign: "left" }}>
              <div>预设：{config.preset || "paper_photo"}</div>
              <div>遮罩 {masks.length} 个</div>
            </div>
          )}
          <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={handleSaveAndRun} disabled={isRunning}>
            保存并执行
          </button>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            {versions.length > 0 && (
              <>
                <span className="faint">历史:</span>
                {versions.slice(0, 5).map((v) => (
                  <button key={v.version} className="btn btn-sm" disabled={restoring} onClick={() => handleRestore(v.version)}>
                    {v.version}
                  </button>
                ))}
              </>
            )}
            <div style={{ flex: 1 }} />
            <button className="btn btn-sm" onClick={() => setCurrentIdx(Math.max(0, currentIdx - 1))} disabled={currentIdx === 0}>←</button>
            <span className="faint">{currentIdx + 1} / {sourceImages.length}</span>
            <button className="btn btn-sm" onClick={() => setCurrentIdx(Math.min(sourceImages.length - 1, currentIdx + 1))} disabled={currentIdx >= sourceImages.length - 1}>→</button>
          </div>

          <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
            {([
              { key: "side", label: "并排" },
              { key: "slider", label: "滑动" },
              { key: "toggle", label: "切换" },
            ] as const).map((m) => (
              <button key={m.key} className={`btn btn-sm ${compareMode === m.key ? "btn-primary" : ""}`} onClick={() => setCompareMode(m.key)}>
                {m.label}
              </button>
            ))}
            <div style={{ flex: 1 }} />
            <button className="btn btn-sm" onClick={() => setZoom(Math.max(25, zoom - 25))}>-</button>
            <span className="faint">{zoom}%</span>
            <button className="btn btn-sm" onClick={() => setZoom(Math.min(400, zoom + 25))}>+</button>
            <button className="btn btn-sm" onClick={() => setZoom(100)}>100%</button>
          </div>

          <div style={{ display: "flex", gap: 12, justifyContent: "center", overflow: "auto" }}>
            {compareMode === "side" && (
              <>
                <div style={{ flex: 1, textAlign: "center" }}>
                  <div className="faint" style={{ marginBottom: 6 }}>原始</div>
                  <div style={zoomStyle}>
                    <img
                      src={api.imageUrl(currentPatientId, "source", currentSourceImg?.name || "")}
                      style={{ maxWidth: "100%", maxHeight: "calc(100vh - 300px)", objectFit: "contain", borderRadius: 8, border: "1px solid var(--border)" }}
                      alt="原图"
                    />
                  </div>
                </div>
                <div style={{ flex: 1, textAlign: "center" }}>
                  <div className="faint" style={{ marginBottom: 6 }}>处理后</div>
                  <div style={zoomStyle}>
                    <img
                      src={api.imageUrl(currentPatientId, "preprocess", currentPreImg?.name || currentSourceImg?.name || "")}
                      style={{ maxWidth: "100%", maxHeight: "calc(100vh - 300px)", objectFit: "contain", borderRadius: 8, border: "1px solid var(--border)" }}
                      alt="处理后"
                    />
                  </div>
                </div>
              </>
            )}

            {compareMode === "slider" && (
              <div
                ref={sliderRef}
                style={{ position: "relative", width: "100%", maxWidth: 640 * (zoom / 100), overflow: "hidden", borderRadius: 8, border: "1px solid var(--border)", cursor: "ew-resize" }}
                onMouseMove={(e) => e.buttons === 1 && handleSliderMove(e)}
                onMouseDown={handleSliderMove}
              >
                <img src={api.imageUrl(currentPatientId, "preprocess", currentPreImg?.name || currentSourceImg?.name || "")} style={{ width: "100%", display: "block" }} alt="处理后" />
                <div style={{ position: "absolute", top: 0, left: 0, height: "100%", width: `${sliderPos}%`, overflow: "hidden" }}>
                  <img
                    src={api.imageUrl(currentPatientId, "source", currentSourceImg?.name || "")}
                    style={{ width: sliderRef.current?.offsetWidth || 600, maxWidth: "none", display: "block" }}
                    alt="原图"
                  />
                </div>
                <div style={{ position: "absolute", top: 0, bottom: 0, left: `${sliderPos}%`, width: 2, background: "var(--primary)" }} />
              </div>
            )}

            {compareMode === "toggle" && (
              <div style={{ textAlign: "center", flex: 1 }}>
                <div className="faint" style={{ marginBottom: 6 }}>{toggleShowOriginal ? "原始" : "处理后"} · 双击切换</div>
                <div style={zoomStyle}>
                  <img
                    src={toggleShowOriginal
                      ? api.imageUrl(currentPatientId, "source", currentSourceImg?.name || "")
                      : api.imageUrl(currentPatientId, "preprocess", currentPreImg?.name || currentSourceImg?.name || "")}
                    style={{ maxWidth: "100%", maxHeight: "calc(100vh - 300px)", objectFit: "contain", borderRadius: 8, border: "1px solid var(--border)" }}
                    alt="对比"
                    onDoubleClick={() => setToggleShowOriginal(!toggleShowOriginal)}
                  />
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}

/** 应用内遮罩框选（像素坐标 x,y,width,height） */
function MaskCanvas({
  patientId,
  imageName,
  images,
  currentIdx,
  onIdx,
  regions,
  onChange,
  onSave,
}: {
  patientId: string;
  imageName: string;
  images: { name: string }[];
  currentIdx: number;
  onIdx: (i: number) => void;
  regions: MaskRegion[];
  onChange: (r: MaskRegion[]) => void;
  onSave: () => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [natural, setNatural] = useState({ w: 0, h: 0 });
  const [display, setDisplay] = useState({ w: 0, h: 0 });
  const [selected, setSelected] = useState<number | null>(null);
  const dragRef = useRef<
    | { type: "draw"; x: number; y: number }
    | { type: "move"; idx: number; ox: number; oy: number; origin: MaskRegion }
    | null
  >(null);
  const [draft, setDraft] = useState<MaskRegion | null>(null);

  const measure = useCallback(() => {
    const img = imgRef.current;
    if (img) setDisplay({ w: img.clientWidth, h: img.clientHeight });
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure, natural, imageName]);

  const scale = natural.w > 0 && display.w > 0 ? display.w / natural.w : 1;

  const toNat = (cx: number, cy: number) => {
    const img = imgRef.current;
    if (!img || !natural.w) return { x: 0, y: 0 };
    const rect = img.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(natural.w, Math.round(((cx - rect.left) / rect.width) * natural.w))),
      y: Math.max(0, Math.min(natural.h, Math.round(((cy - rect.top) / rect.height) * natural.h))),
    };
  };

  const onDown = (e: React.PointerEvent) => {
    const t = e.target as HTMLElement;
    const idxAttr = t.dataset.maskIdx;
    if (idxAttr != null) {
      const idx = Number(idxAttr);
      const { x, y } = toNat(e.clientX, e.clientY);
      dragRef.current = { type: "move", idx, ox: x, oy: y, origin: { ...regions[idx] } };
      setSelected(idx);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    const { x, y } = toNat(e.clientX, e.clientY);
    dragRef.current = { type: "draw", x, y };
    setDraft({ x, y, width: 0, height: 0, color: "white" });
    setSelected(null);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const { x, y } = toNat(e.clientX, e.clientY);
    if (d.type === "draw") {
      setDraft({
        x: Math.min(d.x, x),
        y: Math.min(d.y, y),
        width: Math.abs(x - d.x),
        height: Math.abs(y - d.y),
        color: "white",
      });
    } else {
      const dx = x - d.ox;
      const dy = y - d.oy;
      const o = d.origin;
      onChange(
        regions.map((r, i) =>
          i === d.idx
            ? {
                ...r,
                x: Math.max(0, Math.min(natural.w - r.width, o.x + dx)),
                y: Math.max(0, Math.min(natural.h - r.height, o.y + dy)),
              }
            : r
        )
      );
    }
  };

  const onUp = () => {
    const d = dragRef.current;
    if (d?.type === "draw" && draft && draft.width > 8 && draft.height > 8) {
      onChange([...regions, draft]);
      setSelected(regions.length);
    }
    setDraft(null);
    dragRef.current = null;
  };

  const boxStyle = (r: MaskRegion, idx: number): React.CSSProperties => ({
    position: "absolute",
    left: r.x * scale,
    top: r.y * scale,
    width: r.width * scale,
    height: r.height * scale,
    border: `2px solid ${selected === idx ? "var(--warning)" : "var(--error)"}`,
    background: "rgba(255,255,255,0.55)",
    boxSizing: "border-box",
    cursor: "move",
  });

  return (
    <div style={{ display: "flex", gap: 14 }}>
      <div style={{ flex: 1, textAlign: "center" }}>
        <div className="faint" style={{ marginBottom: 8 }}>在图上拖拽框选隐私区域（保存后执行预处理生效）</div>
        <div
          style={{ position: "relative", display: "inline-block", cursor: "crosshair", userSelect: "none", touchAction: "none" }}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
        >
          <img
            ref={imgRef}
            src={api.imageUrl(patientId, "source", imageName)}
            alt={imageName}
            draggable={false}
            onLoad={(e) => {
              const el = e.currentTarget;
              setNatural({ w: el.naturalWidth, h: el.naturalHeight });
              setDisplay({ w: el.clientWidth, h: el.clientHeight });
            }}
            style={{
              maxWidth: "100%",
              maxHeight: "calc(100vh - 280px)",
              objectFit: "contain",
              display: "block",
              borderRadius: 8,
              border: "1px solid var(--border)",
              pointerEvents: "none",
            }}
          />
          {regions.map((r, i) => (
            <div key={i} data-mask-idx={i} style={boxStyle(r, i)} onClick={(e) => { e.stopPropagation(); setSelected(i); }} />
          ))}
          {draft && <div style={{ ...boxStyle(draft, -1), pointerEvents: "none", borderStyle: "dashed" }} />}
        </div>
        <div style={{ marginTop: 8, justifyContent: "center", display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn btn-sm" disabled={currentIdx === 0} onClick={() => onIdx(currentIdx - 1)}>←</button>
          <span className="faint">{currentIdx + 1}/{images.length} · {imageName}</span>
          <button className="btn btn-sm" disabled={currentIdx >= images.length - 1} onClick={() => onIdx(currentIdx + 1)}>→</button>
        </div>
      </div>
      <div style={{ width: 240, flexShrink: 0 }}>
        <div className="h2" style={{ marginBottom: 8 }}>遮罩列表 ({regions.length})</div>
        {regions.length === 0 && <div className="faint">暂无遮罩，在左侧拖拽添加</div>}
        {regions.map((r, i) => (
          <div
            key={i}
            onClick={() => setSelected(i)}
            style={{
              padding: 8, marginBottom: 6, borderRadius: 6,
              border: `1px solid ${selected === i ? "var(--warning)" : "var(--border)"}`,
              background: "var(--surface-2)", fontSize: 11, cursor: "pointer",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span>区域 {i + 1}</span>
              <button className="btn btn-sm" style={{ padding: "2px 6px" }} onClick={(e) => { e.stopPropagation(); onChange(regions.filter((_, j) => j !== i)); }}>×</button>
            </div>
            <div className="faint">{r.width}×{r.height} @ ({r.x},{r.y})</div>
          </div>
        ))}
        <button className="btn btn-sm btn-primary" style={{ width: "100%", marginTop: 8 }} onClick={onSave}>保存遮罩</button>
      </div>
    </div>
  );
}
