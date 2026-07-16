const SHORTCUTS = [
  { keys: "Ctrl/Cmd + 1~8", desc: "切换阶段" },
  { keys: "Ctrl/Cmd + S", desc: "触发保存事件（编辑区监听后生效）" },
  { keys: "Ctrl/Cmd + N", desc: "聚焦导入路径输入框" },
  { keys: "J / ↓ / →", desc: "OCR 下一页卡片" },
  { keys: "K / ↑ / ←", desc: "OCR 上一页卡片" },
  { keys: "E", desc: "OCR 编辑当前卡片" },
  { keys: "R", desc: "OCR 重识别当前页" },
  { keys: "Space", desc: "OCR 展开/折叠" },
  { keys: "Esc", desc: "关闭弹层" },
  { keys: "?", desc: "显示此帮助" },
  { keys: "双击 / 右键", desc: "侧栏：重命名 / 删除项目或病人" },
];

export default function KeyboardHelp({ onClose }: { onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        background: "rgba(0,0,0,0.5)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        animation: "fade-in 200ms ease-out",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="panel"
        style={{
          padding: 28,
          borderRadius: 20,
          maxWidth: 480,
          width: "90%",
          animation: "zoom-in 300ms cubic-bezier(0.34,1.56,0.64,1)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <span className="h1">快捷键</span>
          <button
            className="btn btn-sm"
            onClick={onClose}
            style={{ borderRadius: "50%", width: 32, height: 32, padding: 0, fontSize: 16 }}
          >
            ×
          </button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {SHORTCUTS.map((s, i) => (
            <div
              key={i}
              style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 0", borderBottom: "1px solid var(--border)" }}
            >
              <kbd
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  padding: "3px 10px",
                  fontSize: 12,
                  fontFamily: "monospace",
                  color: "var(--primary)",
                  minWidth: 130,
                  textAlign: "center",
                }}
              >
                {s.keys}
              </kbd>
              <span style={{ fontSize: 13, color: "var(--text-2)" }}>{s.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
