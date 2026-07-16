import { useState, useEffect, useRef, useCallback } from "react";
import { useWorkbench } from "../../store/workbench";
import { api } from "../../api/client";

const REGION_COLORS = ["#5b5bd6", "#3dd68c", "#e8a838", "#e5484d", "#6d6de0"];

type Region = { name: string; x1: number; y1: number; x2: number; y2: number };

type DragMode =
  | { type: "draw"; startX: number; startY: number }
  | { type: "move"; idx: number; ox: number; oy: number; origin: Region }
  | { type: "resize"; idx: number; corner: "nw" | "ne" | "sw" | "se"; origin: Region }
  | null;

export default function SliceStage() {
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const runStage = useWorkbench((s) => s.runStage);
  const runningTasks = useWorkbench((s) => s.runningTasks);
  const addToast = useWorkbench((s) => s.addToast);

  const [regions, setRegions] = useState<Region[]>([]);
  const [currentImgIdx, setCurrentImgIdx] = useState(0);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [displaySize, setDisplaySize] = useState({ w: 0, h: 0 });
  const [slicePreviews, setSlicePreviews] = useState<any[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [baseStage, setBaseStage] = useState<"source" | "preprocess">("source");
  const [baseImages, setBaseImages] = useState<{ name: string; relative: string; stage: string }[]>([]);
  const [baseHint, setBaseHint] = useState("区域为病人级模板，套用到全部源图");

  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const dragRef = useRef<DragMode>(null);
  const [draft, setDraft] = useState<Region | null>(null);

  useEffect(() => {
    if (currentPatientId) {
      loadRegions();
      loadBaseImages();
    }
  }, [currentPatientId, patientDetail?.stages?.preprocess?.status]);

  const loadRegions = async () => {
    if (!currentPatientId) return;
    try {
      const result = await api.getSliceRegions(currentPatientId);
      setRegions((result.regions || []) as Region[]);
      setDirty(false);
    } catch {
      setRegions([]);
    }
  };

  const loadBaseImages = async () => {
    if (!currentPatientId) return;
    try {
      const r = await api.getSliceBaseImage(currentPatientId);
      setBaseStage(r.stage);
      setBaseImages(r.images || []);
      setBaseHint(r.hint || "");
    } catch {
      setBaseStage("source");
      setBaseImages([]);
    }
  };

  const measure = useCallback(() => {
    const img = imgRef.current;
    if (!img) return;
    setDisplaySize({ w: img.clientWidth, h: img.clientHeight });
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure, currentImgIdx, imgNatural]);

  const sourceImages = patientDetail?.images || [];
  const editImages = baseImages.length > 0
    ? baseImages
    : sourceImages.map((img: any) => ({ name: img.name, relative: img.name, stage: "source" }));
  const stageStatus = patientDetail?.stages?.["slice"]?.status;
  const isStale = stageStatus === "stale";
  const dataSource = patientDetail?.stages?.source?.data?.data_source || "image";
  const task = currentPatientId ? runningTasks[currentPatientId] : undefined;
  const isRunning = task?.stage === "slice";
  const safeIdx = Math.min(currentImgIdx, Math.max(0, editImages.length - 1));
  const currentImg = editImages[safeIdx];
  const pageCount = editImages.length;
  const regionCount = regions.length;
  const expectedSlices = pageCount * regionCount;

  // 切片完成后自动刷新预览
  useEffect(() => {
    if (!currentPatientId || stageStatus !== "done" || !currentImg?.name) return;
    api.getSlicePreview(currentPatientId, currentImg.name)
      .then((result) => setSlicePreviews(result.slices || []))
      .catch(() => setSlicePreviews([]));
  }, [stageStatus, currentImg?.name, currentPatientId]);

  if (!patientDetail || !currentPatientId) return null;

  if (dataSource === "text" || dataSource === "excel") {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">此病人无需切片</div>
        <div className="empty-desc">
          数据源为 {dataSource === "excel" ? "Excel 拆分" : "文本文件"}，没有图片需要切片。
        </div>
      </div>
    );
  }

  if (editImages.length === 0 && sourceImages.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">无源图片</div>
        <div className="empty-desc">需要先有源图片才能配置切片区域</div>
      </div>
    );
  }

  const scale = imgNatural.w > 0 && displaySize.w > 0 ? displaySize.w / imgNatural.w : 1;

  const toNatural = (clientX: number, clientY: number) => {
    const img = imgRef.current;
    if (!img || !imgNatural.w) return { x: 0, y: 0 };
    const rect = img.getBoundingClientRect();
    const x = Math.round(((clientX - rect.left) / rect.width) * imgNatural.w);
    const y = Math.round(((clientY - rect.top) / rect.height) * imgNatural.h);
    return {
      x: Math.max(0, Math.min(imgNatural.w, x)),
      y: Math.max(0, Math.min(imgNatural.h, y)),
    };
  };

  const normalize = (r: Region): Region => ({
    name: r.name,
    x1: Math.min(r.x1, r.x2),
    y1: Math.min(r.y1, r.y2),
    x2: Math.max(r.x1, r.x2),
    y2: Math.max(r.y1, r.y2),
  });

  const onPointerDown = (e: React.PointerEvent) => {
    if (!imgRef.current || isRunning) return;
    const target = e.target as HTMLElement;
    const handle = target.dataset.handle as "nw" | "ne" | "sw" | "se" | undefined;
    const regionIdx = target.dataset.regionIdx;

    if (handle && regionIdx != null) {
      const idx = Number(regionIdx);
      dragRef.current = { type: "resize", idx, corner: handle, origin: { ...regions[idx] } };
      setSelectedIdx(idx);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }

    if (regionIdx != null) {
      const idx = Number(regionIdx);
      const { x, y } = toNatural(e.clientX, e.clientY);
      dragRef.current = {
        type: "move",
        idx,
        ox: x,
        oy: y,
        origin: { ...regions[idx] },
      };
      setSelectedIdx(idx);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }

    const { x, y } = toNatural(e.clientX, e.clientY);
    dragRef.current = { type: "draw", startX: x, startY: y };
    setDraft({ name: `区域${regions.length + 1}`, x1: x, y1: y, x2: x, y2: y });
    setSelectedIdx(null);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const { x, y } = toNatural(e.clientX, e.clientY);

    if (drag.type === "draw") {
      setDraft({
        name: `区域${regions.length + 1}`,
        x1: drag.startX,
        y1: drag.startY,
        x2: x,
        y2: y,
      });
      return;
    }

    if (drag.type === "move") {
      const dx = x - drag.ox;
      const dy = y - drag.oy;
      const o = drag.origin;
      const w = o.x2 - o.x1;
      const h = o.y2 - o.y1;
      let x1 = o.x1 + dx;
      let y1 = o.y1 + dy;
      x1 = Math.max(0, Math.min(imgNatural.w - w, x1));
      y1 = Math.max(0, Math.min(imgNatural.h - h, y1));
      setRegions((prev) =>
        prev.map((r, i) =>
          i === drag.idx ? { ...r, x1, y1, x2: x1 + w, y2: y1 + h } : r
        )
      );
      setDirty(true);
      return;
    }

    if (drag.type === "resize") {
      const o = { ...drag.origin };
      if (drag.corner.includes("n")) o.y1 = y;
      if (drag.corner.includes("s")) o.y2 = y;
      if (drag.corner.includes("w")) o.x1 = x;
      if (drag.corner.includes("e")) o.x2 = x;
      setRegions((prev) => prev.map((r, i) => (i === drag.idx ? normalize(o) : r)));
      setDirty(true);
    }
  };

  const onPointerUp = () => {
    const drag = dragRef.current;
    if (drag?.type === "draw" && draft) {
      const n = normalize(draft);
      if (Math.abs(n.x2 - n.x1) > 8 && Math.abs(n.y2 - n.y1) > 8) {
        setRegions((prev) => [...prev, n]);
        setSelectedIdx(regions.length);
        setDirty(true);
      }
      setDraft(null);
    }
    dragRef.current = null;
  };

  const handleAddRegion = () => {
    if (!imgNatural.w) return;
    const w = Math.round(imgNatural.w * 0.4);
    const h = Math.round(imgNatural.h * 0.3);
    const x1 = Math.round((imgNatural.w - w) / 2);
    const y1 = Math.round((imgNatural.h - h) / 2);
    const r: Region = {
      name: `区域${regions.length + 1}`,
      x1,
      y1,
      x2: x1 + w,
      y2: y1 + h,
    };
    setRegions([...regions, r]);
    setSelectedIdx(regions.length);
    setDirty(true);
  };

  const handleRemoveRegion = (idx: number) => {
    setRegions(regions.filter((_, i) => i !== idx));
    setSelectedIdx(null);
    setDirty(true);
  };

  const handleUpdateRegion = (idx: number, field: keyof Region, value: string | number) => {
    setRegions(
      regions.map((r, i) => {
        if (i !== idx) return r;
        const next = { ...r, [field]: field === "name" ? value : Number(value) };
        return field === "name" ? next : normalize(next as Region);
      })
    );
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.setSliceRegions(currentPatientId, regions);
      setDirty(false);
      addToast("success", `已保存 ${regions.length} 个切片区域`);
    } catch (e: any) {
      addToast("error", e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    if (regions.length === 0) {
      addToast("warning", "请先框选至少一个区域");
      return;
    }
    if (dirty) {
      try {
        await api.setSliceRegions(currentPatientId, regions);
        setDirty(false);
      } catch (e: any) {
        addToast("error", e.message || "保存失败");
        return;
      }
    }
    runStage(currentPatientId, "slice");
    setSlicePreviews(null);
  };

  const handlePreview = async () => {
    if (!currentImg) return;
    try {
      const result = await api.getSlicePreview(currentPatientId, currentImg.name);
      setSlicePreviews(result.slices || []);
      if (!result.has_slices) addToast("info", "暂无切片结果，请先执行切片");
    } catch {
      setSlicePreviews([]);
    }
  };

  const boxStyle = (r: Region, idx: number, isDraft = false): React.CSSProperties => {
    const left = Math.min(r.x1, r.x2) * scale;
    const top = Math.min(r.y1, r.y2) * scale;
    const width = Math.abs(r.x2 - r.x1) * scale;
    const height = Math.abs(r.y2 - r.y1) * scale;
    const color = REGION_COLORS[idx % REGION_COLORS.length];
    const selected = selectedIdx === idx;
    return {
      position: "absolute",
      left,
      top,
      width,
      height,
      border: `2px solid ${color}`,
      background: isDraft ? `${color}22` : selected ? `${color}28` : `${color}14`,
      boxSizing: "border-box",
      cursor: isDraft ? "crosshair" : "move",
      pointerEvents: isDraft ? "none" : "auto",
    };
  };

  const renderHandles = (idx: number) => {
    if (selectedIdx !== idx) return null;
    const corners: Array<{ k: "nw" | "ne" | "sw" | "se"; style: React.CSSProperties }> = [
      { k: "nw", style: { left: -4, top: -4, cursor: "nwse-resize" } },
      { k: "ne", style: { right: -4, top: -4, cursor: "nesw-resize" } },
      { k: "sw", style: { left: -4, bottom: -4, cursor: "nesw-resize" } },
      { k: "se", style: { right: -4, bottom: -4, cursor: "nwse-resize" } },
    ];
    return corners.map((c) => (
      <div
        key={c.k}
        data-handle={c.k}
        data-region-idx={idx}
        style={{
          position: "absolute",
          width: 8,
          height: 8,
          background: "#fff",
          border: `1.5px solid ${REGION_COLORS[idx % REGION_COLORS.length]}`,
          borderRadius: 1,
          ...c.style,
        }}
      />
    ));
  };

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <div className="h2">切片</div>
        <span className="faint">{regionCount} 个区域</span>
        {regionCount > 0 && pageCount > 0 && (
          <span className="faint">→ OCR 将识 {expectedSlices} 张</span>
        )}
        {baseStage === "preprocess" && (
          <span style={{ fontSize: 11, color: "var(--primary)", padding: "2px 8px", borderRadius: 4, background: "var(--primary-fade)" }}>
            底图：预处理
          </span>
        )}
        {isStale && (
          <span style={{ fontSize: 11, color: "var(--warning)", padding: "2px 8px", borderRadius: 4, background: "var(--warning-fade)" }}>
            上游已变更，建议重切
          </span>
        )}
        {dirty && (
          <span style={{ fontSize: 11, color: "var(--primary)", padding: "2px 8px", borderRadius: 4, background: "var(--primary-fade)" }}>
            未保存
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button className="btn btn-sm" onClick={() => setCurrentImgIdx(Math.max(0, safeIdx - 1))} disabled={safeIdx === 0}>
          ←
        </button>
        <span className="faint">{safeIdx + 1} / {pageCount || 1}</span>
        <button
          className="btn btn-sm"
          onClick={() => setCurrentImgIdx(Math.min(pageCount - 1, safeIdx + 1))}
          disabled={safeIdx >= pageCount - 1}
        >
          →
        </button>
        <button className="btn btn-sm" onClick={handleAddRegion}>+ 区域</button>
        <button className="btn btn-sm" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? "保存中…" : "保存"}
        </button>
        <button className="btn btn-sm btn-primary" onClick={handleRun} disabled={isRunning || regions.length === 0}>
          {isRunning ? "切片中…" : "执行切片"}
        </button>
        <button className="btn btn-sm" onClick={handlePreview}>预览结果</button>
      </div>

      <div className="faint" style={{ marginBottom: 10 }}>
        {baseHint} · 拖拽框选 · 拖动移动 · 拖角缩放 · 切完后 OCR 只识切片
      </div>

      <div style={{ display: "flex", gap: 14, minHeight: 0 }}>
        <div style={{ flex: 1, overflow: "auto", textAlign: "center" }}>
          <div
            ref={wrapRef}
            style={{
              position: "relative",
              display: "inline-block",
              maxWidth: "100%",
              cursor: "crosshair",
              userSelect: "none",
              touchAction: "none",
            }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            <img
              ref={imgRef}
              src={api.imageUrl(
                currentPatientId,
                (currentImg?.stage as string) || baseStage,
                currentImg?.relative || currentImg?.name || "",
              )}
              alt={currentImg?.name}
              draggable={false}
              onLoad={(e) => {
                const el = e.currentTarget;
                setImgNatural({ w: el.naturalWidth, h: el.naturalHeight });
                setDisplaySize({ w: el.clientWidth, h: el.clientHeight });
              }}
              style={{
                maxWidth: "100%",
                maxHeight: "calc(100vh - 260px)",
                objectFit: "contain",
                display: "block",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border)",
                pointerEvents: "none",
              }}
            />
            {regions.map((r, idx) => (
              <div
                key={idx}
                data-region-idx={idx}
                style={boxStyle(r, idx)}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedIdx(idx);
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    top: -18,
                    left: 0,
                    fontSize: 10,
                    fontWeight: 600,
                    color: REGION_COLORS[idx % REGION_COLORS.length],
                    whiteSpace: "nowrap",
                    pointerEvents: "none",
                  }}
                >
                  {r.name}
                </span>
                {renderHandles(idx)}
              </div>
            ))}
            {draft && <div style={boxStyle(draft, regions.length, true)} />}
          </div>
          <div className="faint" style={{ marginTop: 6 }}>
            {currentImg?.name}
            {imgNatural.w > 0 && ` · ${imgNatural.w}×${imgNatural.h}`}
          </div>
        </div>

        <div style={{ width: 280, flexShrink: 0, overflowY: "auto" }}>
          <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
            <span className="h2">区域列表</span>
            <div style={{ flex: 1 }} />
            <button className="btn btn-sm btn-primary" onClick={handleAddRegion}>+</button>
          </div>

          {regions.length === 0 && (
            <div className="faint" style={{ padding: 16, textAlign: "center", border: "1px dashed var(--border)", borderRadius: "var(--radius-md)" }}>
              在左侧图片上拖拽框选，或点 + 添加
            </div>
          )}

          {regions.map((r, idx) => (
            <div
              key={idx}
              onClick={() => setSelectedIdx(idx)}
              style={{
                padding: 10,
                marginBottom: 8,
                borderRadius: "var(--radius-md)",
                background: selectedIdx === idx ? "var(--primary-fade)" : "var(--surface-2)",
                border: `1px solid ${selectedIdx === idx ? REGION_COLORS[idx % REGION_COLORS.length] : "var(--border)"}`,
                borderLeft: `3px solid ${REGION_COLORS[idx % REGION_COLORS.length]}`,
                cursor: "pointer",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <input
                  value={r.name}
                  onChange={(e) => handleUpdateRegion(idx, "name", e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  style={{ flex: 1, fontSize: 12, padding: "3px 6px" }}
                />
                <button
                  className="btn btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemoveRegion(idx);
                  }}
                  style={{ padding: "3px 8px" }}
                >
                  ×
                </button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 11 }}>
                {(["x1", "y1", "x2", "y2"] as const).map((k) => (
                  <label key={k} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span className="faint" style={{ width: 18 }}>{k.toUpperCase()}</span>
                    <input
                      type="number"
                      value={r[k]}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => handleUpdateRegion(idx, k, e.target.value)}
                      style={{ fontSize: 11, padding: "2px 4px" }}
                    />
                  </label>
                ))}
              </div>
              <div className="faint" style={{ marginTop: 4, fontSize: 10 }}>
                {Math.abs(r.x2 - r.x1)} × {Math.abs(r.y2 - r.y1)} px
              </div>
            </div>
          ))}

          {isRunning && task && (
            <div style={{ marginTop: 12, padding: 10, borderRadius: "var(--radius-md)", border: "1px solid var(--primary)", background: "var(--primary-fade)" }}>
              <div style={{ fontSize: 12, color: "var(--primary)", fontWeight: 600 }}>切片进行中</div>
              <div className="progress-bar" style={{ height: 3, marginTop: 6 }}>
                <div className="progress-fill" style={{ width: `${task.total > 0 ? (task.current / task.total) * 100 : 30}%` }} />
              </div>
              <div className="faint" style={{ marginTop: 4 }}>{task.message}</div>
            </div>
          )}

          {slicePreviews && (
            <div style={{ marginTop: 16 }}>
              <div className="panel-section-title">切片结果 · {currentImg?.name}</div>
              {slicePreviews.length === 0 ? (
                <div className="faint">无结果，请先执行切片</div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  {slicePreviews.map((s: any) => (
                    <div key={s.name} style={{ textAlign: "center" }}>
                      <img
                        src={api.imageUrl(currentPatientId, "slice", s.relative)}
                        alt={s.name}
                        style={{ width: "100%", borderRadius: 6, border: "1px solid var(--border)" }}
                      />
                      <div className="faint" style={{ fontSize: 10, marginTop: 2 }}>{s.name}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
