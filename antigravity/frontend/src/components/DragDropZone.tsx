import { useState, useEffect, useRef, DragEvent } from "react";
import { useWorkbench } from "../store/workbench";

/**
 * 全局拖拽导入：拖拽文件夹/文件到窗口任意位置时显示导入提示。
 *
 * - 拖拽文件夹 → 导入为图片病人（image 项目）
 * - 拖拽 .xlsx → 导入为 Excel 拆分（excel 项目）
 * - 拖拽 .md/.txt/.docx → 导入为文本病人（text 项目）
 *
 * 仅在 Electron 环境下能获取完整文件路径。
 * Web 环境下使用 File API 读取文件名（路径不完整）。
 */
export default function DragDropZone() {
  const currentProjectId = useWorkbench((s) => s.currentProjectId);
  const currentProject = useWorkbench((s) => s.projects.find((p) => p.id === s.currentProjectId));
  const importPatients = useWorkbench((s) => s.importPatients);
  const importText = useWorkbench((s) => s.importText);
  const importExcel = useWorkbench((s) => s.importExcel);
  const addToast = useWorkbench((s) => s.addToast);

  const [dragging, setDragging] = useState(false);
  const dragCounter = useRef(0);

  useEffect(() => {
    const handleDragEnter = (e: globalThis.DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current++;
        setDragging(true);
      }
    };
    const handleDragLeave = (e: globalThis.DragEvent) => {
      dragCounter.current--;
      if (dragCounter.current <= 0) {
        setDragging(false);
        dragCounter.current = 0;
      }
    };
    const handleDragOver = (e: globalThis.DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        e.preventDefault();
      }
    };
    const handleDrop = (e: globalThis.DragEvent) => {
      e.preventDefault();
      dragCounter.current = 0;
      setDragging(false);
      handleFiles(e);
    };

    window.addEventListener("dragenter", handleDragEnter);
    window.addEventListener("dragleave", handleDragLeave);
    window.addEventListener("dragover", handleDragOver);
    window.addEventListener("drop", handleDrop);

    return () => {
      window.removeEventListener("dragenter", handleDragEnter);
      window.removeEventListener("dragleave", handleDragLeave);
      window.removeEventListener("dragover", handleDragOver);
      window.removeEventListener("drop", handleDrop);
    };
  }, [currentProjectId, currentProject]);

  const handleFiles = async (e: globalThis.DragEvent) => {
    if (!currentProjectId || !currentProject) {
      addToast("warning", "请先选择一个项目再导入");
      return;
    }

    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;

    // Electron 环境:通过 file.path 获取完整路径
    const electronFile = files[0] as any;
    const filePath = electronFile?.path;

    if (filePath) {
      // Electron:有完整路径
      const ext = filePath.toLowerCase().split(".").pop() || "";
      if (ext === "xlsx" || ext === "xls") {
        addToast("info", "正在从 Excel 拆分病人…");
        try {
          await importExcel(filePath);
        } catch (e: any) {
          addToast("error", e.message || "Excel 导入失败");
        }
      } else if (ext === "md" || ext === "txt" || ext === "docx") {
        addToast("info", "正在导入文本文件…");
        try {
          // 单文件:取所在目录
          const dir = filePath.substring(0, filePath.lastIndexOf("/"));
          await importText(dir);
        } catch (e: any) {
          addToast("error", e.message || "文本导入失败");
        }
      } else {
        // 文件夹或图片:取目录路径
        const dir = filePath.substring(0, filePath.lastIndexOf("/"));
        addToast("info", "正在导入图片文件夹…");
        try {
          await importPatients(dir);
        } catch (e: any) {
          addToast("error", e.message || "导入失败");
        }
      }
    } else {
      // Web 环境:无完整路径,提示用户手动输入
      const fileName = files[0].name;
      addToast("warning", `Web 环境无法获取文件路径,请手动在侧边栏输入路径导入。文件名: ${fileName}`);
    }
  };

  if (!dragging) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(99,102,241,0.15)",
        backdropFilter: "blur(8px)",
        pointerEvents: "none",
        animation: "fade-in 150ms ease-out",
      }}
    >
      <div
        className="panel"
        style={{
          padding: 40,
          textAlign: "center",
          border: "2px dashed var(--primary)",
          borderRadius: 20,
        }}
      >
        <div style={{ fontSize: 48, marginBottom: 12 }}></div>
        <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>
          释放以导入
        </div>
        <div style={{ fontSize: 13, color: "var(--text-2)" }}>
          {currentProject
            ? `导入到项目「${currentProject.name}」`
            : "请先选择一个项目"}
        </div>
      </div>
    </div>
  );
}
