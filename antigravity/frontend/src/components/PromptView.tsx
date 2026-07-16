import { useState, useEffect, useRef } from "react";
import { useWorkbench } from "../store/workbench";
import { api } from "../api/client";

type Tab = "global" | "fields" | "md";

export default function PromptView() {
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const projects = useWorkbench((s) => s.projects);
  const addToast = useWorkbench((s) => s.addToast);

  const [tab, setTab] = useState<Tab>("global");
  const [globalPrompt, setGlobalPrompt] = useState("");
  const [fields, setFields] = useState<Record<string, any>>({});
  const [mdText, setMdText] = useState("");
  const [mdPath, setMdPath] = useState("");
  const [hasMd, setHasMd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedField, setSelectedField] = useState<string | null>(null);

  const currentProject = projects.find((p) => p.id === currentProjectId);

  useEffect(() => {
    if (currentProjectId) {
      loadPrompt();
    }
  }, [currentProjectId]);

  const loadPrompt = async () => {
    if (!currentProjectId) return;
    setLoading(true);
    try {
      const data = await api.getPrompt(currentProjectId);
      setGlobalPrompt(data.global || "");
      setFields(data.fields || {});
      setHasMd(data.has_engineered_md);
      if (data.has_engineered_md) {
        const md = await api.getPromptMd(currentProjectId);
        setMdText(md.text);
        setMdPath(md.path);
      } else {
        setMdText("");
        setMdPath("");
      }
    } catch (e) {
      console.error("loadPrompt", e);
    } finally {
      setLoading(false);
    }
  };

  if (!currentProjectId) {
    return (
      <div className="empty-state" style={{ height: "100%" }}>
        <div className="empty-icon"></div>
        <div className="empty-title">请先选择项目</div>
        <div className="empty-desc">提示词工程是项目级配置</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ padding: 20 }}>
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line short" />
        <div className="skeleton skeleton-line" />
      </div>
    );
  }

  // ─── 生成字段规则 ───
  const handleGenerate = async (useLlm: boolean) => {
    if (!currentProject?.has_template) {
      addToast("warning", "请先在「项目设置」中配置抽取模板（Excel）");
      return;
    }
    if (useLlm && !currentProject?.llm_api_key_configured) {
      addToast("warning", "请先在「项目设置」→「项目抽取 LLM」填写 API Key 和模型后再增强");
      return;
    }
    setGenerating(true);
    try {
      // 不硬编码 openai：后端按项目配置的 provider/base_url/model 解析
      const result = await api.generatePrompt(currentProjectId, useLlm, "");
      setFields(result.fields || {});
      const msg =
        (result as any).message ||
        `已生成 ${result.field_count} 个字段规则${useLlm ? (result as any).llm_used ? "（LLM增强）" : "（规则已生成，增强可能失败）" : ""}`;
      if (useLlm && (result as any).llm_error) {
        addToast("warning", msg);
      } else {
        addToast("success", msg);
      }
      // 切到字段 Tab 方便查看
      setTab("fields");
    } catch (e: any) {
      addToast("error", e.message || "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  // ─── 渲染最终 .md ───
  const handleRender = async () => {
    if (Object.keys(fields).length === 0) {
      addToast("warning", "请先生成字段规则");
      return;
    }
    setRendering(true);
    try {
      const title = currentProject?.name || "病历数据提取规范";
      const result = await api.renderPromptMd(currentProjectId, title, "1.0", globalPrompt);
      setMdText("");
      setMdPath(result.path);
      setHasMd(true);
      // 重新加载 md
      const md = await api.getPromptMd(currentProjectId);
      setMdText(md.text);
      addToast("success", `提示词工程已渲染: ${result.char_count} 字`);
    } catch (e: any) {
      addToast("error", e.message || "渲染失败");
    } finally {
      setRendering(false);
    }
  };

  // ─── 保存 ───
  const handleSaveGlobal = async () => {
    setSaving(true);
    try {
      await api.updatePromptGlobal(currentProjectId, globalPrompt);
      addToast("success", "全局提示词已保存");
    } catch (e: any) {
      addToast("error", e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveFields = async () => {
    setSaving(true);
    try {
      await api.updatePromptFields(currentProjectId, fields);
      addToast("success", "字段规则已保存");
    } catch (e: any) {
      addToast("error", e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveMd = async () => {
    setSaving(true);
    try {
      await api.updatePromptMd(currentProjectId, mdText);
      addToast("success", "提示词 .md 已保存");
    } catch (e: any) {
      addToast("error", e.message);
    } finally {
      setSaving(false);
    }
  };

  // 字段分组
  const fieldEntries = Object.entries(fields);
  const grouped: Record<string, [string, any][]> = {};
  for (const [name, data] of fieldEntries) {
    const cat = data.category || "未分组";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push([name, data]);
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* 工具条 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexShrink: 0, flexWrap: "wrap" }}>
        <div className="h1">提示词工程</div>
        <span className="sub">{currentProject?.name}</span>
        {hasMd && <span style={{ fontSize: 11, color: "var(--success)", padding: "2px 8px", borderRadius: 10, background: "var(--success-fade)" }}>✓ 已生成 .md</span>}
        <div style={{ flex: 1 }} />
        <button className="btn btn-sm" onClick={() => handleGenerate(false)} disabled={generating}>
          {generating ? "生成中…" : "从模板生成"}
        </button>
        <button
          className="btn btn-sm"
          onClick={() => handleGenerate(true)}
          disabled={generating}
          title={
            !currentProject?.llm_api_key_configured
              ? "需先在项目设置里配置 LLM API Key"
              : `使用项目 LLM：${(currentProject as any)?.llm_provider || ""} ${(currentProject as any)?.llm_model || ""}`
          }
        >
          {generating ? "增强中…" : "LLM增强生成"}
        </button>
        <button className="btn btn-sm btn-primary" onClick={handleRender} disabled={rendering || fieldEntries.length === 0}>
          {rendering ? "渲染中…" : "渲染 .md"}
        </button>
      </div>

      {!currentProject?.has_template && (
        <div style={{ padding: 10, borderRadius: 10, background: "var(--warning-fade)", border: "1px solid var(--warning)", marginBottom: 12, fontSize: 12, color: "var(--warning)" }}>
          ! 项目未配置抽取模板。请关闭此窗口，点击顶栏「项目设置」指定 Excel 模板路径
        </div>
      )}

      {/* Tab 切换 */}
      <div style={{ display: "flex", gap: 4, marginBottom: 12, flexShrink: 0 }}>
        <TabButton active={tab === "global"} onClick={() => setTab("global")}>📌 全局提示词</TabButton>
        <TabButton active={tab === "fields"} onClick={() => setTab("fields")}>📋 字段规则 ({fieldEntries.length})</TabButton>
        <TabButton active={tab === "md"} onClick={() => setTab("md")}>最终 .md {hasMd ? "✓" : ""}</TabButton>
      </div>

      {/* 内容区 */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>
        {tab === "global" && (
          <GlobalTab
            globalPrompt={globalPrompt}
            setGlobalPrompt={setGlobalPrompt}
            onSave={handleSaveGlobal}
            saving={saving}
          />
        )}
        {tab === "fields" && (
          <FieldsTab
            grouped={grouped}
            fields={fields}
            setFields={setFields}
            selectedField={selectedField}
            setSelectedField={setSelectedField}
            onSave={handleSaveFields}
            saving={saving}
          />
        )}
        {tab === "md" && (
          <MdTab
            mdText={mdText}
            setMdText={setMdText}
            mdPath={mdPath}
            hasMd={hasMd}
            onSave={handleSaveMd}
            saving={saving}
            onRender={handleRender}
          />
        )}
      </div>
    </div>
  );
}

// ─── Tab 按钮 ───
function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      className={`btn btn-sm ${active ? "btn-primary" : ""}`}
      onClick={onClick}
      style={{ borderRadius: "20px", padding: "6px 14px" }}
    >
      {children}
    </button>
  );
}

// ─── 全局提示词 Tab ───
function GlobalTab({ globalPrompt, setGlobalPrompt, onSave, saving }: any) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="faint">
        项目级全局提示词，会替换默认的角色描述和任务说明。填写疾病领域背景、特殊规则、输出格式要求等。
      </div>
      <textarea
        value={globalPrompt}
        onChange={(e) => setGlobalPrompt(e.target.value)}
        style={{
          flex: 1, minHeight: 300, fontSize: 13, lineHeight: 1.8,
          fontFamily: "inherit", resize: "none",
        }}
        placeholder={`示例：

你是一个专业的大动脉炎病历数据提取AI助手。必须严格基于病历原文，准确提取病例信息，不推测不臆断。

疾病背景：大动脉炎是一种累及主动脉及其主要分支的慢性非特异性炎症性疾病...

特殊规则：
1. 四肢血压差异是重要诊断依据
2. 炎症指标(血沉、CRP)是活动度评估关键
3. 血管壁FDG摄取增高提示活动性炎症`}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-sm btn-primary" onClick={onSave} disabled={saving}>
          {saving ? "保存中…" : "保存全局提示词"}
        </button>
        <span className="faint">{globalPrompt.length} 字</span>
      </div>
    </div>
  );
}

// ─── 字段规则 Tab ───
function FieldsTab({ grouped, fields, setFields, selectedField, setSelectedField, onSave, saving }: any) {
  const fieldNames = Object.keys(fields);

  if (fieldNames.length === 0) {
    return (
      <div className="empty-state" style={{ flex: 1 }}>
        <div className="empty-icon">📋</div>
        <div className="empty-title">尚无字段规则</div>
        <div className="empty-desc">点击上方「从模板生成」按钮，从 Excel 模板自动生成字段规则</div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", gap: 12, overflow: "hidden" }}>
      {/* 左:字段列表 */}
      <div style={{ width: 240, flexShrink: 0, overflowY: "auto", paddingRight: 8, borderRight: "1px solid var(--border)" }}>
        {Object.entries(grouped).map(([category, fieldList]: any) => (
          <div key={category} style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: "var(--text-2)", fontWeight: 600, marginBottom: 6, padding: "4px 8px", background: "var(--surface-2)", borderRadius: 6 }}>
              {category} ({fieldList.length})
            </div>
            {fieldList.map(([name]: any) => (
              <div
                key={name}
                onClick={() => setSelectedField(name)}
                style={{
                  padding: "5px 10px", fontSize: 12, cursor: "pointer", borderRadius: 6,
                  background: selectedField === name ? "var(--primary-fade)" : "transparent",
                  color: selectedField === name ? "var(--primary)" : "var(--text-2)",
                  transition: "all 150ms ease-out",
                  marginBottom: 2,
                }}
              >
                {name}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* 右:字段编辑 */}
      <div style={{ flex: 1, overflowY: "auto", paddingLeft: 8 }}>
        {selectedField && fields[selectedField] ? (
          <FieldEditor
            name={selectedField}
            data={fields[selectedField]}
            onUpdate={(newData: any) => {
              setFields({ ...fields, [selectedField]: newData });
            }}
          />
        ) : (
          <div className="empty-state" style={{ height: "100%" }}>
            <div className="empty-icon">👈</div>
            <div className="empty-desc">从左侧选择一个字段编辑规则</div>
          </div>
        )}
        <div style={{ marginTop: 16 }}>
          <button className="btn btn-sm btn-primary" onClick={onSave} disabled={saving}>
            {saving ? "保存中…" : "保存所有字段规则"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── 单字段编辑器 ───
function FieldEditor({ name, data, onUpdate }: { name: string; data: any; onUpdate: (data: any) => void }) {
  const update = (key: string, value: any) => {
    onUpdate({ ...data, [key]: value });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="h2">{name}</div>

      <div className="form-group">
        <label className="form-label">分类</label>
        <input value={data.category || ""} onChange={(e) => update("category", e.target.value)} />
      </div>

      <div className="form-group">
        <label className="form-label">类型 (direct/existence/report/numeric/memo)</label>
        <select value={data.variable_type || "direct"} onChange={(e) => update("variable_type", e.target.value)}>
          <option value="direct">直接提取 (direct)</option>
          <option value="existence">存在性判断 (existence)</option>
          <option value="report">报告内容提取 (report)</option>
          <option value="numeric">数值提取 (numeric)</option>
          <option value="memo">备注 (memo)</option>
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">描述</label>
        <textarea value={data.description || ""} onChange={(e) => update("description", e.target.value)} style={{ minHeight: 60, resize: "vertical" }} />
      </div>

      <div className="form-group">
        <label className="form-label">同义词 (逗号分隔)</label>
        <input
          value={Array.isArray(data.synonyms) ? data.synonyms.join(", ") : ""}
          onChange={(e) => update("synonyms", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
          placeholder="高血压, 高血压病, HTN, hypertension"
        />
      </div>

      <div className="form-group">
        <label className="form-label">取值规则</label>
        <textarea value={data.rules || ""} onChange={(e) => update("rules", e.target.value)} style={{ minHeight: 80, resize: "vertical" }}
          placeholder="1=诊断明确提及&#10;0=明确否认&#10;-1=未提及" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="form-group">
          <label className="form-label">单位</label>
          <input value={data.unit || ""} onChange={(e) => update("unit", e.target.value)} placeholder="g/L, mm/h" />
        </div>
        <div className="form-group">
          <label className="form-label">取值规则(数值)</label>
          <input value={data.value_rule || ""} onChange={(e) => update("value_rule", e.target.value)} placeholder="取最高值/最低值" />
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">提取示例</label>
        <textarea value={data.example || ""} onChange={(e) => update("example", e.target.value)} style={{ minHeight: 60, resize: "vertical" }}
          placeholder='原文: "高血压病史8年余" → 提取: 1' />
      </div>

      <div className="form-group">
        <label className="form-label">特别注意</label>
        <textarea value={data.notes || ""} onChange={(e) => update("notes", e.target.value)} style={{ minHeight: 40, resize: "vertical" }} />
      </div>
    </div>
  );
}

// ─── 最终 .md Tab ───
function MdTab({ mdText, setMdText, mdPath, hasMd, onSave, saving, onRender }: any) {
  const [editing, setEditing] = useState(false);

  if (!hasMd && !mdText) {
    return (
      <div className="empty-state" style={{ flex: 1 }}>
        <div className="empty-icon"></div>
        <div className="empty-title">尚未生成提示词 .md</div>
        <div className="empty-desc">先生成字段规则，再点击「渲染 .md」按钮</div>
        <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={onRender}>渲染 .md</button>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        <span className="faint" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {mdPath}
        </span>
        {editing ? (
          <>
            <button className="btn btn-sm btn-primary" onClick={() => { onSave(); setEditing(false); }} disabled={saving}>
              {saving ? "" : "保存"}
            </button>
            <button className="btn btn-sm" onClick={() => setEditing(false)}>只读</button>
          </>
        ) : (
          <>
            <button className="btn btn-sm" onClick={() => setEditing(true)}>编辑</button>
            <button className="btn btn-sm" onClick={onRender}>重新渲染</button>
          </>
        )}
        <span className="faint">{mdText.length} 字</span>
      </div>

      {editing ? (
        <textarea
          value={mdText}
          onChange={(e) => setMdText(e.target.value)}
          style={{
            flex: 1, fontSize: 12, lineHeight: 1.7, fontFamily: "'SF Mono', 'DejaVu Sans Mono', monospace",
            resize: "none",
          }}
        />
      ) : (
        <div
          style={{
            flex: 1, overflowY: "auto", padding: 20,
            background: "rgba(0,0,0,0.15)", borderRadius: 10, border: "1px solid var(--border)",
            fontSize: 13, lineHeight: 1.8, color: "var(--text-2)",
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}
        >
          {mdText}
        </div>
      )}
    </div>
  );
}
