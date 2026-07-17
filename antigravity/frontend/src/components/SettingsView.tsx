import { useState, useEffect } from "react";
import { useWorkbench } from "../store/workbench";
import { api } from "../api/client";
import OcrPanel, { type OcrPanelValue } from "./OcrPanel";

/**
 * 全局设置 = 账号 + 默认策略。
 * 抽取模板 / 项目覆盖 → 项目设置。
 */
export default function SettingsView() {
  const settings = useWorkbench((s) => s.settings);
  const loadSettings = useWorkbench((s) => s.loadSettings);
  const addToast = useWorkbench((s) => s.addToast);

  const [llmProviders, setLlmProviders] = useState<{ name: string; default_url: string }[]>([]);

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
  const [apiKey, setApiKey] = useState("");
  const [temperature, setTemperature] = useState(0.0);
  const [maxTokens, setMaxTokens] = useState(8000);
  const [testingLlm, setTestingLlm] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [testingOcr, setTestingOcr] = useState(false);
  const [ocrTestResult, setOcrTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  // Agent LLM（独立）
  const [agentProvider, setAgentProvider] = useState("DeepSeek");
  const [agentModel, setAgentModel] = useState("");
  const [agentBaseUrl, setAgentBaseUrl] = useState("");
  const [agentApiKey, setAgentApiKey] = useState("");
  const [agentTemperature, setAgentTemperature] = useState(0.2);
  const [agentMaxTokens, setAgentMaxTokens] = useState(2000);
  const [testingAgent, setTestingAgent] = useState(false);
  const [agentTestResult, setAgentTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [savedSection, setSavedSection] = useState("");
  const [parallelPatients, setParallelPatients] = useState(1);

  useEffect(() => {
    api.getLlmProviders().then(setLlmProviders).catch(() => {});
  }, []);

  useEffect(() => {
    if (!settings) return;
    setOcr({
      url: settings.ocr.url || "",
      model: settings.ocr.model || "PaddleOCR-VL-1.5",
      preset: settings.ocr.preset || "paper_photo",
      params: settings.ocr.custom_params || {},
      token: "",
    });
    if (!settings.ocr.custom_params || Object.keys(settings.ocr.custom_params).length === 0) {
      api.getPresetDetails(settings.ocr.preset || "paper_photo").then((r) => {
        setOcr((prev) => ({ ...prev, params: r.payload || {} }));
      }).catch(() => {});
    }
    setProvider(settings.extract_llm.provider || "DeepSeek");
    setModel(settings.extract_llm.model);
    setBaseUrl(settings.extract_llm.base_url);
    setTemperature(settings.extract_llm.temperature);
    setMaxTokens(settings.extract_llm.max_tokens);
    const ag = settings.agent_llm;
    if (ag) {
      setAgentProvider(ag.provider || "DeepSeek");
      setAgentModel(ag.model || "");
      setAgentBaseUrl(ag.base_url || "");
      setAgentTemperature(ag.temperature ?? 0.2);
      setAgentMaxTokens(ag.max_tokens ?? 2000);
    }
    const n = settings.execution?.max_parallel_patients ?? 1;
    setParallelPatients(Math.max(1, Math.min(4, Number(n) || 1)));
  }, [settings]);

  const showSaved = (section: string) => {
    setSavedSection(section);
    setTimeout(() => setSavedSection(""), 2000);
  };

  const handleSaveOcr = async () => {
    try {
      await api.updateOcr({
        url: ocr.url,
        model: ocr.model,
        preset: ocr.preset,
        custom_params: ocr.params,
        ...(ocr.token ? { token: ocr.token } : {}),
      });
      setOcr((p) => ({ ...p, token: "" }));
      await loadSettings();
      showSaved("ocr");
      addToast("success", "全局 OCR 默认已保存");
    } catch (e: any) {
      addToast("error", e.message || "保存失败");
    }
  };

  const handleTestOcr = async () => {
    setTestingOcr(true);
    setOcrTestResult(null);
    try {
      const result = await api.testOcr({
        url: ocr.url,
        model: ocr.model,
        ...(ocr.token ? { token: ocr.token } : {}),
      });
      setOcrTestResult(result);
      if (result.ok) addToast("success", "OCR 连接测试成功");
      else addToast("error", result.message);
    } catch (e: any) {
      setOcrTestResult({ ok: false, message: e.message });
      addToast("error", e.message || "测试失败");
    } finally {
      setTestingOcr(false);
    }
  };

  const handleProviderChange = (name: string) => {
    setProvider(name);
    const p = llmProviders.find((x) => x.name === name);
    if (p?.default_url) setBaseUrl(p.default_url);
  };

  const handleSaveLlm = async () => {
    try {
      await api.updateExtractLLM({
        provider,
        model,
        base_url: baseUrl,
        temperature,
        max_tokens: maxTokens,
        ...(apiKey ? { api_key: apiKey } : {}),
      });
      setApiKey("");
      await loadSettings();
      showSaved("llm");
      addToast("success", "全局 LLM 默认已保存");
    } catch (e: any) {
      addToast("error", e.message || "保存失败");
    }
  };

  const handleAgentProviderChange = (name: string) => {
    setAgentProvider(name);
    const p = llmProviders.find((x) => x.name === name);
    if (p?.default_url) setAgentBaseUrl(p.default_url);
  };

  const handleSaveAgentLlm = async () => {
    try {
      await api.updateAgentLLM({
        provider: agentProvider,
        model: agentModel,
        base_url: agentBaseUrl,
        temperature: agentTemperature,
        max_tokens: agentMaxTokens,
        ...(agentApiKey ? { api_key: agentApiKey } : {}),
      });
      setAgentApiKey("");
      await loadSettings();
      showSaved("agent");
      addToast("success", "Agent LLM 已保存");
    } catch (e: any) {
      addToast("error", e.message || "保存失败");
    }
  };

  const handleTestAgentLlm = async () => {
    setTestingAgent(true);
    setAgentTestResult(null);
    try {
      const result = await api.testAgentLLM({
        provider: agentProvider,
        model: agentModel,
        base_url: agentBaseUrl,
        ...(agentApiKey ? { api_key: agentApiKey } : {}),
      });
      setAgentTestResult(result);
      if (result.ok) addToast("success", "Agent LLM 连接成功");
      else addToast("error", result.message);
    } catch (e: any) {
      setAgentTestResult({ ok: false, message: e.message });
      addToast("error", e.message || "测试失败");
    } finally {
      setTestingAgent(false);
    }
  };

  const handleCopyFromExtract = async () => {
    try {
      const r = await api.copyAgentLLMFromExtract();
      await loadSettings();
      showSaved("agent");
      addToast("success", r.message || "已从抽取 LLM 复制");
    } catch (e: any) {
      addToast("error", e.message || "复制失败");
    }
  };

  const handleTestLlm = async () => {
    setTestingLlm(true);
    setLlmTestResult(null);
    try {
      const result = await api.testLLM({
        provider,
        model,
        base_url: baseUrl,
        ...(apiKey ? { api_key: apiKey } : {}),
      });
      setLlmTestResult(result);
      if (result.ok) addToast("success", "LLM 连接测试成功");
      else addToast("error", result.message);
    } catch (e: any) {
      setLlmTestResult({ ok: false, message: e.message });
      addToast("error", e.message || "测试失败");
    } finally {
      setTestingLlm(false);
    }
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "8px 0" }}>
      <div className="h1" style={{ marginBottom: 6 }}>全局设置</div>
      <div className="sub" style={{ marginBottom: 12 }}>
        账号与默认策略。运行时：<strong>项目覆盖 &gt; 全局默认</strong>
      </div>
      <div
        style={{
          marginBottom: 20,
          padding: "10px 12px",
          borderRadius: 8,
          background: "var(--primary-fade)",
          border: "1px solid var(--primary)",
          fontSize: 12,
          color: "var(--text-2)",
          lineHeight: 1.6,
        }}
      >
        · Token / API Key 只在这里配置<br />
        · OCR 用户预设库全局共享<br />
        · 批量可同时处理多名病人（见「批量加速」）<br />
        · 抽取模板、导出路径请到「项目设置」
      </div>

      <ConfigSection title="飞桨 OCR（默认）" saved={savedSection === "ocr"}>
        <OcrPanel
          value={ocr}
          onChange={setOcr}
          tokenConfigured={!!settings?.ocr.token_configured}
          addToast={addToast}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button className="btn btn-primary" onClick={handleSaveOcr}>保存默认 OCR</button>
          <button className="btn" onClick={handleTestOcr} disabled={testingOcr}>
            {testingOcr ? "测试中…" : "测试连接"}
          </button>
        </div>
        {ocrTestResult && <TestResult result={ocrTestResult} />}
      </ConfigSection>

      <ConfigSection title="抽取 LLM（默认）" saved={savedSection === "llm"}>
        <Field label="Provider">
          <select value={provider} onChange={(e) => handleProviderChange(e.target.value)}>
            {llmProviders.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
        </Field>
        <Field label="模型名称">
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="deepseek-chat / gpt-4o-mini" />
        </Field>
        <Field label="Base URL" hint="留空则用 Provider 默认">
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </Field>
        <Field label={`API Key ${settings?.extract_llm.api_key_configured ? "（已配置 ✓）" : "（未配置）"}`}>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="留空保留已有" />
        </Field>
        <Field label={`Temperature: ${temperature.toFixed(2)}`}>
          <input type="range" min={0} max={2} step={0.05} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
        </Field>
        <Field label="Max Tokens">
          <input type="number" min={100} max={32000} step={100} value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} />
        </Field>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSaveLlm}>保存默认 LLM</button>
          <button className="btn" onClick={handleTestLlm} disabled={testingLlm}>
            {testingLlm ? "测试中…" : "测试连接"}
          </button>
        </div>
        {llmTestResult && <TestResult result={llmTestResult} />}
      </ConfigSection>

<ConfigSection title="病例归档 LLM（独立）" saved={savedSection === "agent"}>
        <div className="faint" style={{ fontSize: 12, marginBottom: 10 }}>
          仅用于病例归档 Agent，与上方抽取 LLM 分离。未配置时走规则模式。
        </div>
        <Field label="Provider">
          <select value={agentProvider} onChange={(e) => handleAgentProviderChange(e.target.value)}>
            {llmProviders.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
        </Field>
        <Field label="模型名称">
          <input value={agentModel} onChange={(e) => setAgentModel(e.target.value)} placeholder="deepseek-chat / gpt-4o-mini" />
        </Field>
        <Field label="Base URL" hint="留空则用 Provider 默认">
          <input value={agentBaseUrl} onChange={(e) => setAgentBaseUrl(e.target.value)} />
        </Field>
        <Field label={`API Key ${settings?.agent_llm?.api_key_configured ? "（已配置 ✓）" : "（未配置）"}`}>
          <input type="password" value={agentApiKey} onChange={(e) => setAgentApiKey(e.target.value)} placeholder="留空保留已有" />
        </Field>
        <Field label={`Temperature: ${agentTemperature.toFixed(2)}`}>
          <input type="range" min={0} max={2} step={0.05} value={agentTemperature} onChange={(e) => setAgentTemperature(Number(e.target.value))} />
        </Field>
        <Field label="Max Tokens">
          <input type="number" min={100} max={32000} step={100} value={agentMaxTokens} onChange={(e) => setAgentMaxTokens(Number(e.target.value))} />
        </Field>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={handleSaveAgentLlm}>保存 Agent LLM</button>
          <button className="btn" onClick={handleTestAgentLlm} disabled={testingAgent}>
            {testingAgent ? "测试中…" : "测试连接"}
          </button>
          <button className="btn" onClick={handleCopyFromExtract} title="把抽取 LLM 的配置复制过来">
            从抽取 LLM 复制
          </button>
        </div>
        {agentTestResult && <TestResult result={agentTestResult} />}
      </ConfigSection>

      <ConfigSection title="批量加速" saved={savedSection === "execution"}>
        <div className="faint" style={{ fontSize: 12, marginBottom: 12, lineHeight: 1.6 }}>
          同时处理几个病人（仅影响批量与流水线；单人执行始终是 1）。
          <br />
          数字越大通常越快，也更容易触发 OCR/LLM 限流。建议先从 2 试起。
        </div>
        <Field label={`同时处理：${parallelPatients} 人`}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            {[1, 2, 3, 4].map((n) => (
              <button
                key={n}
                type="button"
                className={`btn btn-sm ${parallelPatients === n ? "btn-primary" : ""}`}
                onClick={() => setParallelPatients(n)}
              >
                {n}
                {n === 1 ? " 稳妥" : n <= 3 ? "" : " 慎用"}
              </button>
            ))}
          </div>
          <input
            type="range"
            min={1}
            max={4}
            step={1}
            value={parallelPatients}
            onChange={(e) => setParallelPatients(Number(e.target.value))}
            style={{ width: "100%" }}
          />
          <div className="faint" style={{ marginTop: 6, fontSize: 11 }}>
            1 稳妥（默认） · 2–3 常用 · 4 赶工慎用
          </div>
        </Field>
        {parallelPatients >= 4 && (
          <div style={{
            marginBottom: 12, padding: "8px 10px", borderRadius: 8, fontSize: 12,
            background: "var(--warning-fade, rgba(234,179,8,.12))",
            border: "1px solid var(--warning, #eab308)",
            color: "var(--text-2)",
          }}>
            同时过多可能触发接口限流或费用上升，建议从 2–3 试起。
          </div>
        )}
        <button
          className="btn btn-primary"
          onClick={async () => {
            try {
              const r = await api.updateExecution({ max_parallel_patients: parallelPatients });
              setParallelPatients(r.max_parallel_patients ?? parallelPatients);
              await loadSettings();
              showSaved("execution");
              addToast("success", `批量加速已保存：同时处理 ${r.max_parallel_patients ?? parallelPatients} 人`);
            } catch (e: any) {
              addToast("error", e.message || "保存失败");
            }
          }}
        >
          保存批量加速
        </button>
      </ConfigSection>

      <div style={{ height: 40 }} />
    </div>
  );
}

function ConfigSection({ title, saved, children }: { title: string; saved: boolean; children: React.ReactNode }) {
  return (
    <div className="panel" style={{ padding: 20, marginBottom: 16, borderColor: saved ? "var(--success)" : undefined, transition: "border-color 0.3s ease-out" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span className="h2">{title}</span>
        {saved && <span style={{ color: "var(--success)", fontSize: 12 }}>✓ 已保存</span>}
      </div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label className="form-label">{label}</label>
      {children}
      {hint && <div className="faint" style={{ marginTop: 3 }}>{hint}</div>}
    </div>
  );
}

function TestResult({ result }: { result: { ok: boolean; message: string } }) {
  return (
    <div style={{
      marginTop: 10, padding: 10, borderRadius: 8, fontSize: 12,
      background: result.ok ? "var(--success-fade)" : "var(--error-fade)",
      border: `1px solid ${result.ok ? "var(--success)" : "var(--error)"}`,
      color: result.ok ? "var(--success)" : "var(--error)",
    }}>
      {result.ok ? "✓ " : "× "}{result.message}
    </div>
  );
}
