import { useState } from "react";
import { selectFolder, selectFile, selectSaveFile } from "../hooks/useFileDialog";

interface PathInputProps {
  value: string;
  onChange: (value: string) => void;
  mode?: "folder" | "file" | "save";
  filters?: { name: string; extensions: string[] }[];
  placeholder?: string;
  style?: React.CSSProperties;
}

/** 路径输入：文本 + 浏览（Electron 原生对话框）。 */
export default function PathInput({
  value,
  onChange,
  mode = "folder",
  filters,
  placeholder = "输入或选择路径…",
  style,
}: PathInputProps) {
  const [browsing, setBrowsing] = useState(false);

  const handleBrowse = async () => {
    setBrowsing(true);
    try {
      let path: string | null = null;
      if (mode === "folder") {
        path = await selectFolder();
      } else if (mode === "file") {
        path = await selectFile(filters);
      } else {
        path = await selectSaveFile(filters);
      }
      if (path) onChange(path);
    } finally {
      setBrowsing(false);
    }
  };

  return (
    <div style={{ display: "flex", gap: 6, ...style }}>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-role="import-input"
        style={{ flex: 1 }}
      />
      <button
        className="btn btn-sm"
        onClick={handleBrowse}
        disabled={browsing}
        title="浏览文件夹/文件"
        style={{ flexShrink: 0, minWidth: 52 }}
      >
        {browsing ? "…" : "浏览"}
      </button>
    </div>
  );
}
