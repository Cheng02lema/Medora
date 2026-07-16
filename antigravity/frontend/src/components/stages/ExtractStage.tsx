import { useState, useRef, useEffect, useMemo } from "react";
import { useWorkbench } from "../../store/workbench";
import { api } from "../../api/client";

interface ExtractedField {
  value: any;
  original_value?: any;
  edited?: boolean;
}

// 字段分组规则（按常见模板字段名分组）
const FIELD_GROUPS: { name: string; patterns: string[] }[] = [
  { name: "基本信息", patterns: ["姓名", "年龄", "住院号", "就诊时间", "入院", "性别", "日期", "病案", "来源"] },
  { name: "既往史", patterns: ["高血压", "糖尿病", "高脂", "冠心病", "心功能", "心肌梗", "脑梗", "脑卒"] },
  { name: "个人史", patterns: ["吸烟", "饮酒"] },
  { name: "主诉/现病史", patterns: ["主诉", "现病史", "发热", "胸闷", "胸痛", "乏力", "晕厥", "黑矇", "颈痛", "盗汗", "腹痛", "头晕", "头痛", "跛行", "关节", "结节", "溃疡", "体重", "视力", "听力"] },
  { name: "血压", patterns: ["收缩压", "舒张压", "血压", "SBP", "DBP"] },
  { name: "实验室检查", patterns: ["血红蛋白", "白细胞", "中性", "淋巴", "血小板", "尿素", "肌酐", "尿酸", "胆固醇", "甘油", "脂蛋白", "球蛋白", "IgG", "IgM", "IgA", "白介素", "IL", "肿瘤", "TNF", "补体", "钙蛋白", "肌钙", "BNP", "血沉", "ESR", "CRP", "反应蛋白", "淀粉样"] },
  { name: "影像", patterns: ["MRA", "CTA", "PET", "彩超", "超声", "MRI"] },
  { name: "诊疗", patterns: ["NIH", "Kerr", "评分", "激素", "泼尼松", "甲泼", "治疗", "药物", "免疫", "环磷", "阿司", "介入", "手术"] },
  { name: "其他", patterns: [] },
];

function classifyField(name: string): string {
  for (const group of FIELD_GROUPS) {
    if (group.patterns.some((p) => name.includes(p))) return group.name;
  }
  return "其他";
}

// 判断字段是否为存在性判断（值在 0/1/-1 之间）
function isExistentialField(name: string, value: any): boolean {
  const existNames = ["高血压", "糖尿病", "高脂", "冠心病", "心功能", "心肌梗", "脑梗", "吸烟", "饮酒", "发热", "胸闷", "胸痛", "乏力", "晕厥", "黑矇", "颈痛", "盗汗", "腹痛", "头晕", "头痛", "跛行", "关节", "结节", "溃疡", "体重下降", "视力下降"];
  return existNames.some((n) => name.includes(n));
}

// 判断字段是否为数值型
function isNumericField(name: string, value: any): boolean {
  if (typeof value === "number") return true;
  const numericNames = ["年龄", "血压", "血红蛋白", "白细胞", "血小板", "肌酐", "尿酸", "胆固醇", "甘油", "血沉", "CRP", "Ig", "白介素", "IL", "补体", "评分"];
  return numericNames.some((n) => name.includes(n));
}

