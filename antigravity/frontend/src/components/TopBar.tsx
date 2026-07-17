import { useState, lazy, Suspense, useEffect, useRef } from "react";
import { useWorkbench } from "../store/workbench";

const SettingsView = lazy(() => import("./SettingsView"));
const PromptView = lazy(() => import("./PromptView"));
const ProjectSettingsView = lazy(() => import("./ProjectSettingsView"));
const ProjectBatchPanel = lazy(() => import("./ProjectBatchPanel"));
const CaseOrganizePanel = lazy(() => import("./CaseOrganizePanel"));

export default function TopBar({ onShowHelp }: { onShowHelp?: () => void }) {
  const toggleSidebar = useWorkbench((s) => s.toggleSidebar);
  const togglePanel = useWorkbench((s) => s.togglePanel);
  const projects = useWorkbench((s) => s.projects);
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const [showSettings, setShowSettings] = useState(false);
  const [showProjectSettings, setShowProjectSettings] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [showOrganize, setShowOrganize] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const currentProject = projects.find((p) => p.id === currentProjectId);

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

  // 点击外部关闭菜单
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

  return (
    <>
      <div className="topbar">
        <button className="collapse-btn" onClick={toggleSidebar} title="侧栏">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="1" y="2" width="4" height="10" rx="1" />
            <rect x="7" y="2" width="6" height="10" rx="1" />
          </svg>
        </button>
        <span className="brand">Clarinora</span>
        {currentProject && (
          <span style={{ fontSize: 12, color: "var(--text-3)", marginLeft: 4 }}>
            / {currentProject.name}
          </span>
        )}

        <div className="spacer" />

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
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)",
                padding: 4,
                zIndex: 50,
                animation: "content-in 120ms ease-out",
              }}
            >
              {currentProjectId && (
                <>
                  <MenuItem label="项目设置" hint={!currentProject?.has_template ? "未配模板" : ""} onClick={() => { setShowProjectSettings(true); setMenuOpen(false); }} />
                  <MenuItem label="提示词工程" hint={!currentProject?.has_prompt ? "未生成" : ""} onClick={() => { setShowPrompt(true); setMenuOpen(false); }} />
                  <MenuItem label="病例归档" onClick={() => { setShowOrganize(true); setMenuOpen(false); }} />
                  <div style={{ height: 1, background: "var(--border)", margin: "4px 0" }} />
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
            <rect x="1" y="2" width="6" height="10" rx="1" />
            <rect x="9" y="2" width="4" height="10" rx="1" />
          </svg>
        </button>
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
    <div
      onClick={onClick}
      style={{
        padding: "7px 10px",
        fontSize: 12,
        cursor: "pointer",
        borderRadius: "var(--radius)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        transition: "background 80ms ease",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-3)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <span>{label}</span>
      {hint && <span style={{ fontSize: 10, color: "var(--warning)" }}>{hint}</span>}
    </div>
  );
}

// ─── 统一 Modal 壳 ───
function Modal({ title, onClose, children, maxWidth = 700 }: { title: string; onClose: () => void; children: React.ReactNode; maxWidth?: number }) {
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
    <Modal title="批量启动" onClose={onClose} maxWidth={800}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <ProjectBatchPanel onClose={onClose} />
      </Suspense>
    </Modal>
  );
}

function OrganizeOverlay({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="病例归档" onClose={onClose} maxWidth={960}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <CaseOrganizePanel onClose={onClose} onImported={onClose} />
      </Suspense>
    </Modal>
  );
}

function ProjectSettingsOverlay({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="项目设置" onClose={onClose} maxWidth={760}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <ProjectSettingsView onClose={onClose} />
      </Suspense>
    </Modal>
  );
}

function PromptOverlay({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="提示词工程" onClose={onClose} maxWidth={1100}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <PromptView />
      </Suspense>
    </Modal>
  );
}

function SettingsOverlay({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="全局设置" onClose={onClose} maxWidth={700}>
      <Suspense fallback={<div className="faint" style={{ padding: 30, textAlign: "center" }}>加载中…</div>}>
        <SettingsView />
      </Suspense>
    </Modal>
  );
}
