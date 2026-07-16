import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useWorkbench } from "../store/workbench";
import PathInput from "./PathInput";

type ChatMsg = { role: "user" | "assistant"; content: string };

/**
 * 病例归档：Agent 对话 + 工具 loop（PDF 每 N 页 / 目录归档）
 * 主路径：选源目录 → 场景或指令 → 确认 → 导入
 */
export default function CaseOrganizePanel({
  onClose,
  onImported,
}: {
  onClose?: () => void;
  onImported?: () => void;
}) {
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const projects = useWorkbench((s) => s.projects);
  const loadPatients = useWorkbench((s) => s.loadPatients);
  const addToast = useWorkbench((s) => s.addToast);
  const currentProject = projects.find((p) => p.id === currentProjectId);

  const [workPath, setWorkPath] = useState("");
  const [outPath, setOutPath] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [toolLog, setToolLog] = useState<any[]>([]);
  const [plan, setPlan] = useState<any>(null);
  const [treeText, setTreeText] = useState("");
  const [validateInfo, setValidateInfo] = useState<any>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [llmOk, setLlmOk] = useState(false);
  const [llmModel, setLlmModel] = useState("");
  const [showLlm, setShowLlm] = useState(false);
  const [agentProvider, setAgentProvider] = useState("DeepSeek");
  const [agentModel, setAgentModel] = useState("deepseek-chat");
  const [agentBaseUrl, setAgentBaseUrl] = useState("https://api.deepseek.com");
  const [agentKey, setAgentKey] = useState("");
  const [llmProviders, setLlmProviders] = useState<{ name: string; default_url: string }[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, toolLog]);

  useEffect(() => {
    api.getLlmProviders().then(setLlmProviders).catch(() => {});
    api.getSettings().then((s) => {
      const ag = s.agent_llm;
      if (ag) {
        setAgentProvider(ag.provider || "DeepSeek");
        setAgentModel(ag.model && ag.model !== "gpt-4o-mini" ? ag.model : "deepseek-chat");
        setAgentBaseUrl(ag.base_url || "https://api.deepseek.com");
        setLlmOk(!!ag.api_key_configured);
        setLlmModel(ag.model || "");
      }
    }).catch(() => {});
  }, []);

  const ensureOut = (work: string) => {
    if (!work || outPath) return;
    setOutPath(`${work.replace(/\/$/, "")}_organized`);
  };

  const startSession = async (autoMsg?: string) => {
    if (!workPath.trim()) {
      addToast("warning", "请先选择源目录");
      return null;
    }
    setBusy(true);
    try {
      const out = outPath.trim() || `${workPath.trim().replace(/\/$/, "")}_organized`;
      if (!outPath.trim()) setOutPath(out);
      const r = await api.createOrganizeSession({
        work_path: workPath.trim(),
        out_path: out,
        project_id: currentProjectId || undefined,
      });
      setSessionId(r.session.id);
      setLlmOk(!!r.llm_configured);
      setLlmModel(r.llm?.model || r.llm?.provider || "");
      setMessages([
        {
          role: "assistant",
          content:
            `已就绪。\n` +
            `源目录：${r.session.work_path}\n` +
            `输出：${r.session.out_path}\n` +
            `模式：${r.llm_configured ? `LLM ${r.llm?.model || ""}` : "规则模式（PDF 分页 / 目录归档可用）"}\n\n` +
            `可直接点下方场景，或输入例如：「把 PDF 按每 2 页拆成病人」`,
        },
      ]);
      setToolLog([]);
      setPlan(null);
      setTreeText("");
      setValidateInfo(null);
      addToast("success", "整理会话已创建");
      if (autoMsg) {
        await chat(autoMsg, r.session.id);
      }
      return r.session.id;
    } catch (e: any) {
      addToast("error", e.message || "创建失败");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const chat = async (text?: string, sid?: string) => {
    const id = sid || sessionId;
    const msg = (text ?? input).trim();
    if (!id || !msg) return;
    if (!sid) setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setBusy(true);
    try {
      const r = await api.chatOrganize(id, {
        message: msg,
        confirm_apply: /确认执行|执行计划/.test(msg),
      });
      setMessages((m) => [...m, { role: "assistant", content: r.reply || "(无回复)" }]);
      if (r.tools?.length) setToolLog((t) => [...t, ...r.tools]);
      if (r.session?.plan_summary) setPlan(r.session.plan_summary);
      try {
        const tree = await api.getOrganizeTree(id, "out");
        setTreeText(tree.tree?.tree || "");
        setValidateInfo(tree.validate);
      } catch {
        /* ignore */
      }
    } catch (e: any) {
      addToast("error", e.message || "对话失败");
      setMessages((m) => [...m, { role: "assistant", content: `错误：${e.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  const runScene = async (prompt: string) => {
    let id = sessionId;
    if (!id) {
      id = await startSession();
      if (!id) return;
    }
    await chat(prompt, id);
  };

  const doImport = async () => {
    if (!sessionId) return;
    if (!currentProjectId) {
      addToast("warning", "请先选择项目");
      return;
    }
    setBusy(true);
    try {
      const r = await api.importOrganizeSession(sessionId, currentProjectId);
      addToast("success", r.message || `已导入 ${r.imported} 人`);
      await loadPatients();
      onImported?.();
    } catch (e: any) {
      addToast("error", e.message || "导入失败");
    } finally {
      setBusy(false);
    }
  };

  const saveAgentLlm = async () => {
    try {
      await api.updateAgentLLM({
        provider: agentProvider,
        model: agentModel,
        base_url: agentBaseUrl,
        ...(agentKey ? { api_key: agentKey } : {}),
      });
      setAgentKey("");
      setLlmOk(true);
      setLlmModel(agentModel || agentProvider);
      setShowLlm(false);
      addToast("success", "Agent LLM 已保存");
    } catch (e: any) {
      addToast("error", e.message || "保存失败");
    }
  };

  const scenes = [
    { label: "扫描目录", prompt: "扫描源目录，列出图片和 PDF" },
    { label: "PDF 每 2 页一人", prompt: "把目录里的 PDF 按每 2 页拆成一个病人文件夹，复制到输出目录并校验" },
    { label: "PDF 每 1 页一人", prompt: "把目录里的 PDF 按每 1 页拆成一个病人文件夹并校验" },
    { label: "已有一人一夹→整理", prompt: "生成整理计划" },
    { label: "确认执行复制", prompt: "确认执行" },
    { label: "校验输出", prompt: "校验输出目录" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "min(82vh, 760px)", minHeight: 440 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <div style={{ fontWeight: 700 }}>病例归档</div>
        {currentProject && <span className="faint" style={{ fontSize: 12 }}>→ {currentProject.name}</span>}
        <div style={{ flex: 1 }} />
        <span className="faint" style={{ fontSize: 12 }}>
          {llmOk ? `LLM：${llmModel || "已配置"}` : "规则+工具可用 · 可配 DeepSeek"}
        </span>
        <button className="btn btn-sm" onClick={() => setShowLlm((v) => !v)}>{showLlm ? "收起" : "配置 LLM"}</button>
      </div>

      {showLlm && (
        <div style={{ marginBottom: 10, padding: 10, border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
          <label>
            <div className="faint">Provider</div>
            <select value={agentProvider} onChange={(e) => {
              setAgentProvider(e.target.value);
              const p = llmProviders.find((x) => x.name === e.target.value);
              if (p?.default_url) setAgentBaseUrl(p.default_url);
            }}>
              {(llmProviders.length ? llmProviders : [{ name: "DeepSeek", default_url: "https://api.deepseek.com" }]).map((p) => (
                <option key={p.name} value={p.name}>{p.name}</option>
              ))}
            </select>
          </label>
          <label>
            <div className="faint">模型</div>
            <input value={agentModel} onChange={(e) => setAgentModel(e.target.value)} placeholder="deepseek-chat" />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            <div className="faint">Base URL</div>
            <input value={agentBaseUrl} onChange={(e) => setAgentBaseUrl(e.target.value)} />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            <div className="faint">API Key</div>
            <input type="password" value={agentKey} onChange={(e) => setAgentKey(e.target.value)} placeholder="留空保留已有" />
          </label>
          <div style={{ gridColumn: "1 / -1", display: "flex", gap: 8 }}>
            <button className="btn btn-sm btn-primary" onClick={() => void saveAgentLlm()}>保存</button>
            <button className="btn btn-sm" onClick={async () => {
              try {
                await api.copyAgentLLMFromExtract();
                addToast("success", "已从抽取 LLM 复制");
                const s = await api.getSettings();
                if (s.agent_llm) {
                  setLlmOk(!!s.agent_llm.api_key_configured);
                  setLlmModel(s.agent_llm.model || "");
                }
              } catch (e: any) {
                addToast("error", e.message);
              }
            }}>从抽取 LLM 复制</button>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <div>
          <div className="faint" style={{ fontSize: 11, marginBottom: 4 }}>源目录</div>
          <PathInput value={workPath} onChange={(v) => { setWorkPath(v); ensureOut(v); }} mode="folder" placeholder="含 PDF / 图片的目录" />
        </div>
        <div>
          <div className="faint" style={{ fontSize: 11, marginBottom: 4 }}>输出目录（一人一夹）</div>
          <PathInput value={outPath} onChange={setOutPath} mode="folder" placeholder="默认 源目录_organized" />
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <button className="btn btn-sm btn-primary" disabled={busy || !workPath} onClick={() => void startSession("扫描源目录，列出图片和 PDF")}>
          {sessionId ? "重新开始" : "开始"}
        </button>
        {scenes.map((s) => (
          <button key={s.label} className="btn btn-sm" disabled={busy || !workPath} onClick={() => void runScene(s.prompt)}>
            {s.label}
          </button>
        ))}
        <button className="btn btn-sm btn-primary" disabled={busy || !sessionId || !currentProjectId} onClick={() => void doImport()}>
          导入到当前项目
        </button>
      </div>

      <div style={{ display: "flex", gap: 12, flex: 1, minHeight: 0 }}>
        <div style={{ flex: "1 1 55%", display: "flex", flexDirection: "column", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", minWidth: 0 }}>
          <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
            {messages.length === 0 && (
              <div className="faint" style={{ fontSize: 12, lineHeight: 1.65 }}>
                选源目录后点「开始」，或直接点 <b>PDF 每 2 页一人</b>。
                <br />
                流程：扫描 → PDF 渲页 → 按 N 页分组 → 校验 → 导入。
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  marginBottom: 10,
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: m.role === "user" ? "var(--primary-fade)" : "var(--surface-2)",
                  border: "1px solid var(--border)",
                  fontSize: 13,
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.55,
                }}
              >
                <div className="faint" style={{ fontSize: 10, marginBottom: 4 }}>{m.role === "user" ? "你" : "助理"}</div>
                {m.content}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
          <div style={{ borderTop: "1px solid var(--border)", padding: 8, display: "flex", gap: 8 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={!sessionId || busy}
              placeholder={sessionId ? "例如：把 PDF 按每 2 页拆成病人…" : "请先点开始"}
              style={{ flex: 1 }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void chat();
                }
              }}
            />
            <button className="btn btn-sm btn-primary" disabled={!sessionId || busy || !input.trim()} onClick={() => void chat()}>
              发送
            </button>
          </div>
        </div>

        <div style={{ flex: "1 1 45%", display: "flex", flexDirection: "column", gap: 8, minWidth: 0, minHeight: 0 }}>
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10, background: "var(--surface-2)" }}>
            <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6 }}>结果摘要</div>
            {plan ? (
              <div style={{ fontSize: 12, lineHeight: 1.5 }}>
                病人 <b>{plan.patient_count ?? "—"}</b> · 文件/页 <b>{plan.file_count ?? "—"}</b>
                <div style={{ marginTop: 6 }}>
                  {(plan.patients || []).slice(0, 20).map((n: string) => (
                    <span key={n} style={{ display: "inline-block", margin: "0 4px 4px 0", padding: "1px 6px", borderRadius: 4, border: "1px solid var(--border)", fontSize: 11 }}>{n}</span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="faint" style={{ fontSize: 12 }}>执行场景后显示</div>
            )}
            {validateInfo && (
              <div style={{ marginTop: 8, fontSize: 12, color: validateInfo.ok ? "var(--success)" : "var(--warning)" }}>
                {validateInfo.message}
              </div>
            )}
          </div>

          <div style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 8, padding: 10, overflow: "auto", fontFamily: "ui-monospace, Menlo, monospace", fontSize: 11, whiteSpace: "pre", background: "var(--surface)", minHeight: 0 }}>
            <div className="faint" style={{ marginBottom: 6, fontFamily: "inherit" }}>输出目录 / 工具步骤</div>
            {treeText || "—"}
            {toolLog.length > 0 && (
              <div style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
                {toolLog.slice(-15).map((t, i) => (
                  <div key={i} style={{ marginBottom: 4 }}>
                    → {t.name}{t.result?.error ? ` ERR ${t.result.error}` : " ok"}
                    {t.result?.patient_count != null ? ` patients=${t.result.patient_count}` : ""}
                    {t.result?.rendered != null ? ` pages=${t.result.rendered}` : ""}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {onClose && (
        <div style={{ marginTop: 10, textAlign: "right" }}>
          <button className="btn btn-sm" onClick={onClose}>关闭</button>
        </div>
      )}
    </div>
  );
}