export default function ExtractStage() {
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const editExtractFields = useWorkbench((s) => s.editExtractFields);
  const runningTasks = useWorkbench((s) => s.runningTasks);
  const addToast = useWorkbench((s) => s.addToast);

  const [activeField, setActiveField] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [rawText, setRawText] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);
  const [promptText, setPromptText] = useState("");
  const [searchField, setSearchField] = useState("");
  const sourceRef = useRef<HTMLDivElement>(null);

  const task = currentPatientId ? runningTasks[currentPatientId] : undefined;
  const isRunning = task?.stage === "extract";
  const extracted = patientDetail?.extracted_fields;
  const mergedText = patientDetail?.merged_text || "";
  const fields: Record<string, ExtractedField> = extracted?.fields || {};
  const entries = useMemo(() => Object.entries(fields), [extracted]);

  // hooks 必须在所有 early return 之前
  const grouped = useMemo(() => {
    const groups: Record<string, [string, ExtractedField][]> = {};
    for (const [name, field] of entries) {
      const g = classifyField(name);
      if (!groups[g]) groups[g] = [];
      groups[g].push([name, field]);
    }
    return groups;
  }, [entries]);

  if (!patientDetail || !currentPatientId) return null;

  if (isRunning) {
    return (
      <div className="empty-state">
        <div className="empty-icon" style={{ animation: "pulse 1.4s infinite" }}>·</div>
        <div className="empty-title">AI 正在阅读病历…</div>
        <div className="empty-desc">{task?.message || "正在调用大模型…"}</div>
        {task && task.total > 0 && (
          <div className="progress-bar" style={{ width: 200, marginTop: 12 }}>
            <div className="progress-fill" style={{ width: `${(task.current / task.total) * 100}%` }} />
          </div>
        )}
      </div>
    );
  }

  if (!extracted) {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">尚未抽取</div>
        <div className="empty-desc">需要先完成合并，再点击右侧「执行」抽取字段</div>
      </div>
    );
  }

  const filteredEntries = searchField.trim()
    ? entries.filter(([name]) => name.toLowerCase().includes(searchField.toLowerCase()))
    : entries;

  const stats = {
    total: entries.length,
    hasValue: entries.filter(([, v]) => {
      const val = typeof v === "object" && v !== null ? v.value : v;
      return val !== "-1" && val !== -1 && val !== "" && val !== null && val !== undefined;
    }).length,
    unmentioned: entries.filter(([, v]) => {
      const val = typeof v === "object" && v !== null ? v.value : v;
      return val === "-1" || val === -1;
    }).length,
    edited: entries.filter(([, v]) => typeof v === "object" && v !== null && v.edited).length,
  };

  // 字段高亮联动:点击字段 → 在源文中搜索关键词
  const handleFieldClick = (name: string) => {
    setActiveField(name);
    if (!sourceRef.current || !mergedText) return;

    const keywords = extractKeywords(name);
    // 先清旧高亮
    sourceRef.current.querySelectorAll("mark.field-hit").forEach((el) => {
      const parent = el.parentNode;
      if (parent) {
        parent.replaceChild(document.createTextNode(el.textContent || ""), el);
        parent.normalize();
      }
    });

    for (const kw of keywords) {
      if (!kw || kw.length < 1) continue;
      const hit = findAndHighlight(sourceRef.current, kw);
      if (hit) {
        hit.scrollIntoView({ behavior: "smooth", block: "center" });
        hit.classList.add("highlight-flash");
        setTimeout(() => hit.classList.remove("highlight-flash"), 1600);
        return;
      }
    }
  };

  const handleLoadRaw = async () => {
    if (!rawText) {
      try {
        const result = await api.getRawResponse(currentPatientId);
        setRawText(result.text);
      } catch (e) {
        setRawText("(无法读取)");
      }
    }
    setShowRaw(!showRaw);
  };

  const handleLoadPrompt = async () => {
    if (!promptText) {
      try {
        const result = await api.getPatientPrompt(currentPatientId);
        setPromptText(result.text);
      } catch (e) {
        setPromptText("(无法读取)");
      }
    }
    setShowPrompt(!showPrompt);
  };

  // 渲染源文本（按页分割，点击字段时动态 mark）
  const renderSourceText = () => {
    if (!mergedText) return <span className="faint">无源文本</span>;
    const pages = mergedText.split("---PAGE_BREAK---");
    return pages.map((page, i) => (
      <div key={i} data-page={i}>
        {pages.length > 1 && i > 0 && (
          <div className="merge-page-marker">── 第 {i + 1} 页 ──</div>
        )}
        <div className="source-page-text" style={{ whiteSpace: "pre-wrap" }}>{page.trim()}</div>
      </div>
    ));
  };

  return (
    <>
      {/* 工具条 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <div className="h2">抽取结果 ({stats.total} 字段)</div>
        <span className="faint">有值 {stats.hasValue} · 未提及 {stats.unmentioned} · 已编辑 {stats.edited}</span>
        <div style={{ flex: 1 }} />
        <input
          value={searchField}
          onChange={(e) => setSearchField(e.target.value)}
          placeholder="搜索字段…"
          style={{ width: 140 }}
        />
        <button className="btn btn-sm" onClick={handleLoadRaw}>
          {showRaw ? "隐藏" : "LLM原始响应"}
        </button>
        <button className="btn btn-sm" onClick={handleLoadPrompt}>
          {showPrompt ? "隐藏" : "Prompt"}
        </button>
      </div>

      {/* LLM 原始响应 / Prompt */}
      {showRaw && (
        <div style={{ marginBottom: 12, padding: 12, borderRadius: 10, background: "rgba(0,0,0,0.25)", border: "1px solid var(--border)", maxHeight: 300, overflowY: "auto" }}>
          <div className="faint" style={{ marginBottom: 6 }}>LLM 原始响应:</div>
          <pre style={{ fontSize: 11, color: "var(--text-2)", whiteSpace: "pre-wrap", margin: 0 }}>{rawText || "(空)"}</pre>
        </div>
      )}
      {showPrompt && (
        <div style={{ marginBottom: 12, padding: 12, borderRadius: 10, background: "rgba(0,0,0,0.25)", border: "1px solid var(--border)", maxHeight: 300, overflowY: "auto" }}>
          <div className="faint" style={{ marginBottom: 6 }}>使用的 Prompt:</div>
          <pre style={{ fontSize: 11, color: "var(--text-2)", whiteSpace: "pre-wrap", margin: 0 }}>{promptText || "(空)"}</pre>
        </div>
      )}

      {/* 分屏:左源文 + 右字段 */}
      <div className="extract-split" style={{ height: "calc(100vh - 200px)" }}>
        {/* 左:源文本 */}
        <div ref={sourceRef} className="extract-source">
          {renderSourceText()}
        </div>

        {/* 右:字段表单 */}
        <div className="extract-fields">
          {searchField.trim() ? (
            // 搜索模式:平铺所有匹配字段
            filteredEntries.map(([name, field]) => (
              <FieldCard
                key={name}
                name={name}
                field={field}
                active={activeField === name}
                onClick={() => handleFieldClick(name)}
                onSave={(v) => editExtractFields(currentPatientId, { [name]: v })}
              />
            ))
          ) : (
            // 分组模式
            Object.entries(grouped).map(([groupName, fieldList]) => (
              <FieldGroup
                key={groupName}
                name={groupName}
                fields={fieldList}
                activeField={activeField}
                onFieldClick={handleFieldClick}
                onSave={(name, v) => editExtractFields(currentPatientId, { [name]: v })}
              />
            ))
          )}
        </div>
      </div>
    </>
  );
}

