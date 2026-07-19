import { useState, lazy, Suspense, useEffect, useRef } from "react";
import { useWorkbench } from "../store/workbench";
import { STAGE_LABELS } from "../api/client";

const SettingsView = lazy(() => import("./SettingsView"));
const PromptView = lazy(() => import("./PromptView"));
const ProjectSettingsView = lazy(() => import("./ProjectSettingsView"));
const ProjectBatchPanel = lazy(() => import("./ProjectBatchPanel"));
const CaseOrganizePanel = lazy(() => import("./CaseOrganizePanel"));

export default function TopBar({
  onShowHelp,
  isReconnecting = false,
  isDisconnected = false,
}: {
  onShowHelp?: () => void;
  isReconnecting?: boolean;
  isDisconnected?: boolean;
}) {
  const toggleSidebar = useWorkbench((s) => s.toggleSidebar);
  const togglePanel = useWorkbench((s) => s.togglePanel);
  const projects = useWorkbench((s) => s.projects);
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const selectedIds = useWorkbench((s) => s.selectedIds);
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentStage = useWorkbench((s) => s.currentStage);
  const patients = useWorkbench((s) => s.patients);
  const settings = useWorkbench((s) => s.settings);
  const [showSettings, setShowSettings] = useState(false);
  const [showProjectSettings, setShowProjectSettings] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [showOrganize, setShowOrganize] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const currentProject = projects.find((p) => p.id === currentProjectId);
  const selectedPatient =
    selectedIds.length === 1
      ? patients.find((p) => p.id === selectedIds[0]) || patientDetail
      : null;

  const parallel =
    settings?.execution?.max_parallel_patients ?? 1;

  let connLabel = "已连接";
  let connClass = "";
  if (isReconnecting) {
    connLabel = "重连中";
    connClass = "warn";
  } else if (isDisconnected) {
    connLabel = "已断开";
    connClass = "err";
  }

  const patientSeg =
    selectedIds.length > 1
      ? `已选 ${selectedIds.length} 人`
      : selectedPatient?.name || (currentPatientId ? "…" : "未选病人");

  const stageSeg = STAGE_LABELS[currentStage] || currentStage;

  useEffect(() => {
    if (!showSettings && !showPrompt && !showProjectSettings && !showBatch && !showOrganize && !menuOpen) return;
    const handler = () => {
      setShowSettings(false);
      setShowProjectSettings(false);
      setShowPrompt(false);
      setShowBatch(false);
      setShowOrganize(false);
      setMenuOpen(false);
    };
    document.addEventListener("clarinora:escape", handler);
    return () => document.removeEventListener("clarinora:escape", handler);
  }, [showSettings, showPrompt, showProjectSettings, showBatch, showOrganize, menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const needTemplate =
    !!currentProjectId && currentProject && !currentProject.has_template;

  return (
    <>
      <div className="topbar">
        <div className="box brand-box">
          <button className="collapse-btn" onClick={toggleSidebar} title="侧栏" style={{ marginRight: 4 }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="1" y="2" width="4" height="10" rx="0" />
              <rect x="7" y="2" width="6" height="10" rx="0" />
            </svg>
          </button>
          <span className="brand-mark" />
          <span className="brand">Clarinora</span>
        </div>

        <div className="box crumbs">
          <span className={`seg ${!currentProject ? "current" : ""}`}>
            {currentProject?.name || "未选项目"}
          </span>
          <span className="sep">/</span>
          <span className={`seg ${selectedIds.length > 0 ? "current" : ""}`}>{patientSeg}</span>
          <span className="sep">/</span>
          <span className="seg current" style={{ color: "var(--violet-2)" }}>{stageSeg}</span>
        </div>

        <div className="box sys-actions">
          <div className="sys">
            <span>连接 <em className={connClass}>{connLabel}</em></span>
            <span>并行 <em>{parallel}</em></span>
          </div>
          <div className="actions-slot">
            {currentProjectId && (
              <button className="btn btn-sm btn-primary" onClick={() => setShowBatch(true)}>
                批量启动
              </button>
            )}
            <div ref={menuRef} style={{ position: "relative" }}>
              <button className="btn btn-sm" onClick={() => setMenuOpen(!menuOpen)}>
                更多
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.2">
                  <path d="M2 3.5L5 6.5L8 3.5" />
                </svg>
              </button>
              {menuOpen && (
                <div
                  style={{
                    position: "absolute",
                    top: "100%",
                    right: 0,
                    marginTop: 4,
                    minWidth: 180,
                    background: "var(--panel2)",
                    border: "1px solid var(--line)",
                    padding: 4,
                    zIndex: 50,
                  }}
                >
                  {currentProjectId && (
                    <>
                      <MenuItem
                        label="项目设置"
                        hint={!currentProject?.has_template ? "未配模板" : ""}
                        onClick={() => { setShowProjectSettings(true); setMenuOpen(false); }}
                      />
                      <MenuItem
                        label="提示词工程"
                        hint={!currentProject?.has_prompt ? "未生成" : ""}
                        onClick={() => { setShowPrompt(true); setMenuOpen(false); }}
                      />
                      <MenuItem label="病例归档" onClick={() => { setShowOrganize(true); setMenuOpen(false); }} />
                      <div style={{ height: 1, background: "var(--line)", margin: "4px 0" }} />
                    </>
                  )}
                  {!currentProjectId && (
                    <MenuItem label="病例归档" onClick={() => { setShowOrganize(true); setMenuOpen(false); }} />
                  )}
                  <MenuItem label="全局设置" onClick={() => { setShowSettings(true); setMenuOpen(false); }} />
                  <MenuItem label="快捷键" onClick={() => { onShowHelp?.(); setMenuOpen(false); }} />
                </div>
              )}
            </div>
            <button className="collapse-btn" onClick={togglePanel} title="操作面板">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="1" y="2" width="6" height="10" rx="0" />
                <rect x="9" y="2" width="4" height="10" rx="0" />
              </svg>
            </button>
          </div>
        </div>

        {needTemplate && (
          <div className="template-hint">
            项目未配模板
            <button type="button" onClick={() => setShowProjectSettings(true)}>
              去项目设置
            </button>
          </div>
        )}
      </div>

      {showBatch && currentProjectId && <BatchOverlay onClose={() => setShowBatch(false)} />}
      {showProjectSettings && currentProjectId && <ProjectSettingsOverlay onClose={() => setShowProjectSettings(false)} />}
      {showPrompt && currentProjectId && <PromptOverlay onClose={() => setShowPrompt(false)} />}
      {showSettings && <SettingsOverlay onClose={() => setShowSettings(false)} />}
      {showOrganize && <OrganizeOverlay onClose={() => setShowOrganize(false)} />}
    </>
  );
}

function MenuItem({ label, hint, onClick }: { label: string; hint?: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        width: "100%",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        padding: "8px 10px",
        border: "none",
        background: "transparent",
        color: "var(--fg)",
        fontSize: 12,
        cursor: "pointer",
        textAlign: "left",
        fontFamily: "inherit",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,.04)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
    >
      <span>{label}</span>
      {hint && <span className="faint" style={{ color: "var(--amber)" }}>{hint}</span>}
    </button>
  );
}

function OverlayShell({
  title,
  onClose,
  maxWidth = 720,
  children,
}: {
  title: string;
  onClose: () => void;
  maxWidth?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" style={{ maxWidth }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function BatchOverlay({ onClose }: { onClose: () => void }) {
  return (
    <OverlayShell title="批量启动" onClose={onClose} maxWidth={760}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <ProjectBatchPanel onClose={onClose} />
      </Suspense>
    </OverlayShell>
  );
}

function ProjectSettingsOverlay({ onClose }: { onClose: () => void }) {
  return (
    <OverlayShell title="项目设置" onClose={onClose} maxWidth={760}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <ProjectSettingsView onClose={onClose} />
      </Suspense>
    </OverlayShell>
  );
}

function PromptOverlay({ onClose }: { onClose: () => void }) {
  return (
    <OverlayShell title="提示词工程" onClose={onClose} maxWidth={900}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <PromptView />
      </Suspense>
    </OverlayShell>
  );
}

function SettingsOverlay({ onClose }: { onClose: () => void }) {
  return (
    <OverlayShell title="全局设置" onClose={onClose} maxWidth={720}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <SettingsView />
      </Suspense>
    </OverlayShell>
  );
}

function OrganizeOverlay({ onClose }: { onClose: () => void }) {
  return (
    <OverlayShell title="病例归档" onClose={onClose} maxWidth={900}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <CaseOrganizePanel onClose={onClose} />
      </Suspense>
    </OverlayShell>
  );
}
