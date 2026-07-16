/** 在 OCR 全文中定位 layout 块文本，返回 [start, end) 或 null。 */

export type TextRange = { start: number; end: number; score: number };

function compressMap(text: string): { compact: string; map: number[] } {
  const map: number[] = [];
  let compact = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (/\s/.test(ch)) continue;
    map.push(i);
    compact += ch;
  }
  return { compact, map };
}

export function locateBlockInText(fullText: string, blockText: string): TextRange | null {
  try {
    const full = String(fullText || "");
    // 块文本可能含 latex / 超长，截断避免卡死
    let block = String(blockText || "").trim();
    if (block.length > 400) block = block.slice(0, 400);
    if (!full || !block) return null;

    // 1) 精确子串
    const exact = full.indexOf(block);
    if (exact >= 0) {
      return { start: exact, end: exact + block.length, score: 1 };
    }

    // 2) 去空白后匹配，再映射回原文
    const { compact: fc, map } = compressMap(full);
    const { compact: bc } = compressMap(block);
    if (bc.length >= 2) {
      const ci = fc.indexOf(bc);
      if (ci >= 0 && map[ci] != null) {
        const start = map[ci];
        const endIdx = map[Math.min(map.length - 1, ci + bc.length - 1)];
        if (endIdx != null) {
          return { start, end: endIdx + 1, score: 0.85 };
        }
      }
    }

    // 3) 前 N 字 needle
    const needleLens = [24, 16, 12, 8].filter((n) => n <= block.length);
    for (const n of needleLens) {
      const needle = block.slice(0, n).trim();
      if (needle.length < 4) continue;
      const i = full.indexOf(needle);
      if (i >= 0) {
        return { start: i, end: Math.min(full.length, i + Math.max(n, needle.length)), score: 0.6 };
      }
      const { compact: nc } = compressMap(needle);
      if (nc.length >= 4) {
        const ci = fc.indexOf(nc);
        if (ci >= 0 && map[ci] != null) {
          const start = map[ci];
          const endIdx = map[Math.min(map.length - 1, ci + nc.length - 1)];
          if (endIdx != null) {
            return { start, end: endIdx + 1, score: 0.5 };
          }
        }
      }
    }

    return null;
  } catch {
    return null;
  }
}

/** 把命中区间渲染为带 mark 的片段（供 React 使用的数据）。 */
export function splitByRange(
  text: string,
  range: TextRange | null,
): { type: "text" | "mark"; value: string }[] {
  if (!range || range.start < 0 || range.end <= range.start) {
    return [{ type: "text", value: text }];
  }
  const s = Math.max(0, range.start);
  const e = Math.min(text.length, range.end);
  const parts: { type: "text" | "mark"; value: string }[] = [];
  if (s > 0) parts.push({ type: "text", value: text.slice(0, s) });
  parts.push({ type: "mark", value: text.slice(s, e) });
  if (e < text.length) parts.push({ type: "text", value: text.slice(e) });
  return parts;
}
