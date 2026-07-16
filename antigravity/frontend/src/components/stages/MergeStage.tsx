import { useState, useRef, useEffect } from "react";
import { useWorkbench } from "../../store/workbench";
import { api } from "../../api/client";

export default function MergeStage() {
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const editMergeText = useWorkbench((s) => s.editMergeText);

  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMatches, setSearchMatches] = useState<number>(0);
  const [currentMatch, setCurrentMatch] = useState(0);
  const [fontSize, setFontSize] = useState(14);
  const [showRaw, setShowRaw] = useState(false);
  const editorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (patientDetail?.merged_text) {
      setText(patientDetail.merged_text);
    }
  }, [patientDetail?.merged_text]);

  if (!patientDetail || !currentPatientId) return null;

  const mergedText = patientDetail.merged_text;
  const mergeEdited = patientDetail.stages["merge"]?.data?.edited;
  const isStale = patientDetail.stages["merge"]?.status === "stale";

  if (!mergedText) {
    return (
      <div className="empty-state">
        <div className="empty-icon"></div>
        <div className="empty-title">尚未合并</div>
        <div className="empty-desc">需要先完成 OCR，再点击右侧「执行」合并文档</div>
      </div>
    );
  }

  const pages = text.split("---PAGE_BREAK---");

  const handleSave = () => {
    editMergeText(currentPatientId, text);
    setEditing(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleCancel = () => {
    setText(mergedText);
    setEditing(false);
  };

  const handleSearch = (q: string) => {
    setSearchQuery(q);
    if (!q.trim()) {
      setSearchMatches(0);
      return;
    }
    const lower = text.toLowerCase();
    const query = q.toLowerCase();
    let count = 0;
    let idx = lower.indexOf(query);
    while (idx >= 0) {
      count++;
      idx = lower.indexOf(query, idx + query.length);
    }
    setSearchMatches(count);
    setCurrentMatch(0);
  };

  const fontSizeLabel = fontSize <= 12 ? "小" : fontSize <= 14 ? "中" : fontSize <= 16 ? "大" : "特大";

  return (
    <>
      {/* 工具条 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div className="h2">合并文档 ({pages.length} 页 · {text.length} 字)</div>
        {mergeEdited && (
          <span style={{ fontSize: 11, color: "var(--primary)", padding: "2px 8px", borderRadius: 10, background: "var(--primary-fade)" }}>
            已编辑
          </span>
        )}
        {isStale && (
          <span style={{ fontSize: 11, color: "var(--warning)", padding: "2px 8px", borderRadius: 10, background: "var(--warning-fade)" }}>
            ! 源数据已变更,建议重新合并
          </span>
        )}
        <div style={{ flex: 1 }} />
        <input
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="搜索…"
          style={{ width: 160 }}
        />
        {searchMatches > 0 && (
          <span className="faint">{currentMatch + 1}/{searchMatches} 匹配</span>
        )}
        <select
          value={fontSize}
          onChange={(e) => setFontSize(Number(e.target.value))}
          style={{ width: "auto" }}
          title="字号"
        >
          <option value={12}>小</option>
          <option value={14}>中</option>
          <option value={16}>大</option>
          <option value={18}>特大</option>
        </select>
        {editing ? (
          <>
            <button className="btn btn-sm btn-primary" onClick={handleSave}>✓ 保存</button>
            <button className="btn btn-sm" onClick={handleCancel}>取消</button>
          </>
        ) : (
          <>
            <button className="btn btn-sm" onClick={() => setEditing(true)}>编辑</button>
            <button className="btn btn-sm" onClick={() => setShowRaw(!showRaw)}>
              {showRaw ? "隐藏原始标记" : "显示原始标记"}
            </button>
          </>
        )}
        {saved && <span style={{ color: "var(--success)", fontSize: 11 }}>✓ 已保存</span>}
      </div>

      {/* 阅读器 */}
      {editing ? (
        <div
          ref={editorRef}
          className="merge-reader editing"
          contentEditable
          suppressContentEditableWarning
          style={{ fontSize }}
          onBlur={(e) => setText(e.currentTarget.innerText)}
          dangerouslySetInnerHTML={{ __html: formatMergeText(text, showRaw) }}
        />
      ) : (
        <div className="merge-reader" style={{ fontSize }}>
          {renderMergeText(text, showRaw, searchQuery)}
        </div>
      )}
    </>
  );
}

function formatMergeText(text: string, showRaw: boolean): string {
  if (showRaw) return escapeHtml(text);
  const pages = text.split("---PAGE_BREAK---");
  return pages.map((page, i) => {
    const formatted = escapeHtml(page.trim());
    if (pages.length > 1 && i > 0) {
      return `<div class="merge-page-marker">── 第 ${i + 1} 页 ──</div>\n${formatted}`;
    }
    return formatted;
  }).join("\n");
}

function renderMergeText(text: string, showRaw: boolean, searchQuery: string): React.ReactNode {
  const pages = text.split("---PAGE_BREAK---");
  return (
    <>
      {pages.map((page, i) => {
        const trimmed = page.trim();
        return (
          <div key={i}>
            {pages.length > 1 && i > 0 && (
              <div className="merge-page-marker">── 第 {i + 1} 页 ──</div>
            )}
            {showRaw && i > 0 && (
              <div className="merge-page-marker" style={{ color: "var(--text-3)" }}>--- PAGE BREAK ---</div>
            )}
            {renderPageContent(trimmed, searchQuery)}
          </div>
        );
      })}
    </>
  );
}

function renderPageContent(text: string, searchQuery: string): React.ReactNode {
  if (!text) return null;

  // 检测 HTML 表格
  if (text.includes("<table") || text.includes("<TABLE")) {
    const parts: React.ReactNode[] = [];
    const regex = /(<table[\s\S]*?<\/table>)/gi;
    let lastIdx = 0;
    let match;
    let key = 0;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIdx) {
        const before = text.slice(lastIdx, match.index).trim();
        if (before) parts.push(<div key={key++}>{highlightMerge(before, searchQuery)}</div>);
      }
      parts.push(
        <div key={key++} dangerouslySetInnerHTML={{ __html: match[1] }} style={{ margin: "8px 0" }} />
      );
      lastIdx = match.index + match[1].length;
    }
    if (lastIdx < text.length) {
      const after = text.slice(lastIdx).trim();
      if (after) parts.push(<div key={key++}>{highlightMerge(after, searchQuery)}</div>);
    }
    return <>{parts}</>;
  }

  return highlightMerge(text, searchQuery);
}

function highlightMerge(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const parts: React.ReactNode[] = [];
  let lastIdx = 0;
  let idx = lower.indexOf(q);
  let key = 0;
  while (idx >= 0) {
    if (idx > lastIdx) parts.push(text.slice(lastIdx, idx));
    parts.push(
      <mark key={key++}>{text.slice(idx, idx + query.length)}</mark>
    );
    lastIdx = idx + query.length;
    idx = lower.indexOf(q, lastIdx);
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return <>{parts}</>;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br/>");
}
