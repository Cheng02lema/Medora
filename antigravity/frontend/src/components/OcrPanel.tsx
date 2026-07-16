import { useEffect, useMemo, useState } from "react";
import { api, type OcrParamSchema, type OcrPresetItem } from "../api/client";

export interface OcrPanelValue {
  url: string;
  model: string;
  preset: string;
  params: Record<string, any>;
  token: string;
}

interface Props {
  value: OcrPanelValue;
  onChange: (v: OcrPanelValue) => void;
  tokenConfigured?: boolean;
  /** 是否显示接口地址/模型 */
  showConnection?: boolean;
  /** Token 仅全局设置显示 */
  showToken?: boolean;
  compact?: boolean;
  onPresetsChanged?: () => void;
  addToast?: (type: string, message: string) => void;
}

/**
 * 飞桨 OCR 配置面板：
 * - 模型 + 预设（内置/用户）
 * - 始终展示全部 optionalPayload 参数（选预设会填充，改参数可另存预设）
 * - 用户预设可增删改
 */
export default function OcrPanel({
  value,
  onChange,
  tokenConfigured = false,
  showConnection = true,
  showToken = true,
  compact = false,
  onPresetsChanged,
  addToast,
}: Props) {
  const [presets, setPresets] = useState<OcrPresetItem[]>([]);
  const [models, setModels] = useState<{ id: string; label: string }[]>([]);
  const [paramSchema, setParamSchema] = useState<OcrParamSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveName, setSaveName] = useState("");
  const [busy, setBusy] = useState(false);

  const loadPresets = async () => {
    try {
      const r = await api.getOcrPresets();
      // 兼容旧接口返回数组
      if (Array.isArray(r as any)) {
        setPresets(
          (r as any).map((p: any) => ({
            key: p.key,
            label: p.label,
            description: p.description || "",
            builtin: true,
            params: p.params || {},
          }))
        );
        setModels([
          { id: "PaddleOCR-VL-1.5", label: "PaddleOCR-VL-1.5" },
          { id: "PaddleOCR-VL-1.6", label: "PaddleOCR-VL-1.6（最新）" },
          { id: "PaddleOCR-VL", label: "PaddleOCR-VL（v1）" },
        ]);
      } else {
        setPresets(r.presets || []);
        setModels(r.models || []);
      }
    } catch {
      setPresets([]);
    }
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([
      loadPresets(),
      api.getOcrParamSchema().then((r) => setParamSchema(r.params || [])).catch(() => setParamSchema([])),
    ]).finally(() => setLoading(false));
  }, []);

  const currentPreset = presets.find((p) => p.key === value.preset);

  const groups = useMemo(() => {
    const map = new Map<string, OcrParamSchema[]>();
    for (const p of paramSchema) {
      const g = p.group || "其他";
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(p);
    }
    return Array.from(map.entries());
  }, [paramSchema]);

  const patch = (partial: Partial<OcrPanelValue>) => onChange({ ...value, ...partial });

  const applyPreset = async (key: string) => {
    patch({ preset: key });
    try {
      const r = await api.getPresetDetails(key);
      patch({ preset: key, params: { ...(r.payload || {}) } });
    } catch {
      const p = presets.find((x) => x.key === key);
      if (p?.params) patch({ preset: key, params: { ...p.params } });
    }
  };

  const setParam = (key: string, v: any) => {
    patch({ params: { ...value.params, [key]: v } });
  };

  const handleSaveAsPreset = async () => {
    const label = saveName.trim();
    if (!label) {
      addToast?.("warning", "请输入预设名称");
      return;
    }
    setBusy(true);
    try {
      const r = await api.createOcrPreset({
        label,
        description: "用户自定义",
        params: value.params,
      });
      await loadPresets();
      onPresetsChanged?.();
      patch({ preset: r.preset.key });
      setSaveName("");
      addToast?.("success", `已保存预设「${r.preset.label}」`);
    } catch (e: any) {
      addToast?.("error", e.message || "保存预设失败");
    } finally {
      setBusy(false);
    }
  };

  const handleUpdatePreset = async () => {
    if (!currentPreset || currentPreset.builtin) {
      addToast?.("warning", "内置预设请用「另存为」");
      return;
    }
    setBusy(true);
    try {
      await api.updateOcrPreset(currentPreset.key, {
        label: currentPreset.label,
        description: currentPreset.description,
        params: value.params,
      });
      await loadPresets();
      onPresetsChanged?.();
      addToast?.("success", "预设已更新");
    } catch (e: any) {
      addToast?.("error", e.message || "更新失败");
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePreset = async () => {
    if (!currentPreset || currentPreset.builtin) return;
    if (!confirm(`删除用户预设「${currentPreset.label}」？`)) return;
    setBusy(true);
    try {
      await api.deleteOcrPreset(currentPreset.key);
      await loadPresets();
      onPresetsChanged?.();
      await applyPreset("paper_photo");
      addToast?.("success", "预设已删除");
    } catch (e: any) {
      addToast?.("error", e.message || "删除失败");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 12 }}>
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line short" />
      </div>
    );
  }

  return (
    <div>
      {showConnection && (
        <>
          <Field label="接口地址" hint="PaddleOCR 在线 Job API">
            <input
              value={value.url}
              onChange={(e) => patch({ url: e.target.value })}
              placeholder="https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
            />
          </Field>
          <Field label="模型" hint="对应 request 的 model 字段">
            <select value={value.model} onChange={(e) => patch({ model: e.target.value })}>
              {models.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
              {/* 允许自定义模型名 */}
              {!models.some((m) => m.id === value.model) && value.model && (
                <option value={value.model}>{value.model}（当前）</option>
              )}
            </select>
            <input
              style={{ marginTop: 6 }}
              value={value.model}
              onChange={(e) => patch({ model: e.target.value })}
              placeholder="或直接输入模型名"
            />
          </Field>
          {showToken && (
            <Field
              label={`Token ${tokenConfigured ? "（已配置 ✓）" : "（未配置）"}`}
              hint="留空则保留已保存的 Token · 仅全局存储"
            >
              <input
                type="password"
                value={value.token}
                onChange={(e) => patch({ token: e.target.value })}
                placeholder="粘贴 OCR API Token…"
              />
            </Field>
          )}
        </>
      )}

      <Field label="预设" hint="选择后填充下方参数；修改参数后可另存为用户预设">
        <select
          value={value.preset}
          onChange={(e) => applyPreset(e.target.value)}
        >
          {presets.map((p) => (
            <option key={p.key} value={p.key}>
              {p.builtin ? "" : "★ "}{p.label}
            </option>
          ))}
        </select>
        {currentPreset && (
          <div className="faint" style={{ marginTop: 4 }}>
            {currentPreset.builtin ? "内置" : "用户"} · {currentPreset.description || currentPreset.key}
          </div>
        )}
      </Field>

      {/* 参数面板：始终显示 */}
      <div
        style={{
          marginTop: 8,
          marginBottom: 14,
          padding: compact ? 10 : 14,
          borderRadius: 8,
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>optionalPayload 参数</span>
          <span className="faint" style={{ fontSize: 11 }}>写入飞桨 request</span>
        </div>

        {groups.map(([group, params]) => (
          <div key={group} style={{ marginBottom: 12 }}>
            <div className="faint" style={{ fontSize: 11, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              {group}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: compact ? "1fr" : "1fr 1fr", gap: 8 }}>
              {params.map((param) => (
                <OcrParamControl
                  key={param.key}
                  param={param}
                  value={value.params[param.key] ?? param.default}
                  onChange={(v) => setParam(param.key, v)}
                />
              ))}
            </div>
          </div>
        ))}

        {/* 预设管理 */}
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 4 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>预设管理</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="新预设名称…"
              style={{ flex: 1, minWidth: 120, fontSize: 12 }}
            />
            <button className="btn btn-sm btn-primary" disabled={busy} onClick={handleSaveAsPreset}>
              另存为预设
            </button>
            {currentPreset && !currentPreset.builtin && (
              <>
                <button className="btn btn-sm" disabled={busy} onClick={handleUpdatePreset}>
                  更新当前
                </button>
                <button className="btn btn-sm" disabled={busy} onClick={handleDeletePreset}>
                  删除
                </button>
              </>
            )}
          </div>
          <div className="faint" style={{ marginTop: 6, fontSize: 11 }}>
            内置预设不可删改；用户预设标 ★，可更新/删除。
          </div>
        </div>
      </div>
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

function OcrParamControl({
  param,
  value,
  onChange,
}: {
  param: OcrParamSchema;
  value: any;
  onChange: (v: any) => void;
}) {
  if (param.type === "bool") {
    return (
      <label
        style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}
        title={param.description}
      >
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          style={{ width: "auto" }}
        />
        <span>{param.label}</span>
      </label>
    );
  }
  if (param.type === "enum") {
    return (
      <div title={param.description}>
        <label style={{ fontSize: 11, color: "var(--text-2)" }}>{param.label}</label>
        <select
          value={value ?? param.default}
          onChange={(e) => onChange(e.target.value)}
          style={{ fontSize: 12, padding: "4px 6px", marginTop: 2 }}
        >
          {(param.options || []).map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      </div>
    );
  }
  if (param.type === "list") {
    return (
      <div title={param.description} style={{ gridColumn: "1 / -1" }}>
        <label style={{ fontSize: 11, color: "var(--text-2)" }}>{param.label}</label>
        <input
          value={Array.isArray(value) ? value.join(", ") : ""}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            )
          }
          placeholder="逗号分隔，空=不忽略"
          style={{ fontSize: 11, padding: "4px 6px", marginTop: 2 }}
        />
      </div>
    );
  }
  return (
    <div title={param.description}>
      <label style={{ fontSize: 11, color: "var(--text-2)" }}>{param.label}</label>
      <input
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        style={{ fontSize: 11, padding: "4px 6px", marginTop: 2 }}
      />
    </div>
  );
}
