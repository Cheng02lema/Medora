import { useEffect } from "react";
import { useWorkbench } from "../store/workbench";
import { STAGE_ORDER, type StageKey } from "../api/client";

/**
 * 全局快捷键系统。
 *
 * 全局:
 *   Ctrl/Cmd+N  — 导入病人（聚焦导入输入框）
 *   Ctrl/Cmd+F  — 聚焦搜索
 *   Ctrl/Cmd+S  — 保存当前编辑
 *   Ctrl/Cmd+1~8 — 切换阶段
 *   Esc         — 关闭 Lightbox/对话框/取消编辑
 *   ?           — 显示快捷键帮助
 *
 * OCR 阶段:
 *   J / ↓       — 下一页卡片
 *   K / ↑       — 上一页卡片
 *   E           — 编辑当前卡片
 *   R           — 重新 OCR 当前页
 *   Space       — 展开/折叠当前卡片
 *
 * 合并阶段:
 *   J / →       — 下一页
 *   K / ←       — 上一页
 *   E           — 进入编辑
 *
 * 抽取阶段:
 *   Tab         — 下一字段
 *   Shift+Tab   — 上一字段
 *   Ctrl/Cmd+S  — 保存
 *   1/0/-       — 存在性字段快速填值
 */
export function useKeyboardShortcuts() {
  const currentStage = useWorkbench((s) => s.currentStage);
  const setStage = useWorkbench((s) => s.setStage);
  const addToast = useWorkbench((s) => s.addToast);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;
      const ctrl = e.ctrlKey || e.metaKey;

      // ─── 全局快捷键（即使焦点在输入框也生效） ───
      if (ctrl && e.key === "s") {
        e.preventDefault();
        // 触发当前编辑器的保存（通过自定义事件）
        document.dispatchEvent(new CustomEvent("clarinora:save"));
        return;
      }

      if (ctrl && e.key >= "1" && e.key <= "8") {
        e.preventDefault();
        const idx = parseInt(e.key) - 1;
        if (idx < STAGE_ORDER.length) {
          setStage(STAGE_ORDER[idx]);
        }
        return;
      }

      if (ctrl && e.key === "n") {
        e.preventDefault();
        const importInput = document.querySelector<HTMLInputElement>("[data-role='import-input']");
        if (importInput) {
          importInput.focus();
        }
        return;
      }

      // ─── 以下快捷键在输入框中不生效 ───
      if (isInput) return;

      if (e.key === "Escape") {
        document.dispatchEvent(new CustomEvent("clarinora:escape"));
        return;
      }

      if (e.key === "?" || (e.shiftKey && e.key === "/")) {
        e.preventDefault();
        addToast("info", "快捷键: Ctrl+1~8 切换阶段 · J/K 翻页 · E 编辑 · Ctrl+S 保存 · Esc 取消");
        return;
      }

      // ─── 阶段相关快捷键 ───
      if (currentStage === "ocr" || currentStage === "merge") {
        if (e.key === "j" || e.key === "ArrowDown" || e.key === "ArrowRight") {
          e.preventDefault();
          document.dispatchEvent(new CustomEvent("clarinora:next"));
          return;
        }
        if (e.key === "k" || e.key === "ArrowUp" || e.key === "ArrowLeft") {
          e.preventDefault();
          document.dispatchEvent(new CustomEvent("clarinora:prev"));
          return;
        }
        if (e.key === "e") {
          e.preventDefault();
          document.dispatchEvent(new CustomEvent("clarinora:edit"));
          return;
        }
      }

      if (currentStage === "ocr") {
        if (e.key === "r") {
          e.preventDefault();
          document.dispatchEvent(new CustomEvent("clarinora:rerun"));
          return;
        }
        if (e.key === " ") {
          e.preventDefault();
          document.dispatchEvent(new CustomEvent("clarinora:toggle-expand"));
          return;
        }
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [currentStage, setStage, addToast]);
}
