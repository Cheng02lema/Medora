import { useState, useRef, useEffect } from "react";
import { useWorkbench } from "../../store/workbench";
import { api } from "../../api/client";
import LazyImage from "../LazyImage";
import ErrorBoundary from "../ErrorBoundary";
import OcrReviewView from "./OcrReviewView";

interface OcrPage {
  page: string;
  text: string;
  char_count: number;
  md_path: string;
  source_stage?: string;
  source_relative?: string;
  source_image?: string;
  parent_page?: string;
  region_name?: string;
  display_label?: string;
  input_mode?: string;
  image_source?: string;
  slice_base_stage?: string;
  has_layout?: boolean;
}

interface OcrInputPlan {
  requested_mode: string;
  effective_mode: string;
  image_source_requested?: string;
  image_source_effective?: string;
  image_source_label?: string;
  structure_label?: string;
  count: number;
  message: string;
  warning: string;
  error?: string;
  has_slices: boolean;
  has_preprocess?: boolean;
  has_source?: boolean;
  preprocess_count?: number;
  source_count?: number;
  slice_region_count: number;
  slice_status: string;
  slice_base_stage?: string;
}

export default function OCRStage() {
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const stageData = useWorkbench((s) => s.stageData);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const editOcrPage = useWorkbench((s) => s.editOcrPage);
  const rerunOcrPage = useWorkbench((s) => s.rerunOcrPage);
  const runningTasks = useWorkbench((s) => s.runningTasks);
  const addToast = useWorkbench((s) => s.addToast);
  const setStage = useWorkbench((s) => s.setStage);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const [allExpanded, setAllExpanded] = useState(true);
  const [searching, setSearching] = useState(false);
  const [activeCardIdx, setActiveCardIdx] = useState(0);
  const [inputPlan, setInputPlan] = useState<OcrInputPlan | null>(null);
  const [modeBusy, setModeBusy] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "review">("list");
  const [reviewPage, setReviewPage] = useState<string | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stageKey = currentPatientId ? `${currentPatientId}:ocr` : "";
  const stageInfo = stageKey ? stageData[stageKey] : null;
  const pages: OcrPage[] = stageInfo?.pages || patientDetail?.ocr_pages || [];
  const task = currentPatientId ? runningTasks[currentPatientId] : undefined;
  const isRunning = task?.stage === "ocr";
  const ocrEdited = patientDetail?.stages?.["ocr"]?.data?.edited;
  const dataSource = patientDetail?.stages?.source?.data?.data_source || "image";
  const sourceImages = patientDetail?.images || [];

  useEffect(() => {
    if (!currentPatientId) return;
    api.getOcrInputs(currentPatientId).then(setInputPlan).catch(() => setInputPlan(null));
  }, [
    currentPatientId,
    patientDetail?.stages?.slice?.status,
    patientDetail?.stages?.ocr?.status,
    patientDetail?.stages?.preprocess?.status,
    isRunning,
  ]);

  const refreshInputPlan = async () => {
    if (!currentPatientId) return;
    try {
      const plan = await api.getOcrInputs(currentPatientId);
      setInputPlan(plan);
    } catch {
      /* ignore */
    }
  };

  const applyInputOptions = async (
    mode?: "auto" | "slices" | "full",
    imageSource?: "auto" | "preprocess" | "source",
  ) => {
    if (!currentPatientId) return;
    setModeBusy(true);
    try {
      const r = await api.setOcrInputMode(currentPatientId, mode, imageSource);
      await refreshInputPlan();
      const msg = r.message || "OCR 输入已更新";
      const warn = r.warning || r.error;
      addToast(warn ? "warning" : "info", warn ? `${msg} · ${warn}` : `${msg} · 请重新执行 OCR`);
    } catch (e: any) {
      addToast("error", e.message || "切换失败");
    } finally {
      setModeBusy(false);
    }
  };

  // 键盘导航: J/K 翻页, E 编辑, R 重OCR（列表模式）
  useEffect(() => {
    if (viewMode === "review") return;
    const pageCount = Math.max(1, pages.length || 1);
    const next = () => setActiveCardIdx((i) => Math.min(pageCount - 1, i + 1));
    const prev = () => setActiveCardIdx((i) => Math.max(0, i - 1));
    const edit = () => {
      const card = document.querySelector(`[data-card-idx="${activeCardIdx}"]`);
      const btn = card?.querySelector('[data-action="edit"]') as HTMLButtonElement | null;
      btn?.click();
    };
    const rerun = () => {
      const card = document.querySelector(`[data-card-idx="${activeCardIdx}"]`);
      const btn = card?.querySelector('[data-action="rerun"]') as HTMLButtonElement | null;
      btn?.click();
    };
    const toggleExpand = () => setAllExpanded((e) => !e);

    document.addEventListener("medora:next", next);
    document.addEventListener("medora:prev", prev);
    document.addEventListener("medora:edit", edit);
    document.addEventListener("medora:rerun", rerun);
    document.addEventListener("medora:toggle-expand", toggleExpand);
    return () => {
      document.removeEventListener("medora:next", next);
      document.removeEventListener("medora:prev", prev);
      document.removeEventListener("medora:edit", edit);
      document.removeEventListener("medora:rerun", rerun);
      document.removeEventListener("medora:toggle-expand", toggleExpand);
    };
  }, [activeCardIdx, pages.length, viewMode]);

  useEffect(() => {
    if (viewMode === "review") return;
    const card = document.querySelector(`[data-card-idx="${activeCardIdx}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeCardIdx, viewMode]);

  if (!patientDetail || !currentPatientId) return null;

  const openReview = (pageName?: string) => {
    if (!pages.length) {
      addToast("warning", "暂无 OCR 结果");
      return;
    }
    const focus =
      pageName ||
      pages[activeCardIdx]?.page ||
      pages.find((p) => p.has_layout)?.page ||
      pages[0]?.page ||
      null;
    setReviewPage(focus);
    setViewMode("review");
  };

  if (viewMode === "review") {
    return (
      <ErrorBoundary
        onError={(err) => {
          console.error("[OCR审查]", err);
          addToast("error", `审查页异常：${err.message}`);
          setViewMode("list");
        }}
      >
        <OcrReviewView
          key={`${currentPatientId}:${reviewPage || "review"}`}
          patientId={currentPatientId}
          pages={pages || []}
          initialPage={reviewPage}
          onBack={() => setViewMode("list")}
          onRerunPage={(name) => {
            try {
              rerunOcrPage(currentPatientId, name);
            } catch (e: any) {
              addToast("error", e?.message || "重识别失败");
            }
          }}
          onSavePage={async (pageName, text) => {
            await editOcrPage(currentPatientId, pageName, text);
          }}
          addToast={(type, msg) => addToast(type, msg)}
        />
      </ErrorBoundary>
    );
  }

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(async () => {
      try {
        const result = await api.searchOcr(currentPatientId, query);
        setSearchResults(result.results);
      } catch (e) {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  };

  if (dataSource === "text" || dataSource === "excel") {
    return (
      <div className="empty-state">
        <div className="empty-icon">⏭</div>
        <div className="empty-title">此病人无需 OCR</div>
        <div className="empty-desc">
          数据源为 {dataSource === "excel" ? "Excel 拆分" : "文本文件"}，已在导入时生成合并文本。
          <br />
          请直接跳到「合并」或「抽取」阶段。
        </div>
      </div>
    );
  }

  if (pages.length === 0 && !isRunning) {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">尚未进行 OCR 识别</div>
        <div className="empty-desc">
          {inputPlan?.message || "点击右侧「执行」开始识别"}
          {inputPlan?.warning ? ` · ${inputPlan.warning}` : ""}
          {inputPlan?.effective_mode === "slices"
            ? " · 将只识别切片图"
            : " · 将识别整页"}
        </div>
        {inputPlan?.warning && inputPlan.slice_region_count > 0 && !inputPlan.has_slices && (
          <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={() => setStage("slice")}>
            去切片
          </button>
        )}
      </div>
    );
  }

  return (
    <>
      {/* 工具条 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <div className="h2">OCR 识别结果 ({pages.length} 页)</div>
        {ocrEdited && (
          <span style={{ fontSize: 11, color: "var(--primary)", padding: "2px 8px", borderRadius: 4, background: "var(--primary-fade)" }}>
            含人工编辑
          </span>
        )}
        <div style={{ flex: 1 }} />
        <input
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="搜索所有页…"
          style={{ width: 200 }}
        />
        <button className="btn btn-sm" onClick={() => setAllExpanded(!allExpanded)}>
          {allExpanded ? "全部折叠" : "全部展开"}
        </button>
        <button
          className="btn btn-sm btn-primary"
          onClick={() => openReview()}
          disabled={!pages.length || isRunning}
          title={pages.some((p) => p.has_layout) ? "进入图文审查（点框定位文字）" : "建议先重跑 OCR 以生成版面；仍可进入查看"}
        >
          审查模式
        </button>
      </div>

      {/* 输入来源：结构 + 图源 */}
      {inputPlan && (
        <div
          style={{
            marginBottom: 14,
            padding: "10px 12px",
            borderRadius: 8,
            border: `1px solid ${inputPlan.error || inputPlan.warning ? "var(--warning)" : "var(--border)"}`,
            background: inputPlan.error || inputPlan.warning ? "var(--warning-fade)" : "var(--surface-2)",
            fontSize: 12,
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontWeight: 600 }}>
              {inputPlan.structure_label || (inputPlan.effective_mode === "slices" ? "切片" : "整页")}
              {" · "}
              {inputPlan.image_source_label
                || (inputPlan.image_source_effective === "preprocess"
                  ? "预处理"
                  : inputPlan.image_source_effective === "slice"
                    ? "切片"
                    : "原图")}
            </span>
            <span className="faint">{inputPlan.message}</span>
            {(inputPlan.error || inputPlan.warning) && (
              <span style={{ color: "var(--warning)" }}>{inputPlan.error || inputPlan.warning}</span>
            )}
            <div style={{ flex: 1 }} />
            {inputPlan.warning && inputPlan.slice_region_count > 0 && !inputPlan.has_slices && (
              <button className="btn btn-sm btn-primary" onClick={() => setStage("slice")}>去切片</button>
            )}
            {inputPlan.image_source_requested === "preprocess" && !inputPlan.has_preprocess && (
              <button className="btn btn-sm btn-primary" onClick={() => setStage("preprocess")}>去预处理</button>
            )}
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <span className="faint" style={{ minWidth: 36 }}>结构</span>
            {([
              { key: "auto", label: "自动" },
              { key: "slices", label: "切片" },
              { key: "full", label: "整页" },
            ] as const).map((opt) => {
              const active = (inputPlan.requested_mode || "auto") === opt.key;
              return (
                <button
                  key={opt.key}
                  className={`btn btn-sm ${active ? "btn-primary" : ""}`}
                  disabled={modeBusy || (opt.key === "slices" && !inputPlan.has_slices)}
                  title={opt.key === "slices" && !inputPlan.has_slices ? "尚无切片产物" : undefined}
                  onClick={() => applyInputOptions(opt.key)}
                >
                  {opt.label}
                </button>
              );
            })}

            <span className="faint" style={{ marginLeft: 8, minWidth: 36 }}>图源</span>
            {([
              { key: "auto", label: "自动" },
              { key: "preprocess", label: `预处理${inputPlan.preprocess_count != null ? `(${inputPlan.preprocess_count})` : ""}` },
              { key: "source", label: `原图${inputPlan.source_count != null ? `(${inputPlan.source_count})` : ""}` },
            ] as const).map((opt) => {
              const active = (inputPlan.image_source_requested || "auto") === opt.key;
              const disabled = modeBusy || inputPlan.effective_mode === "slices";
              return (
                <button
                  key={opt.key}
                  className={`btn btn-sm ${active ? "btn-primary" : ""}`}
                  disabled={disabled}
                  title={
                    inputPlan.effective_mode === "slices"
                      ? "切片模式下图源由切片底图决定；请先切到「整页」"
                      : opt.key === "preprocess" && !inputPlan.has_preprocess
                        ? "尚无预处理产物，选中后需先去跑预处理"
                        : undefined
                  }
                  onClick={() => applyInputOptions(undefined, opt.key)}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          {inputPlan.effective_mode === "slices" && (
            <div className="faint" style={{ marginTop: 6, fontSize: 11 }}>
              当前为切片 OCR
              {inputPlan.slice_base_stage
                ? ` · 切片底图：${inputPlan.slice_base_stage === "preprocess" ? "预处理" : "原图"}`
                : ""}
              。若要直接提交原图/预处理整页，请先切到「整页」。
            </div>
          )}
        </div>
      )}

      {/* 搜索结果 */}
      {searchResults !== null && (
        <div style={{ marginBottom: 16, padding: 12, borderRadius: 10, background: "var(--warning-fade)", border: "1px solid var(--warning)" }}>
          <div style={{ fontSize: 12, color: "var(--warning)", marginBottom: 6 }}>
            {searching ? "搜索中…" : `找到 ${searchResults.length} 处匹配`}
          </div>
          {searchResults.slice(0, 8).map((r, i) => (
            <div
              key={i}
              style={{ fontSize: 12, padding: "4px 0", cursor: "pointer", color: "var(--text-2)" }}
              onClick={() => {
                const el = document.getElementById(`ocr-card-${r.page}`);
                el?.scrollIntoView({ behavior: "smooth", block: "center" });
                el?.classList.add("highlight-flash");
                setTimeout(() => el?.classList.remove("highlight-flash"), 1500);
              }}
            >
              <span style={{ color: "var(--text-3)" }}>{r.page}:</span>{" "}
              {r.snippet}
            </div>
          ))}
          {searchResults.length > 8 && (
            <div className="faint" style={{ marginTop: 4 }}>还有 {searchResults.length - 8} 处…</div>
          )}
        </div>
      )}

      {/* OCR 卡片列表 */}
      {pages.map((page, idx) => {
        const isThisPageRunning = isRunning && task?.total > 0 && task.current === idx;
        const pageStatus = isThisPageRunning ? "running" : page.text ? "done" : "pending";
        const isMatch = searchResults?.some((r) => r.page === page.page);
        const isActive = activeCardIdx === idx;

        return (
          <div key={page.page || idx} data-card-idx={idx} id={`ocr-card-${page.page}`}>
          <OCRCard
            page={page}
            index={idx}
            status={pageStatus}
            patientId={currentPatientId}
            sourceImages={sourceImages}
            expanded={allExpanded || !!isMatch}
            searchQuery={searchQuery}
            isActive={isActive}
            onSave={(text) => editOcrPage(currentPatientId, page.page, text)}
            onRerun={() => rerunOcrPage(currentPatientId, page.page)}
            onReview={() => openReview(page.page)}
          />
          </div>
        );
      })}

      {/* 运行中指示 */}
      {isRunning && task && (
        <div style={{ marginTop: 16, padding: 16, borderRadius: 14, background: "var(--surface-2)", border: "1px solid var(--primary)" }}>
          <div style={{ fontSize: 13, color: "var(--primary)", fontWeight: 600 }}>
            OCR 进行中 · {task.current}/{task.total}
          </div>
          <div className="progress-bar" style={{ height: 4, marginTop: 8 }}>
            <div className="progress-fill" style={{ width: `${task.total > 0 ? (task.current / task.total) * 100 : 0}%` }} />
          </div>
          <div className="faint" style={{ marginTop: 6 }}>{task.message}</div>
        </div>
      )}
    </>
  );
}

function stageBadge(stage?: string): { text: string; color: string } | null {
  if (!stage) return null;
  if (stage === "preprocess") return { text: "预处理", color: "var(--primary)" };
  if (stage === "slice") return { text: "切片", color: "var(--success)" };
  if (stage === "source") return { text: "原图", color: "var(--text-3)" };
  return { text: stage, color: "var(--text-3)" };
}

function resolveThumb(page: OcrPage, sourceImages: { name: string }[]): { stage: string; file: string } {
  // 优先 page_meta 记录的真实 OCR 输入图
  if (page.source_stage && (page.source_relative || page.source_image)) {
    return {
      stage: page.source_stage,
      file: page.source_relative || page.source_image || "",
    };
  }
  const base = (page.page || "").replace(/_\d+$/, "");
  if (base.includes("__")) {
    const parent = base.split("__")[0];
    // 尝试常见扩展名；后端 files 按路径找
    return { stage: "slice", file: `${parent}/${base}.jpg` };
  }
  if (!base) return { stage: "source", file: sourceImages[0]?.name || "" };
  // 有预处理优先猜 preprocess（与后端 auto 一致）
  const exact = sourceImages.find((img) => img.name === base || img.name.startsWith(base));
  if (exact) return { stage: "source", file: exact.name };
  const byStem = sourceImages.find((img) => {
    const s = img.name.replace(/\.[^.]+$/, "");
    return s === base || s.startsWith(base) || base.startsWith(s);
  });
  if (byStem) return { stage: "source", file: byStem.name };
  return { stage: "source", file: `${base}.jpg` };
}

function OCRCard({
  page,
  index,
  status,
  patientId,
  sourceImages,
  expanded,
  searchQuery,
  isActive,
  onSave,
  onRerun,
  onReview,
}: {
  page: OcrPage;
  index: number;
  status: string;
  patientId: string;
  sourceImages: { name: string }[];
  expanded: boolean;
  searchQuery: string;
  isActive: boolean;
  onSave: (text: string) => void;
  onRerun: () => void;
  onReview: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(page.text || "");
  const [saved, setSaved] = useState(false);
  const [expandedLocal, setExpandedLocal] = useState(expanded);
  const textRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setExpandedLocal(expanded);
  }, [expanded]);

  useEffect(() => {
    setText(page.text || "");
  }, [page.text]);

  const handleSave = () => {
    onSave(text);
    setEditing(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleCancel = () => {
    setText(page.text || "");
    setEditing(false);
  };

  const handleRerun = () => {
    if (editing) {
      if (!confirm("重新识别将覆盖当前文本（含你的编辑），确定？")) return;
    }
    onRerun();
  };

  const statusIcon: Record<string, string> = {
    pending: "○",
    running: "·",
    done: "✓",
  };

  const thumb = resolveThumb(page, sourceImages);
  const thumbSrc = api.thumbUrl(patientId, thumb.stage, thumb.file);
  const badge = stageBadge(page.source_stage || page.image_source || thumb.stage);
  const titleLabel = page.display_label || page.region_name
    ? (page.display_label || `${page.parent_page || ""} · ${page.region_name || ""}`)
    : page.page;

  const isExpanded = expandedLocal || editing;

  return (
    <div
      id={`ocr-card-${page.page}`}
      className={`ocr-card ${status} ${isActive ? "active" : ""}`}
      style={{ display: "flex", flexDirection: "row" }}
    >
      <LazyImage
        src={thumbSrc}
        className="ocr-thumb"
        alt={page.page}
        onClick={() => status === "done" && onReview()}
        title="点击进入审查模式"
        style={{ width: 80, height: 100, borderRadius: 8, flexShrink: 0, cursor: status === "done" ? "pointer" : "default", border: "1px solid var(--border)" }}
      />

      <div className="ocr-body" style={{ flex: 1, minWidth: 0 }}>
        <div className="ocr-header">
          <span className={`status-dot ${status === "done" ? "done" : status === "running" ? "running" : "pending"}`} />
          <span style={{ fontWeight: 600 }}>
            {statusIcon[status]} {page.region_name ? `切片 ${index + 1}` : `第 ${index + 1} 页`}
          </span>
          <span className="faint" title={page.page}>{titleLabel}</span>
          {badge && (
            <span
              style={{
                fontSize: 10,
                color: badge.color,
                padding: "1px 6px",
                borderRadius: 4,
                background: "var(--surface-2)",
                border: `1px solid ${badge.color}`,
              }}
              title={
                page.source_stage === "slice" && page.slice_base_stage
                  ? `切片 · 底图=${page.slice_base_stage === "preprocess" ? "预处理" : "原图"}`
                  : `OCR 输入：${badge.text}`
              }
            >
              {badge.text}
            </span>
          )}
          {page.has_layout && (
            <span style={{ fontSize: 10, color: "var(--success)", padding: "1px 6px", borderRadius: 4, background: "var(--success-fade, rgba(34,197,94,0.12))" }}>
              可溯源
            </span>
          )}
          {status === "done" && (
            <span className="faint">{page.char_count || (page.text?.length || 0)} 字</span>
          )}
          {saved && <span style={{ color: "var(--success)", fontSize: 11 }}>已保存</span>}
          <div style={{ flex: 1 }} />
          {!expandedLocal && status === "done" && (
            <button className="btn btn-sm" onClick={() => setExpandedLocal(true)}>展开</button>
          )}
          {expandedLocal && !editing && status === "done" && (
            <>
              <button className="btn btn-sm" onClick={() => setExpandedLocal(false)}>折叠</button>
              <button className="btn btn-sm btn-primary" onClick={onReview} title="图文审查：点框定位文字">
                审查
              </button>
              <button className="btn btn-sm" data-action="edit" onClick={() => setEditing(true)}>编辑</button>
              <button className="btn btn-sm" data-action="rerun" onClick={handleRerun} title="重新识别此页">重识别</button>
            </>
          )}
          {editing && (
            <>
              <button className="btn btn-sm btn-primary" data-action="save" onClick={handleSave}>保存</button>
              <button className="btn btn-sm" onClick={handleCancel}>取消</button>
            </>
          )}
        </div>

        {status === "running" ? (
          <div style={{ padding: 16, textAlign: "center" }}>
            <div className="faint">正在识别…</div>
          </div>
        ) : status === "pending" ? (
          <div style={{ padding: 16, textAlign: "center" }}>
            <div className="faint">待识别</div>
          </div>
        ) : !isExpanded ? (
          <div
            style={{
              fontSize: 12, color: "var(--text-3)",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}
          >
            {(page.text || "").slice(0, 80)}…
          </div>
        ) : editing ? (
          <div
            ref={textRef}
            className="ocr-text"
            contentEditable
            suppressContentEditableWarning
            onBlur={(e) => setText(e.currentTarget.innerText)}
            style={{ cursor: "text", minHeight: 100, maxHeight: 400 }}
            dangerouslySetInnerHTML={{ __html: escapeHtml(page.text || "") }}
          />
        ) : (
          <div className="ocr-text" style={{ maxHeight: 400 }}>
            {renderOcrText(page.text || "", searchQuery)}
          </div>
        )}
      </div>
    </div>
  );
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderOcrText(text: string, searchQuery: string): React.ReactNode {
  if (!text) return <span style={{ color: "var(--text-3)" }}>(空)</span>;

  if (text.includes("<table") || text.includes("<TABLE")) {
    const parts: React.ReactNode[] = [];
    const regex = /(<table[\s\S]*?<\/table>)/gi;
    let lastIdx = 0;
    let match;
    let key = 0;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIdx) {
        const before = text.slice(lastIdx, match.index).trim();
        if (before) parts.push(
          <div key={key++}>{highlightText(before, searchQuery)}</div>
        );
      }
      parts.push(
        <div
          key={key++}
          className="ocr-table"
          dangerouslySetInnerHTML={{ __html: match[1] }}
          style={{ margin: "8px 0" }}
        />
      );
      lastIdx = match.index + match[1].length;
    }
    if (lastIdx < text.length) {
      const after = text.slice(lastIdx).trim();
      if (after) parts.push(
        <div key={key++}>{highlightText(after, searchQuery)}</div>
      );
    }
    return <>{parts}</>;
  }

  return highlightText(text, searchQuery);
}

function highlightText(text: string, query: string): React.ReactNode {
  const q = (query || "").trim();
  if (!q) return text;
  const lower = text.toLowerCase();
  const qq = q.toLowerCase();
  const parts: React.ReactNode[] = [];
  let lastIdx = 0;
  let idx = lower.indexOf(qq);
  let key = 0;
  while (idx >= 0) {
    if (idx > lastIdx) parts.push(text.slice(lastIdx, idx));
    parts.push(
      <mark key={key++} style={{ background: "rgba(245,158,11,0.4)", color: "var(--text)", borderRadius: 2, padding: "0 2px" }}>
        {text.slice(idx, idx + q.length)}
      </mark>
    );
    lastIdx = idx + q.length;
    idx = lower.indexOf(qq, lastIdx);
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return <>{parts}</>;
}
