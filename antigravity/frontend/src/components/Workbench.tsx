import { useEffect, useState } from "react";
import { useWorkbench } from "../store/workbench";
import { useKeyboardShortcuts } from "../hooks/useKeyboard";
import { useWebSocket } from "../hooks/useWebSocket";
import ErrorBoundary from "./ErrorBoundary";
import TopBar from "./TopBar";
import ProjectSidebar from "./ProjectSidebar";
import StageNav from "./StageNav";
import StageContent from "./StageContent";
import StagePanel from "./StagePanel";
import StatusBar from "./StatusBar";
import ToastContainer from "./ToastContainer";
import DragDropZone from "./DragDropZone";
import KeyboardHelp from "./KeyboardHelp";

export default function Workbench() {
  const init = useWorkbench((s) => s.init);
  const onWSMessage = useWorkbench((s) => s.onWSMessage);
  const sidebarCollapsed = useWorkbench((s) => s.sidebarCollapsed);
  const panelCollapsed = useWorkbench((s) => s.panelCollapsed);
  const addToast = useWorkbench((s) => s.addToast);

  const [showHelp, setShowHelp] = useState(false);

  useKeyboardShortcuts();
  const { isReconnecting, isDisconnected } = useWebSocket({ onMessage: onWSMessage });

  useEffect(() => {
    init();
  }, [init]);

  // WebSocket 重连后刷新
  useEffect(() => {
    const handler = () => {
      useWorkbench.getState().refreshAll();
      addToast("info", "连接已恢复，数据已刷新");
    };
    document.addEventListener("medora:reconnected", handler);
    return () => document.removeEventListener("medora:reconnected", handler);
  }, [addToast]);

  // Esc 关闭帮助
  useEffect(() => {
    const handler = () => {
      if (showHelp) setShowHelp(false);
    };
    document.addEventListener("medora:escape", handler);
    return () => document.removeEventListener("medora:escape", handler);
  }, [showHelp]);

  // ? 键显示帮助
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "?" || (e.shiftKey && e.key === "/")) {
        const target = e.target as HTMLElement;
        if (target.tagName !== "INPUT" && target.tagName !== "TEXTAREA" && !target.isContentEditable) {
          setShowHelp(true);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // 离开页面提示
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      const hasDraft = Object.keys(localStorage).some((k) => k.startsWith("medora:draft:"));
      if (hasDraft) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);

  return (
    <ErrorBoundary>
      <div className="app-root">
        <TopBar onShowHelp={() => setShowHelp(true)} />
        <div className="main-area">
          <div className={`panel sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
            <ProjectSidebar />
          </div>
          <div className="panel center-area">
            <StageNav />
            <StageContent />
          </div>
          <div className={`panel stage-panel ${panelCollapsed ? "collapsed" : ""}`}>
            <StagePanel />
          </div>
        </div>
        <StatusBar isReconnecting={isReconnecting} isDisconnected={isDisconnected} />
        <ToastContainer />
        <DragDropZone />
        {showHelp && <KeyboardHelp onClose={() => setShowHelp(false)} />}
      </div>
    </ErrorBoundary>
  );
}
