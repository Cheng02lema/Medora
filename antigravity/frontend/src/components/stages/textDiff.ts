/** 简单行级 diff，用于 OCR 审查退出确认。 */

export type DiffLine =
  | { type: "same"; text: string }
  | { type: "add"; text: string }
  | { type: "del"; text: string };

/** Myers 简化：LCS 行 diff（页文本通常不太长）。 */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = (before || "").split("\n");
  const b = (after || "").split("\n");
  const n = a.length;
  const m = b.length;
  // DP LCS lengths
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ type: "same", text: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ type: "del", text: a[i] });
      i++;
    } else {
      out.push({ type: "add", text: b[j] });
      j++;
    }
  }
  while (i < n) {
    out.push({ type: "del", text: a[i++] });
  }
  while (j < m) {
    out.push({ type: "add", text: b[j++] });
  }
  return out;
}

export function countDiffStats(lines: DiffLine[]): { add: number; del: number; same: number } {
  let add = 0;
  let del = 0;
  let same = 0;
  for (const l of lines) {
    if (l.type === "add") add++;
    else if (l.type === "del") del++;
    else same++;
  }
  return { add, del, same };
}
