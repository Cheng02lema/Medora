import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import { locateBlockInText, splitByRange, type TextRange } from "./locateBlockInText";
import { countDiffStats, diffLines, type DiffLine } from "./textDiff";

export type ReviewPage = {
  page: string;
  text: string;
  char_count?: number;
  source_stage?: string;
  source_relative?: string;
  source_image?: string;
  parent_page?: string;
  region_name?: string;
  display_label?: string;
  has_layout?: boolean;
  image_source?: string;
  slice_base_stage?: string;
};

type LayoutBlock = {
  id: number;
  label: string;
  text: string;
  bbox: number[];
  noise?: boolean;
  empty?: boolean;
};

type LayoutCache = {
  blocks: LayoutBlock[];
  image: { stage?: string; relative?: string; name?: string; width?: number; height?: number };
  has_layout: boolean;
  message?: string;
};

function resolveImage(page: ReviewPage, layout?: LayoutCache) {
  if (layout?.image?.relative || layout?.image?.name) {
    return {
      stage: layout.image.stage || page.source_stage || "source",
      file: layout.image.relative || layout.image.name || "",
    };
  }
  if (page.source_stage && (page.source_relative || page.source_image)) {
    return {
      stage: page.source_stage,
      file: page.source_relative || page.source_image || "",
    };
  }
  const base = (page.page || "").replace(/_\d+$/, "");
  if (base.includes("__")) {
    const parent = base.split("__")[0];
    return { stage: "slice", file: `${parent}/${base}.jpg` };
  }
  return { stage: "source", file: `${base}.jpg` };
}

function stageLabel(stage: string) {
  if (stage === "slice") return "切片图";
  if (stage === "preprocess") return "预处理图";
  return "源图";
}

