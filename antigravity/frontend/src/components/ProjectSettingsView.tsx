import { useEffect, useState } from "react";
import { useWorkbench } from "../store/workbench";
import { api, type ProjectConfig } from "../api/client";
import PathInput from "./PathInput";
import OcrPanel, { type OcrPanelValue } from "./OcrPanel";

/**
 * 项目设置：模板必配；OCR/LLM 默认继承全局，可开关覆盖。
 */
export default function ProjectSettingsView({ onClose }: { onClose?: () => void }) {
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const projects = useWorkbench((s) => s.projects);
  const loadProjects = useWorkbench((s) => s.loadProjects);
  const addToast = useWorkbench((s) => s.addToast);

  const project = projects.find((p) => p.id === currentProjectId);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<ProjectConfig | null>(null);

  const [template, setTemplate] = useState("");
  const [outputExcel, setOutputExcel] = useState("");
  const [makeDocx, setMakeDocx] = useState(false);

  const [ocrUseGlobal, setOcrUseGlobal] = useState(true);
  const [llmUseGlobal, setLlmUseGlobal] = useState(true);
  const [execUseGlobal, setExecUseGlobal] = useState(true);
  const [projectParallel, setProjectParallel] = useState(1);
  const [globalParallel, setGlobalParallel] = useState(1);

  const [ocr, setOcr] = useState<OcrPanelValue>({
    url: "",
    model: "PaddleOCR-VL-1.5",
    preset: "paper_photo",
    params: {},
    token: "",
  });

  const [provider, setProvider] = useState("DeepSeek");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [temperature, setTemperature] = useState(0);
  const [maxTokens, setMaxTokens] = useState(8000);
  const [providers, setProviders] = useState<{ name: string; default_url: string }[]>([]);

  useEffect(() => {
    api.getLlmProviders().then(setProviders).catch(() => {});
  }, []);

  useEffect(() => {
    if (!currentProjectId) return;
    setLoading(true);
    api
      .getProjectConfig(currentProjectId)
      .then((cfg) => {
        setConfig(cfg);
        setTemplate(cfg.pipeline.extraction_template || "");
        setOutputExcel(cfg.pipeline.output_excel || "");
        setMakeDocx(!!cfg.pipeline.make_docx);

        const ocrGlobal = cfg.ocr_use_global !== false;
        const llmGlobal = cfg.llm_use_global !== false;
        setOcrUseGlobal(ocrGlobal);
        setLlmUseGlobal(llmGlobal);
        const execGlobal = cfg.execution_use_global !== false;
        setExecUseGlobal(execGlobal);
        setGlobalParallel(cfg.global_max_parallel_patients ?? 1);
        setProjectParallel(
          cfg.max_parallel_patients ??
            cfg.effective_max_parallel_patients ??
            cfg.global_max_parallel_patients ??
            1,
        );

        // 面板展示 effective；覆盖模式下编辑的是项目值
        const srcOcr = ocrGlobal ? cfg.global_ocr : cfg.ocr;
        const params = srcOcr?.custom_params || {};
        setOcr({
          url: srcOcr?.url || "",
          model: srcOcr?.model || "PaddleOCR-VL-1.5",
          preset: srcOcr?.preset || "paper_photo",
          params,
          token: "",
        });
        if (!params || Object.keys(params).length === 0) {
          api.getPresetDetails(srcOcr?.preset || "paper_photo").then((r) => {
            setOcr((prev) => ({ ...prev, params: r.payload || {} }));
          }).catch(() => {});
        }

        const srcLlm = llmGlobal ? cfg.global_llm : cfg.llm;
        setProvider(srcLlm?.provider || "DeepSeek");
        setModel(srcLlm?.model || "");
        setBaseUrl(srcLlm?.base_url || "");
        setTemperature(srcLlm?.temperature ?? 0);
        setMaxTokens(srcLlm?.max_tokens ?? 8000);
      })
      .catch((e) => addToast("error", e.message || "加载项目配置失败"))
      .finally(() => setLoading(false));
  }, [currentProjectId]);

  if (!currentProjectId || !project) {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">请先选择项目</div>
      </div>
    );
  }

  if (loading || !config) {
    return (
      <div style={{ padding: 20 }}>
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line short" />
      </div>
    );
  }

  const enableOcrOverride = () => {
    // 从全局 effective 拷一份作为起点
    const g = config.global_ocr || config.ocr;
    setOcrUseGlobal(false);
    setOcr({
      url: g.url || "",
      model: g.model || "PaddleOCR-VL-1.5",
      preset: g.preset || "paper_photo",
      params: { ...(g.custom_params || {}) },
      token: "",
    });
  };

  const enableLlmOverride = () => {
    const g = config.global_llm || config.llm;
    setLlmUseGlobal(false);
    setProvider(g.provider || "DeepSeek");
    setModel(g.model || "");
    setBaseUrl(g.base_url || "");
    setTemperature(g.temperature ?? 0);
    setMaxTokens(g.max_tokens ?? 8000);
  };

  const saveAll = async () => {
    setSaving(true);
    try {
      await api.updateProjectPipeline(currentProjectId, {
        extraction_template: template,
        output_excel: outputExcel,
        make_docx: makeDocx,
      });

      if (ocrUseGlobal) {
        await api.updateProjectOCR(currentProjectId, { use_global: true });
      } else {
        await api.updateProjectOCR(currentProjectId, {
          use_global: false,
          url: ocr.url,
          model: ocr.model,
          preset: ocr.preset,
          custom_params: ocr.params,
        });
      }

      if (llmUseGlobal) {
        await api.updateProjectLLM(currentProjectId, { use_global: true });
      } else {
        await api.updateProjectLLM(currentProjectId, {
          use_global: false,
          provider,
          model,
          base_url: baseUrl,
          temperature,
          max_tokens: maxTokens,
        });
      }

      if (execUseGlobal) {
        await api.updateProjectExecution(currentProjectId, { use_global: true });
      } else {
        await api.updateProjectExecution(currentProjectId, {
          use_global: false,
          max_parallel_patients: projectParallel,
        });
      }

      await loadProjects();
      addToast("success", "项目配置已保存");
      onClose?.();
    } catch (e: any) {
      addToast("error", e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const gOcr = config.global_ocr;
  const gLlm = config.global_llm;

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <div className="h1" style={{ marginBottom: 6 }}>项目设置</div>
      <div className="sub" style={{ marginBottom: 12 }}>
        {project.name} · {project.source_type}
      </div>
      <div
        style={{
          marginBottom: 16,
          padding: "10px 12px",
          borderRadius: 8,
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          fontSize: 12,
          color: "var(--text-2)",
          lineHeight: 1.6,
        }}
      >
        运行时：<strong>项目覆盖 &gt; 全局默认</strong>
        <br />
        Token / 预设库在全局；本页只配模板与可选覆盖。
      </div>

      <Section title="抽取模板（本项目必配）">
        <Field label="模板路径" hint="Excel 或字段 JSON">
          <PathInput
            value={template}
            onChange={setTemplate}
            mode="file"
            filters={[{ name: "模板", extensions: ["xlsx", "xls", "json"] }]}
            placeholder="/path/to/模板.xlsx"
          />
        </Field>
        <Field label="导出 Excel 路径">
          <PathInput
            value={outputExcel}
            onChange={setOutputExcel}
            mode="save"
            filters={[{ name: "Excel", extensions: ["xlsx"] }]}
          />
        </Field>
      </Section>

      <Section title="批量加速">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
            <input
              type="radio"
              checked={execUseGlobal}
              onChange={() => setExecUseGlobal(true)}
              style={{ width: "auto" }}
            />
            与全局一致（当前全局：{globalParallel} 人）
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
            <input
              type="radio"
              checked={!execUseGlobal}
              onChange={() => setExecUseGlobal(false)}
              style={{ width: "auto" }}
            />
            本项目单独设置
            {!execUseGlobal && (
              <select
                value={projectParallel}
                onChange={(e) => setProjectParallel(Number(e.target.value))}
                style={{ marginLeft: 4, width: 72 }}
              >
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>{n} 人</option>
                ))}
              </select>
            )}
          </label>
        </div>
        <div className="faint" style={{ marginTop: 8, fontSize: 12 }}>
          实际生效：{execUseGlobal ? globalParallel : projectParallel} 人 · 仅批量/流水线
        </div>
      </Section>

      <Section title="导出选项">
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={makeDocx} onChange={(e) => setMakeDocx(e.target.checked)} style={{ width: "auto" }} />
          合并时生成 .docx
        </label>
        {template ? (
          <div className="faint" style={{ marginTop: 8, color: "var(--success)" }}>已配置模板</div>
        ) : (
          <div className="faint" style={{ marginTop: 8, color: "var(--warning)" }}>未配置模板</div>
        )}
      </Section>

      <Section title="飞桨 OCR">
        <InheritBar
          useGlobal={ocrUseGlobal}
          label="继承全局 OCR"
          summary={
            gOcr
              ? `${gOcr.model || "—"} · ${gOcr.preset || "—"} · Token ${gOcr.token_configured ? "已配" : "未配"}`
              : "—"
          }
          onInherit={() => setOcrUseGlobal(true)}
          onOverride={enableOcrOverride}
        />
        {ocrUseGlobal ? (
          <div className="faint" style={{ fontSize: 12, lineHeight: 1.6 }}>
            使用全局默认。改模型/参数请到「全局设置」，或点「本项目覆盖」。
          </div>
        ) : (
          <OcrPanel
            value={ocr}
            onChange={setOcr}
            showConnection={true}
            showToken={false}
            tokenConfigured={!!gOcr?.token_configured}
            addToast={addToast}
          />
        )}
        {!ocrUseGlobal && (
          <div className="faint" style={{ marginTop: 8, fontSize: 11 }}>
            Token 使用全局配置（{gOcr?.token_configured ? "已配置" : "未配置"}）；此处只覆盖地址/模型/预设/参数。
          </div>
        )}
      </Section>

      <Section title="抽取 LLM">
        <InheritBar
          useGlobal={llmUseGlobal}
          label="继承全局 LLM"
          summary={
            gLlm
              ? `${gLlm.provider || "—"} · ${gLlm.model || "未填模型"} · Key ${gLlm.api_key_configured ? "已配" : "未配"}`
              : "—"
          }
          onInherit={() => setLlmUseGlobal(true)}
          onOverride={enableLlmOverride}
        />
        {llmUseGlobal ? (
          <div className="faint" style={{ fontSize: 12 }}>
            使用全局默认。API Key 仅在全局设置中配置。
          </div>
        ) : (
          <>
            <Field label="Provider">
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                {providers.map((p) => (
                  <option key={p.name} value={p.name}>{p.name}</option>
                ))}
              </select>
            </Field>
            <Field label="模型">
              <input value={model} onChange={(e) => setModel(e.target.value)} />
            </Field>
            <Field label="Base URL">
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </Field>
            <Field label={`Temperature: ${temperature.toFixed(2)}`}>
              <input type="range" min={0} max={2} step={0.05} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
            </Field>
            <Field label="Max Tokens">
              <input type="number" min={100} max={32000} step={100} value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} />
            </Field>
            <div className="faint" style={{ fontSize: 11 }}>
              API Key 请在全局设置中配置（本项目不存密钥）。
            </div>
          </>
        )}
      </Section>

      <div style={{ display: "flex", gap: 8, marginTop: 8, marginBottom: 24 }}>
        <button className="btn btn-primary" disabled={saving} onClick={saveAll}>
          {saving ? "保存中…" : "保存项目配置"}
        </button>
        {onClose && <button className="btn" onClick={onClose}>关闭</button>}
      </div>
    </div>
  );
}

function InheritBar({
  useGlobal,
  label,
  summary,
  onInherit,
  onOverride,
}: {
  useGlobal: boolean;
  label: string;
  summary: string;
  onInherit: () => void;
  onOverride: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 8,
        marginBottom: 12,
        padding: "8px 10px",
        borderRadius: 8,
        background: useGlobal ? "var(--success-fade)" : "var(--warning-fade)",
        border: `1px solid ${useGlobal ? "var(--success)" : "var(--warning)"}`,
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 600, color: useGlobal ? "var(--success)" : "var(--warning)" }}>
        {useGlobal ? label : "本项目覆盖"}
      </span>
      <span className="faint" style={{ fontSize: 11, flex: 1 }}>{summary}</span>
      {useGlobal ? (
        <button className="btn btn-sm" onClick={onOverride}>本项目覆盖</button>
      ) : (
        <button className="btn btn-sm" onClick={onInherit}>改回继承全局</button>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel" style={{ padding: 18, marginBottom: 14 }}>
      <div className="h2" style={{ marginBottom: 12 }}>{title}</div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label className="form-label">{label}</label>
      {children}
      {hint && <div className="faint" style={{ marginTop: 3 }}>{hint}</div>}
    </div>
  );
}