function FieldGroup({
  name,
  fields,
  activeField,
  onFieldClick,
  onSave,
}: {
  name: string;
  fields: [string, ExtractedField][];
  activeField: string | null;
  onFieldClick: (name: string) => void;
  onSave: (name: string, v: any) => void;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="field-group">
      <div className="field-group-header" onClick={() => setExpanded(!expanded)}>
        <span className={`field-group-arrow ${expanded ? "expanded" : ""}`}></span>
        <span>{name}</span>
        <span className="faint">({fields.length})</span>
      </div>
      {expanded && (
        <div className="field-group-content">
          {fields.map(([fname, field]) => (
            <FieldCard
              key={fname}
              name={fname}
              field={field}
              active={activeField === fname}
              onClick={() => onFieldClick(fname)}
              onSave={(v) => onSave(fname, v)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FieldCard({
  name,
  field,
  active,
  onClick,
  onSave,
}: {
  name: string;
  field: ExtractedField;
  active: boolean;
  onClick: () => void;
  onSave: (v: any) => void;
}) {
  const value = typeof field === "object" && field !== null ? field.value : field;
  const edited = typeof field === "object" && field !== null ? field.edited : false;
  const isUnmentioned = value === "-1" || value === -1;
  const isExist = isExistentialField(name, value);
  const isNumeric = isNumericField(name, value);
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(String(value ?? ""));

  useEffect(() => {
    setVal(String(value ?? ""));
  }, [value]);

  const handleSave = () => {
    let parsedVal: any = val;
    if (isNumeric && val !== "-1" && val !== "") {
      parsedVal = Number(val);
      if (isNaN(parsedVal)) parsedVal = val;
    }
    onSave(parsedVal);
    setEditing(false);
  };

  const cardClass = `field-card ${edited ? "edited" : ""} ${isUnmentioned ? "unmentioned" : ""} ${active ? "active" : ""}`;

  return (
    <div className={cardClass} onClick={onClick}>
      <div className="field-name">
        <span>{name}</span>
        {edited && <span className="field-badge edited"></span>}
        {isUnmentioned && <span className="field-badge unmentioned">未提及</span>}
      </div>
      {editing ? (
        <div style={{ display: "flex", gap: 4 }}>
          {isExist ? (
            <select
              value={val}
              onChange={(e) => setVal(e.target.value)}
              autoFocus
              onClick={(e) => e.stopPropagation()}
            >
              <option value="1">有</option>
              <option value="0">无</option>
              <option value="-1">未提及</option>
            </select>
          ) : (
            <input
              value={val}
              onChange={(e) => setVal(e.target.value)}
              autoFocus
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave();
                if (e.key === "Escape") setEditing(false);
              }}
            />
          )}
          <button className="btn btn-sm btn-primary" onClick={(e) => { e.stopPropagation(); handleSave(); }}>✓</button>
          <button className="btn btn-sm" onClick={(e) => { e.stopPropagation(); setEditing(false); }}>×</button>
        </div>
      ) : (
        <div
          className={`field-value ${isUnmentioned ? "unmentioned" : ""}`}
          onClick={(e) => { e.stopPropagation(); setEditing(true); }}
          title="点击编辑"
        >
          {isExist
            ? value === 1 || value === "1" ? "有" : value === 0 || value === "0" ? "无" : isUnmentioned ? "未提及 (-1)" : String(value ?? "")
            : isUnmentioned ? "-1" : String(value ?? "")}
        </div>
      )}
    </div>
  );
}

function extractKeywords(fieldName: string): string[] {
  const cleaned = fieldName.replace(/\(.*?\)/g, "").replace(/（.*?）/g, "").trim();
  const keywords = [cleaned];
  const core = cleaned.replace(/病史$/, "").replace(/情况$/, "").replace(/下降$/, "").trim();
  if (core && core !== cleaned) keywords.push(core);
  const diseaseMatch = cleaned.match(/(高血压|糖尿病|冠心病|心功能不全|心肌梗死|脑梗塞|脑梗|高脂血症)/);
  if (diseaseMatch) keywords.push(diseaseMatch[1]);
  const labMatch = cleaned.match(/(血红蛋白|白细胞|血小板|肌酐|尿酸|血沉|CRP|C反应蛋白|胆固醇|甘油三酯|白介素|IgG|IgM|IgA|补体|肌钙蛋白)/);
  if (labMatch) keywords.push(labMatch[1]);
  return keywords;
}

/** 在容器文本节点中查找关键词并包一层 mark */
function findAndHighlight(root: HTMLElement, keyword: string): HTMLElement | null {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const q = keyword.toLowerCase();
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const text = node.textContent || "";
    const idx = text.toLowerCase().indexOf(q);
    if (idx < 0) continue;
    const range = document.createRange();
    range.setStart(node, idx);
    range.setEnd(node, idx + keyword.length);
    const mark = document.createElement("mark");
    mark.className = "field-hit";
    mark.dataset.keyword = keyword;
    mark.style.background = "rgba(91,91,214,0.35)";
    mark.style.color = "var(--text)";
    mark.style.borderRadius = "2px";
    mark.style.padding = "0 2px";
    try {
      range.surroundContents(mark);
      return mark;
    } catch {
      continue;
    }
  }
  return null;
}