export default function OcrReviewView({
  patientId,
  pages,
  initialPage,
  onBack,
  onRerunPage,
  onSavePage,
  addToast,
}: {
  patientId: string;
  pages: ReviewPage[];
  initialPage?: string | null;
  onBack: () => void;
  onRerunPage?: (pageName: string) => void;
  /** 保存单页 OCR 文本；返回 Promise */
  onSavePage?: (pageName: string, text: string) => Promise<void>;
  addToast?: (type: "success" | "error" | "info" | "warning", msg: string) => void;
}) {
  const safePages = Array.isArray(pages) ? pages : [];
  const initialIdx = (() => {
    if (!initialPage) return 0;
    const i = safePages.findIndex((p) => p.page === initialPage);
    return i >= 0 ? i : 0;
  })();
  const [pageIdx, setPageIdx] = useState(initialIdx);
  const [cache, setCache] = useState<Record<string, LayoutCache>>({});
  const [loading, setLoading] = useState(false);
  const [activeBlockId, setActiveBlockId] = useState<number | null>(null);
  const [showAllBoxes, setShowAllBoxes] = useState(true);
  const [hideNoise, setHideNoise] = useState(true);
  const [textRange, setTextRange] = useState<TextRange | null>(null);
  // baseline = 进入审查时的快照（整段会话不变，用于退出 diff / 还原）
  // draft = 当前编辑内容；saved 后仍相对 baseline 显示对照
  const [baselineMap] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const p of safePages) m[p.page] = p.text || "";
    return m;
  });
  const [draftMap, setDraftMap] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const p of safePages) m[p.page] = p.text || "";
    return m;
  });
  // 已成功写盘的版本（用于判断「未保存到磁盘」）
  const [diskMap, setDiskMap] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const p of safePages) m[p.page] = p.text || "";
    return m;
  });
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exitDiffOpen, setExitDiffOpen] = useState(false);
  const textPaneRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const pageCount = safePages.length;
  const safeIdx = pageCount > 0 ? Math.min(pageIdx, pageCount - 1) : 0;
  const page = safePages[safeIdx];
  const layout = page ? cache[page.page] : undefined;
  const pageText = page ? (draftMap[page.page] ?? page.text ?? "") : "";
  const pageBaseline = page ? (baselineMap[page.page] ?? page.text ?? "") : "";
  const pageDisk = page ? (diskMap[page.page] ?? page.text ?? "") : "";
  // 相对进入审查时有改动（含已点「保存本页」的）
  const pageChangedFromBaseline = page ? pageText !== pageBaseline : false;
  // 相对磁盘未写盘
  const pageUnsavedToDisk = page ? pageText !== pageDisk : false;
  const changedPages = useMemo(
    () => safePages.filter((p) => (draftMap[p.page] ?? "") !== (baselineMap[p.page] ?? "")),
    [safePages, draftMap, baselineMap],
  );
  const unsavedToDiskPages = useMemo(
    () => safePages.filter((p) => (draftMap[p.page] ?? "") !== (diskMap[p.page] ?? "")),
    [safePages, draftMap, diskMap],
  );
  const changedCount = changedPages.length;
  const unsavedCount = unsavedToDiskPages.length;

  const loadingRef = useRef<Set<string>>(new Set());
  const cacheRef = useRef(cache);
  cacheRef.current = cache;
  const pageKeys = useMemo(() => safePages.map((p) => p.page).join("\0"), [safePages]);

  const loadLayout = useCallback(async (pageName: string) => {
    if (!pageName || !patientId) return;
    if (cacheRef.current[pageName] || loadingRef.current.has(pageName)) return;
    loadingRef.current.add(pageName);
    setLoading(true);
    try {
      const r = await api.getOcrPageLayout(patientId, pageName);
      setCache((p) => ({
        ...p,
        [pageName]: {
          blocks: Array.isArray(r.blocks) ? r.blocks : [],
          image: r.image || {},
          has_layout: !!r.has_layout,
          message: r.message,
        },
      }));
    } catch (e: any) {
      setCache((p) => ({
        ...p,
        [pageName]: {
          blocks: [],
          image: {},
          has_layout: false,
          message: e?.message || "加载版面失败",
        },
      }));
    } finally {
      loadingRef.current.delete(pageName);
      setLoading(loadingRef.current.size > 0);
    }
  }, [patientId]);

  useEffect(() => {
    if (!page?.page) return;
    setActiveBlockId(null);
    setTextRange(null);
    void loadLayout(page.page);
    const prev = safePages[safeIdx - 1]?.page;
    const next = safePages[safeIdx + 1]?.page;
    if (prev) void loadLayout(prev);
    if (next) void loadLayout(next);
    // 仅依赖页 key 串，避免 pages 引用变化导致死循环
  }, [page?.page, safeIdx, pageKeys, loadLayout]);

  const blocks = useMemo(() => {
    const all = layout?.blocks || [];
    return hideNoise ? all.filter((b) => !b.noise) : all;
  }, [layout, hideNoise]);

  const selectBlock = useCallback(
    (id: number | null) => {
      setActiveBlockId(id);
      if (id == null || !page) {
        setTextRange(null);
        return;
      }
      if (editing) return; // 编辑中不抢光标
      const block = (layout?.blocks || []).find((b) => b.id === id);
      if (!block) {
        setTextRange(null);
        return;
      }
      try {
        const range = locateBlockInText(pageText, block.text || "");
        setTextRange(range);
        if (!range) {
          addToast?.("info", "无法对齐到文本（可能已人工编辑）");
        }
      } catch {
        setTextRange(null);
      }
    },
    [page, layout, addToast, pageText, editing],
  );

  const setDraft = (text: string) => {
    if (!page) return;
    setDraftMap((m) => ({ ...m, [page.page]: text }));
  };

  const handleSaveCurrent = async () => {
    if (!page || !onSavePage) {
      addToast?.("warning", "无法保存");
      return;
    }
    if (!pageUnsavedToDisk) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSavePage(page.page, pageText);
      setDiskMap((m) => ({ ...m, [page.page]: pageText }));
      setEditing(false);
      addToast?.("success", "本页已写入磁盘（退出时仍可对照进入审查前版本）");
    } catch (e: any) {
      addToast?.("error", e?.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    if (!page) return;
    // 取消编辑：回到磁盘版（不是 baseline），避免误丢已保存内容
    setDraftMap((m) => ({ ...m, [page.page]: diskMap[page.page] ?? page.text ?? "" }));
    setEditing(false);
    setTextRange(null);
  };

  /** 还原到进入审查时的版本 */
  const restorePageToBaseline = (pageName: string) => {
    setDraftMap((m) => ({ ...m, [pageName]: baselineMap[pageName] ?? "" }));
  };

  const restoreAllToBaseline = () => {
    setDraftMap({ ...baselineMap });
    setEditing(false);
  };

  const openDiff = () => {
    setEditing(false);
    setExitDiffOpen(true);
  };

  const requestBack = () => {
    setEditing(false);
    // 相对进入审查有任何改动（含已保存到磁盘的）→ 出 diff
    if (changedCount > 0 || unsavedCount > 0) {
      setExitDiffOpen(true);
      return;
    }
    onBack();
  };

  const confirmExitSaveAll = async () => {
    if (!onSavePage) {
      onBack();
      return;
    }
    setSaving(true);
    try {
      const toWrite = unsavedToDiskPages.length ? unsavedToDiskPages : changedPages;
      for (const p of toWrite) {
        const text = draftMap[p.page] ?? "";
        if (text !== (diskMap[p.page] ?? "")) {
          await onSavePage(p.page, text);
        }
      }
      setDiskMap({ ...draftMap });
      setExitDiffOpen(false);
      addToast?.("success", `已保存修改并退出`);
      onBack();
    } catch (e: any) {
      addToast?.("error", e?.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  /** 丢弃：草稿回到 baseline，若磁盘已是改过的则写回 baseline */
  const confirmExitDiscardAll = async () => {
    setSaving(true);
    try {
      if (onSavePage) {
        for (const p of safePages) {
          const base = baselineMap[p.page] ?? "";
          const disk = diskMap[p.page] ?? "";
          if (disk !== base) {
            await onSavePage(p.page, base);
          }
        }
      }
      restoreAllToBaseline();
      setDiskMap({ ...baselineMap });
      setExitDiffOpen(false);
      addToast?.("info", "已还原为进入审查前的版本");
      onBack();
    } catch (e: any) {
      addToast?.("error", e?.message || "还原失败");
    } finally {
      setSaving(false);
    }
  };

  const tryChangePage = (nextIdx: number) => {
    if (nextIdx === pageIdx) return;
    if (editing && pageUnsavedToDisk) {
      if (!confirm("本页有未写入磁盘的修改，切换将保留草稿。继续？")) {
        return;
      }
      setEditing(false);
    } else {
      setEditing(false);
    }
    setPageIdx(nextIdx);
  };

  useEffect(() => {
    if (!textRange) return;
    // 下一帧再滚，等 mark 挂载
    const t = requestAnimationFrame(() => {
      markRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    return () => cancelAnimationFrame(t);
  }, [textRange, safeIdx, activeBlockId]);

  // 键盘
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const inField = tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable;

      if ((e.metaKey || e.ctrlKey) && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        if (editing || pageUnsavedToDisk) void handleSaveCurrent();
        return;
      }

      if (inField) {
        if (e.key === "Escape") {
          e.preventDefault();
          if (editing) handleCancelEdit();
          else requestBack();
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        if (exitDiffOpen) setExitDiffOpen(false);
        else requestBack();
        return;
      }
      if (exitDiffOpen) return;
      if (e.key === "j" || e.key === "J" || e.key === "ArrowRight") {
        e.preventDefault();
        tryChangePage(Math.min(Math.max(0, pageCount - 1), pageIdx + 1));
        return;
      }
      if (e.key === "k" || e.key === "K" || e.key === "ArrowLeft") {
        e.preventDefault();
        tryChangePage(Math.max(0, pageIdx - 1));
        return;
      }
      if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        setEditing(true);
        setTimeout(() => textareaRef.current?.focus(), 0);
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!blocks.length || editing) return;
        const idx = blocks.findIndex((b) => b.id === activeBlockId);
        if (e.key === "ArrowDown") {
          const next = idx < 0 ? 0 : Math.min(blocks.length - 1, idx + 1);
          selectBlock(blocks[next].id);
        } else {
          const prev = idx < 0 ? blocks.length - 1 : Math.max(0, idx - 1);
          selectBlock(blocks[prev].id);
        }
        return;
      }
      if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        setShowAllBoxes((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pageCount, pageIdx, blocks, activeBlockId, selectBlock, editing, exitDiffOpen, pageUnsavedToDisk, changedCount]);

  if (!pageCount || !page) {
    return (
      <div className="empty-state">
        <div className="empty-title">无可审查页</div>
        <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={onBack}>返回列表</button>
      </div>
    );
  }

  const img = resolveImage(page, layout);
  const imageSrc = api.imageUrl(patientId, img.stage || "source", img.file || "");
  const activeBlock = blocks.find((b) => b.id === activeBlockId);
  const layoutReady = !!layout?.has_layout && blocks.length > 0;
  let textParts: { type: "text" | "mark"; value: string }[] = [{ type: "text", value: pageText }];
  try {
    textParts = splitByRange(pageText, textRange);
  } catch {
    textParts = [{ type: "text", value: pageText }];
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 140px)", minHeight: 480 }}>
      {/* 顶栏 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <button className="btn btn-sm" onClick={requestBack}>← 返回列表</button>
        <div className="h2" style={{ margin: 0 }}>OCR 审查</div>
        <span className="faint">
          {safeIdx + 1} / {pageCount}
          {page.display_label || page.region_name
            ? ` · ${page.display_label || `${page.parent_page || ""} · ${page.region_name}`}`
            : ` · ${page.page}`}
        </span>
        <span className="faint">
          定位图：{stageLabel(img.stage)}
          {page.slice_base_stage ? `（底图=${stageLabel(page.slice_base_stage)}）` : ""}
        </span>
        {pageUnsavedToDisk && (
          <span style={{ fontSize: 11, color: "var(--warning)", padding: "2px 8px", borderRadius: 4, background: "var(--warning-fade)" }}>
            本页未写盘
          </span>
        )}
        {!pageUnsavedToDisk && pageChangedFromBaseline && (
          <span style={{ fontSize: 11, color: "var(--primary)", padding: "2px 8px", borderRadius: 4, background: "var(--primary-fade)" }}>
            本页已改（相对进入时）
          </span>
        )}
        {changedCount > 0 && (
          <span className="faint" style={{ fontSize: 11 }}>改动 {changedCount} 页</span>
        )}
        {loading && <span className="faint">加载中…</span>}
        <div style={{ flex: 1 }} />
        <button
          className="btn btn-sm"
          onClick={openDiff}
          disabled={changedCount === 0}
          title={changedCount === 0 ? "暂无相对进入审查时的改动" : "查看行级 diff，可还原"}
          style={changedCount > 0 ? { borderColor: "var(--warning)", color: "var(--warning)" } : undefined}
        >
          修改对照{changedCount > 0 ? ` (${changedCount})` : ""}
        </button>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, cursor: "pointer" }}>
          <input type="checkbox" checked={hideNoise} onChange={(e) => setHideNoise(e.target.checked)} style={{ width: "auto" }} />
          隐藏页眉页脚
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, cursor: "pointer" }}>
          <input type="checkbox" checked={showAllBoxes} onChange={(e) => setShowAllBoxes(e.target.checked)} style={{ width: "auto" }} />
          显示全部框
        </label>
        {page.page && onRerunPage && (
          <button className="btn btn-sm" onClick={() => onRerunPage(page.page)}>重识别本页</button>
        )}
      </div>

      <div className="faint" style={{ fontSize: 11, marginBottom: 8 }}>
        点图定位 · E 编辑 · ⌘/Ctrl+S 写盘 · 「修改对照」看 diff 可还原 · 返回列表有改动也会弹对照
      </div>

      {/* 胶片条 */}
      <div
        style={{
          display: "flex",
          gap: 6,
          overflowX: "auto",
          paddingBottom: 8,
          marginBottom: 10,
          borderBottom: "1px solid var(--border)",
        }}
      >
        {safePages.map((p, i) => {
          const c = cache[p.page];
          const has = c ? c.has_layout : p.has_layout;
          const active = i === safeIdx;
          const thumb = resolveImage(p, c);
          return (
            <button
              key={p.page || `p-${i}`}
              type="button"
              onClick={() => tryChangePage(i)}
              title={p.display_label || p.page}
              style={{
                flexShrink: 0,
                width: 56,
                padding: 0,
                border: `2px solid ${active ? "var(--primary)" : "var(--border)"}`,
                borderRadius: 6,
                overflow: "hidden",
                background: "var(--surface-2)",
                cursor: "pointer",
                position: "relative",
              }}
            >
              <img
                src={api.thumbUrl(patientId, thumb.stage || "source", thumb.file || "")}
                alt=""
                style={{ width: "100%", height: 64, objectFit: "cover", display: "block" }}
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = "0.3"; }}
              />
              <span
                style={{
                  position: "absolute",
                  top: 2,
                  right: 2,
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: has ? "var(--success)" : "var(--text-3)",
                }}
              />
              <div style={{ fontSize: 9, padding: "1px 2px", color: "var(--text-3)" }}>{i + 1}</div>
            </button>
          );
        })}
      </div>

      {!layoutReady && !loading && (
        <div
          style={{
            marginBottom: 10,
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid var(--warning)",
            background: "var(--warning-fade)",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span>{layout?.message || "本页无版面数据，请重新 OCR 以启用图上定位"}</span>
          {onRerunPage && page && (
            <button className="btn btn-sm btn-primary" onClick={() => onRerunPage(page.page)}>重识别</button>
          )}
        </div>
      )}

      {/* 主区 */}
      <div style={{ display: "flex", gap: 12, flex: 1, minHeight: 0 }}>
        <div style={{ flex: "1 1 58%", minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column" }}>
          <ReviewCanvas
            imageSrc={imageSrc}
            blocks={blocks}
            imageWidth={layout?.image?.width || 0}
            imageHeight={layout?.image?.height || 0}
            activeId={activeBlockId}
            showAll={showAllBoxes}
            onSelect={selectBlock}
          />
        </div>

        <div
          style={{
            flex: "1 1 42%",
            minWidth: 240,
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
            border: "1px solid var(--border)",
            borderRadius: 8,
            background: "var(--surface-2)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "8px 12px",
              borderBottom: "1px solid var(--border)",
              fontSize: 12,
              fontWeight: 600,
              display: "flex",
              gap: 8,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <span>识别文本</span>
            <span className="faint" style={{ fontWeight: 400 }}>
              {pageText.length} 字
              {activeBlock ? ` · 块 #${activeBlock.id}` : ""}
              {pageUnsavedToDisk ? " · 未写盘" : pageChangedFromBaseline ? " · 已改" : ""}
            </span>
            <div style={{ flex: 1 }} />
            {!editing ? (
              <button
                className="btn btn-sm btn-primary"
                onClick={() => {
                  setEditing(true);
                  setTimeout(() => textareaRef.current?.focus(), 0);
                }}
              >
                编辑
              </button>
            ) : (
              <>
                <button className="btn btn-sm btn-primary" disabled={saving || !pageUnsavedToDisk} onClick={() => void handleSaveCurrent()}>
                  {saving ? "保存中…" : "写入本页"}
                </button>
                <button className="btn btn-sm" disabled={saving} onClick={handleCancelEdit}>取消编辑</button>
              </>
            )}
          </div>
          {activeBlock && !editing && (
            <div
              style={{
                padding: "6px 12px",
                fontSize: 11,
                color: "var(--text-2)",
                borderBottom: "1px solid var(--border)",
                background: "var(--warning-fade)",
              }}
            >
              {(activeBlock.text || "(空)").slice(0, 160)}
              {(activeBlock.text || "").length > 160 ? "…" : ""}
            </div>
          )}
          {editing ? (
            <textarea
              ref={textareaRef}
              value={pageText}
              onChange={(e) => setDraft(e.target.value)}
              style={{
                flex: 1,
                width: "100%",
                border: "none",
                outline: "none",
                resize: "none",
                padding: 12,
                fontSize: 13,
                lineHeight: 1.65,
                fontFamily: "inherit",
                background: "var(--surface)",
                color: "var(--text)",
              }}
              placeholder="在此修改本页 OCR 全文…"
            />
          ) : (
            <div
              ref={textPaneRef}
              style={{
                flex: 1,
                overflow: "auto",
                padding: 12,
                fontSize: 13,
                lineHeight: 1.65,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {!pageText ? (
                <span className="faint">(空)</span>
              ) : (
                textParts.map((part, i) =>
                  part.type === "mark" ? (
                    <mark
                      key={`m-${i}`}
                      ref={(el) => {
                        if (el) markRef.current = el;
                      }}
                      style={{
                        background: "rgba(245,158,11,0.45)",
                        color: "var(--text)",
                        borderRadius: 2,
                        padding: "0 2px",
                      }}
                    >
                      {part.value}
                    </mark>
                  ) : (
                    <span key={`t-${i}`}>{part.value}</span>
                  ),
                )
              )}
            </div>
          )}
          {blocks.length > 0 && !editing && (
            <div
              style={{
                maxHeight: 140,
                overflowY: "auto",
                borderTop: "1px solid var(--border)",
                padding: 8,
              }}
            >
              <div className="faint" style={{ fontSize: 10, marginBottom: 4 }}>版面块 · 点击同步</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {blocks.slice(0, 48).map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    className={`btn btn-sm ${activeBlockId === b.id ? "btn-primary" : ""}`}
                    style={{ fontSize: 10, padding: "2px 6px" }}
                    onClick={() => selectBlock(b.id === activeBlockId ? null : b.id)}
                    title={(b.text || b.label).slice(0, 80)}
                  >
                    #{b.id} {b.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {exitDiffOpen && (
        <ExitDiffModal
          patientId={patientId}
          pages={(changedCount > 0 ? changedPages : safePages)
            .filter((p) => (draftMap[p.page] ?? "") !== (baselineMap[p.page] ?? ""))
            .map((p) => {
              const thumb = resolveImage(p, cache[p.page]);
              return {
                page: p.page,
                label: p.display_label || p.region_name || p.page,
                before: baselineMap[p.page] ?? "",
                after: draftMap[p.page] ?? "",
                unsaved: (draftMap[p.page] ?? "") !== (diskMap[p.page] ?? ""),
                imageStage: thumb.stage || "source",
                imageFile: thumb.file || "",
              };
            })}
          totalPages={pageCount}
          saving={saving}
          onRestorePage={restorePageToBaseline}
          onRestoreAll={restoreAllToBaseline}
          onSaveAll={() => void confirmExitSaveAll()}
          onDiscardAll={() => void confirmExitDiscardAll()}
          onContinue={() => setExitDiffOpen(false)}
          onExitOnly={() => {
            setExitDiffOpen(false);
            onBack();
          }}
          onJumpToPage={(pageName) => {
            const idx = safePages.findIndex((p) => p.page === pageName);
            if (idx >= 0) {
              setExitDiffOpen(false);
              setEditing(false);
              setPageIdx(idx);
            }
          }}
        />
      )}
    </div>
  );
}

type DiffPageItem = {
  page: string;
  label: string;
  before: string;
  after: string;
  unsaved?: boolean;
  imageStage: string;
  imageFile: string;
};

function ExitDiffModal({
  patientId,
  pages,
  totalPages,
  saving,
  onRestorePage,
  onRestoreAll,
  onSaveAll,
  onDiscardAll,
  onContinue,
  onExitOnly,
  onJumpToPage,
}: {
  patientId: string;
  pages: DiffPageItem[];
  totalPages: number;
  saving: boolean;
  onRestorePage: (page: string) => void;
  onRestoreAll: () => void;
  onSaveAll: () => void;
  onDiscardAll: () => void;
  onContinue: () => void;
  onExitOnly: () => void;
  onJumpToPage: (page: string) => void;
}) {
  // 病人级汇总：所有改动页的 diff 统计
  const pageStats = useMemo(
    () =>
      pages.map((p) => {
        const lines = diffLines(p.before, p.after);
        const s = countDiffStats(lines);
        return { page: p.page, lines, ...s };
      }),
    [pages],
  );
  const totalAdd = pageStats.reduce((n, s) => n + s.add, 0);
  const totalDel = pageStats.reduce((n, s) => n + s.del, 0);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onContinue();
      }}
    >
      <div
        style={{
          width: "min(1100px, 100%)",
          height: "min(92vh, 900px)",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          boxShadow: "0 16px 48px rgba(0,0,0,0.4)",
        }}
      >
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>病人级修改对照</div>
          <div className="faint" style={{ fontSize: 12, marginTop: 6, lineHeight: 1.5 }}>
            {pages.length === 0
              ? "本病人相对进入审查时没有文本改动"
              : `共 ${totalPages} 页 · 改动 ${pages.length} 页 · `}
            {pages.length > 0 && (
              <>
                <span style={{ color: "var(--success)" }}>+{totalAdd}</span>
                {" / "}
                <span style={{ color: "var(--error)" }}>−{totalDel}</span>
                {" 行 · 每页展示病历图 + 文本 diff · 可单页还原"}
              </>
            )}
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 14, minHeight: 0 }}>
          {pages.length === 0 ? (
            <div className="faint" style={{ padding: 32, textAlign: "center" }}>无改动</div>
          ) : (
            pages.map((p, idx) => {
              const st = pageStats[idx];
              const lines = st?.lines || [];
              const imageUrl = api.imageUrl(patientId, p.imageStage, p.imageFile);
              return (
                <div
                  key={p.page}
                  id={`diff-page-${p.page}`}
                  style={{
                    marginBottom: 20,
                    border: "1px solid var(--border)",
                    borderRadius: 10,
                    overflow: "hidden",
                    background: "var(--surface-2)",
                  }}
                >
                  <div
                    style={{
                      padding: "10px 12px",
                      borderBottom: "1px solid var(--border)",
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                    }}
                  >
                    <span style={{ fontWeight: 700, fontSize: 14 }}>
                      {idx + 1}/{pages.length} · {p.label}
                    </span>
                    <span style={{ color: "var(--success)", fontSize: 12 }}>+{st?.add ?? 0}</span>
                    <span style={{ color: "var(--error)", fontSize: 12 }}>−{st?.del ?? 0}</span>
                    <span className="faint" style={{ fontSize: 11 }}>
                      {stageLabel(p.imageStage)} · {p.imageFile || p.page}
                    </span>
                    {p.unsaved && (
                      <span style={{ fontSize: 11, color: "var(--warning)" }}>未写盘</span>
                    )}
                    <div style={{ flex: 1 }} />
                    <button className="btn btn-sm" onClick={() => onJumpToPage(p.page)}>
                      定位到该页审查
                    </button>
                    <button className="btn btn-sm" onClick={() => onRestorePage(p.page)}>
                      还原本页
                    </button>
                    <a
                      className="btn btn-sm"
                      href={imageUrl}
                      target="_blank"
                      rel="noreferrer"
                      title="新窗口打开原图"
                    >
                      打开大图
                    </a>
                  </div>

                  {/* 大图定位：完整显示病历图，不裁切 */}
                  <div
                    style={{
                      padding: 12,
                      borderBottom: "1px solid var(--border)",
                      background: "var(--surface)",
                      textAlign: "center",
                    }}
                  >
                    <div className="faint" style={{ fontSize: 11, marginBottom: 8, textAlign: "left" }}>
                      病历定位图（本页 OCR 实际输入图：{stageLabel(p.imageStage)}）· 点击打开原图
                    </div>
                    <a href={imageUrl} target="_blank" rel="noreferrer">
                      <img
                        src={imageUrl}
                        alt={p.label}
                        style={{
                          width: "100%",
                          maxHeight: "85vh",
                          objectFit: "contain",
                          borderRadius: 8,
                          border: "1px solid var(--border)",
                          cursor: "zoom-in",
                          background: "#0a0a0a",
                          display: "block",
                          margin: "0 auto",
                        }}
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.opacity = "0.35";
                        }}
                      />
                    </a>
                  </div>

                  {/* 完整文本 diff：全部行，不省略 */}
                  <div
                    style={{
                      padding: 0,
                      fontSize: 12,
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                    }}
                  >
                    <div
                      className="faint"
                      style={{
                        padding: "8px 12px",
                        borderBottom: "1px solid var(--border)",
                        fontSize: 11,
                        background: "var(--surface-2)",
                      }}
                    >
                      全文 diff（进入审查前 → 现在）· 共 {lines.length} 行 · 完整展示不省略
                    </div>
                    {lines.length === 0 ? (
                      <div className="faint" style={{ padding: 12 }}>无行级差异</div>
                    ) : (
                      lines.map((l, i) => (
                        <div
                          key={i}
                          style={{
                            padding: "3px 10px",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            background:
                              l.type === "add"
                                ? "rgba(34,197,94,0.14)"
                                : l.type === "del"
                                  ? "rgba(239,68,68,0.14)"
                                  : "transparent",
                            color:
                              l.type === "add"
                                ? "var(--success)"
                                : l.type === "del"
                                  ? "var(--error)"
                                  : "var(--text-2)",
                            borderLeft:
                              l.type === "add"
                                ? "3px solid var(--success)"
                                : l.type === "del"
                                  ? "3px solid var(--error)"
                                  : "3px solid transparent",
                          }}
                        >
                          <span style={{ opacity: 0.55, marginRight: 8, userSelect: "none", fontSize: 10 }}>
                            {String(i + 1).padStart(3, " ")}
                          </span>
                          <span style={{ opacity: 0.7, marginRight: 8, userSelect: "none" }}>
                            {l.type === "add" ? "+" : l.type === "del" ? "−" : " "}
                          </span>
                          {l.text || " "}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div
          style={{
            padding: 12,
            borderTop: "1px solid var(--border)",
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            justifyContent: "flex-end",
            flexShrink: 0,
          }}
        >
          <button className="btn btn-sm" disabled={saving} onClick={onContinue}>继续审查</button>
          {pages.length > 0 && (
            <>
              <button className="btn btn-sm" disabled={saving} onClick={onRestoreAll}>全部还原到进入时</button>
              <button className="btn btn-sm" disabled={saving} onClick={onDiscardAll} style={{ color: "var(--error)" }}>
                还原磁盘并退出
              </button>
              <button className="btn btn-sm" disabled={saving} onClick={onExitOnly}>
                直接退出
              </button>
              <button className="btn btn-sm btn-primary" disabled={saving} onClick={onSaveAll}>
                {saving ? "保存中…" : `保存 ${pages.length} 页改动并退出`}
              </button>
            </>
          )}
          {pages.length === 0 && (
            <button className="btn btn-sm btn-primary" onClick={onExitOnly}>退出审查</button>
          )}
        </div>
      </div>
    </div>
  );
}

function ReviewCanvas({
  imageSrc,
  blocks,
  imageWidth,
  imageHeight,
  activeId,
  showAll,
  onSelect,
}: {
  imageSrc: string;
  blocks: LayoutBlock[];
  imageWidth: number;
  imageHeight: number;
  activeId: number | null;
  showAll: boolean;
  onSelect: (id: number | null) => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [disp, setDisp] = useState({ w: 0, h: 0 });
  const [nat, setNat] = useState({ w: imageWidth, h: imageHeight });
  const [zoom, setZoom] = useState(100);
  const [lightbox, setLightbox] = useState(false);

  useEffect(() => {
    if (imageWidth && imageHeight) setNat({ w: imageWidth, h: imageHeight });
  }, [imageWidth, imageHeight]);

  useEffect(() => {
    setZoom(100);
    setLightbox(false);
  }, [imageSrc]);

  useEffect(() => {
    const measure = () => {
      const img = imgRef.current;
      if (img) setDisp({ w: img.clientWidth, h: img.clientHeight });
    };
    // 缩放后下一帧再量，保证 bbox 对齐
    const t = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(t);
      window.removeEventListener("resize", measure);
    };
  }, [imageSrc, zoom]);

  const sx = nat.w > 0 && disp.w > 0 ? disp.w / nat.w : 1;
  const sy = nat.h > 0 && disp.h > 0 ? disp.h / nat.h : 1;

  const hitTargets = blocks.filter(
    (b) => Array.isArray(b.bbox) && b.bbox.length >= 4 && Number.isFinite(b.bbox[0]),
  );

  const zoomIn = () => setZoom((z) => Math.min(400, z + 25));
  const zoomOut = () => setZoom((z) => Math.max(50, z - 25));
  const zoomReset = () => setZoom(100);

  // 滚轮 + Ctrl/⌘ 缩放
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      if (e.deltaY < 0) setZoom((z) => Math.min(400, z + 10));
      else setZoom((z) => Math.max(50, z - 10));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", minHeight: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span className="faint" style={{ fontSize: 11 }}>缩放</span>
        <button className="btn btn-sm" onClick={zoomOut} title="缩小">−</button>
        <span className="faint" style={{ minWidth: 40, textAlign: "center", fontSize: 12 }}>{zoom}%</span>
        <button className="btn btn-sm" onClick={zoomIn} title="放大">+</button>
        <button className="btn btn-sm" onClick={zoomReset} title="适应窗口">适应</button>
        <button className="btn btn-sm" onClick={() => setLightbox(true)} title="全屏大图">全屏</button>
        {imageSrc && (
          <a className="btn btn-sm" href={imageSrc} target="_blank" rel="noreferrer" title="新窗口打开">
            原图
          </a>
        )}
        <span className="faint" style={{ fontSize: 10 }}>⌘/Ctrl + 滚轮也可缩放</span>
      </div>

      <div
        ref={scrollRef}
        style={{
          flex: 1,
          minHeight: 200,
          overflow: "auto",
          border: "1px solid var(--border)",
          borderRadius: 8,
          background: "#0a0a0a",
          padding: 8,
        }}
      >
        <div style={{ position: "relative", display: "inline-block" }}>
          <img
            ref={imgRef}
            src={imageSrc || ""}
            alt="review"
            onLoad={(e) => {
              const el = e.currentTarget;
              setDisp({ w: el.clientWidth, h: el.clientHeight });
              if (!imageWidth || !imageHeight) {
                setNat({ w: el.naturalWidth || 1, h: el.naturalHeight || 1 });
              }
            }}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.opacity = "0.35";
            }}
            onDoubleClick={() => setLightbox(true)}
            style={{
              width: nat.w > 0 ? Math.max(80, (nat.w * zoom) / 100) : undefined,
              maxWidth: zoom === 100 ? "100%" : "none",
              height: "auto",
              display: "block",
              borderRadius: 4,
              userSelect: "none",
              cursor: "zoom-in",
            }}
            draggable={false}
          />
          {hitTargets.map((b) => {
            const x1 = Number(b.bbox[0]) || 0;
            const y1 = Number(b.bbox[1]) || 0;
            const x2 = Number(b.bbox[2]) || x1;
            const y2 = Number(b.bbox[3]) || y1;
            const active = b.id === activeId;
            const showBorder = showAll || active;
            return (
              <div
                key={String(b.id)}
                title={(b.text || b.label || "").slice(0, 100)}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(active ? null : b.id);
                }}
                style={{
                  position: "absolute",
                  left: x1 * sx,
                  top: y1 * sy,
                  width: Math.max(4, (x2 - x1) * sx),
                  height: Math.max(4, (y2 - y1) * sy),
                  border: showBorder
                    ? `2px solid ${active ? "var(--warning)" : "var(--primary)"}`
                    : "1px solid transparent",
                  background: active
                    ? "rgba(245,158,11,0.28)"
                    : showAll
                      ? "rgba(91,91,214,0.10)"
                      : "transparent",
                  boxSizing: "border-box",
                  cursor: "pointer",
                  borderRadius: 2,
                }}
              />
            );
          })}
        </div>
      </div>

      {hitTargets.length > 0 && !showAll && activeId == null && (
        <div className="faint" style={{ fontSize: 11 }}>
          点击图上区域选中块 · 双击图片全屏 · +/− 放大
        </div>
      )}

      {lightbox && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1100,
            background: "rgba(0,0,0,0.88)",
            display: "flex",
            flexDirection: "column",
          }}
          onClick={() => setLightbox(false)}
        >
          <div
            style={{
              padding: "10px 14px",
              display: "flex",
              alignItems: "center",
              gap: 8,
              color: "#fff",
              flexShrink: 0,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <span style={{ fontWeight: 600 }}>全屏预览</span>
            <span style={{ opacity: 0.7, fontSize: 12 }}>{zoom}%</span>
            <div style={{ flex: 1 }} />
            <button className="btn btn-sm" onClick={zoomOut}>−</button>
            <button className="btn btn-sm" onClick={zoomIn}>+</button>
            <button className="btn btn-sm" onClick={zoomReset}>100%</button>
            {imageSrc && (
              <a className="btn btn-sm" href={imageSrc} target="_blank" rel="noreferrer">原图</a>
            )}
            <button className="btn btn-sm btn-primary" onClick={() => setLightbox(false)}>关闭</button>
          </div>
          <div
            style={{ flex: 1, overflow: "auto", padding: 16, textAlign: "center" }}
            onClick={(e) => e.stopPropagation()}
            onWheel={(e) => {
              if (!(e.ctrlKey || e.metaKey)) return;
              e.preventDefault();
              if (e.deltaY < 0) zoomIn();
              else zoomOut();
            }}
          >
            <img
              src={imageSrc || ""}
              alt="fullscreen"
              style={{
                width: nat.w > 0 ? Math.max(120, (nat.w * zoom) / 100) : "100%",
                maxWidth: zoom <= 100 ? "100%" : "none",
                height: "auto",
                borderRadius: 6,
              }}
              draggable={false}
            />
          </div>
        </div>
      )}
    </div>
  );
}
