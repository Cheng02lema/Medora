# Clarinora · Lattice 风格与人性化体验改造方案

> **状态**：已定稿并落地实现  
> **硬约束**：不改功能名、阶段名、菜单名（源图 / 预处理 / 切片 / OCR / 合并 / 抽取 / 审核 / 导出、批量启动、项目设置…）  
> **视觉参考**：`测试/demo-03-lattice.html`  
> **产品对象**：`antigravity/frontend`  
> **相关**：批量加速见设置「批量加速」；品牌 Nuoyen / Clarinora  

---

## 0. 一句话目标

把「Linear/Notion 圆角深色产品 UI」改成 **Lattice 精密工作台**：直角、网格、等宽数字、紫强调；并在不改功能名的前提下，让「我在哪 / 选了谁 / 能不能跑 / 跑到哪 / 怎么停」一眼可读。

---

## 1. 设计哲学

### 1.1 Lattice 四条铁律

1. **信息密度 > 装饰** — 无大圆角、大阴影、玻璃拟态、插画空状态  
2. **边界必须可见** — 功能块为「板」：`1px` 线框 + 直角，`gap: 8px`  
3. **数字与状态用 mono** — 进度、人数、ID、连接态、阶段编号  
4. **状态用色块** — mint / amber / red / mute 方点，动效极弱  

### 1.2 信息架构（不照搬 demo 左栏阶段）

| Demo | 真 App | 决策 |
|------|--------|------|
| 左 = 阶段 Modules | 左 = 项目 + 病人 | **保留按病人干活** |
| 中 = MATRIX 表 | 中 = 阶段详情 | 单人详情；多选 = 批量矩阵摘要 |
| 右 = Inspector | 右 = 操作面板 | Inspector 气质 + 底栏主操作 |
| 顶 = Brand / 面包屑 / Sys | 顶 = 按钮堆 | **三区 TopBar** |

### 1.3 明确不做

- 改功能/阶段/菜单**名称**  
- 重写 OCR/抽取业务逻辑  
- 业务文案全英文 uppercase  
- 玻璃拟态、花哨动效  

---

## 2. 设计 Token（已写入 `glass.css`）

```
--bg #0c0d10   --panel #12141a   --panel2 #171a22
--fg #d7dbe6   --mute #7a8194    --line #262a36  --line2 #1c1f29
--violet #8b5cf6  --mint #2dd4bf  --amber #f59e0b  --red #f43f5e
圆角 0   拼板 gap 8px   左栏 240px   右栏 280px
背景：24px 网格线（极淡）叠在 --bg 上
字体：--sans 正文；--mono 编号/进度/底栏/面包屑
```

旧变量 `--surface/--primary/--success…` 已映射到新 token，降低回归面。

---

## 3. 布局规格

```
┌──────────────────────────────────────────────────────────┐
│ TOPBAR  Brand | 面包屑(项目/病人/阶段) | 连接·并行·操作   │
│ （可选）未配模板弱提示条                                  │
├──────────┬───────────────────────────┬───────────────────┤
│ SIDEBAR  │ CENTER                    │ RAIL StagePanel   │
│ 240px    │ StageNav 01–08 + 内容     │ hd + 滚动 + 底栏  │
│ 项目/病人│ 单人阶段 or 批量矩阵      │ 执行 / 停止       │
├──────────┴───────────────────────────┴───────────────────┤
│ STATUSBAR  统计 · 同时处理 N · 连接 · Clarinora          │
└──────────────────────────────────────────────────────────┘
```

macOS 红绿灯：TopBar 左侧保留 `padding-left: 78px`。

---

## 4. 状态语言（全站中文统一）

| 内部 status | 展示 | 色 |
|-------------|------|-----|
| pending | 待处理 | mute |
| running | 进行中 | amber |
| done | 完成 | mint |
| error | 失败 | red |
| stale | 待更新 | amber |
| skipped | 跳过 | mute |
| review_pending | 待审核 | amber |

StageNav badge、侧栏方点、批量表、底栏用同一套词。

---

## 5. 组件改造对照

| 组件 | 改造要点 |
|------|----------|
| `glass.css` | Lattice token、网格、直角、hd/kv/row/st/bar、toast/modal |
| `TopBar` | brand 紫方块 + 面包屑 + 连接/并行 + 批量启动/更多；未配模板提示 |
| `ProjectSidebar` | 行式列表（编号+名+状态点+进度）；去彩色头像；Shift 范围选 |
| `StageNav` | `01–08` + 中文阶段名 + 状态 badge |
| `StagePanel` | hd「操作」；底栏栅格主按钮；`对 N 人执行{阶段}`；停止 |
| `StatusBar` | mono 统计 + 同时处理 N + 连接 |
| `BatchView` | KV 四格 + MATRIX 表 + 并行提示 |
| `StageContent` | 空状态分步 01/02；多选进 BatchView |
| `Workbench` | 8px 拼板三栏；TopBar 传入连接态 |

---

## 6. 交互细则

### 6.1 主路径

```
选项目 →（无模板则顶栏提示）→ 导入病人 → 选病人
  → StageNav 看进度 → 右侧执行/编辑 → 下阶段 → 导出
```

### 6.2 选择

| 操作 | 行为 |
|------|------|
| 单击病人 | 单选并加载详情 |
| ⌘/Ctrl+单击 | 切换多选 |
| Shift+单击 | 范围多选（当前过滤列表） |
| 多选 ≥2 | 中区批量摘要，不进单人编辑假象 |

### 6.3 执行按钮

- 1 人：`执行{阶段中文名}`  
- N 人：`对 N 人执行{阶段中文名}`  
- 运行中：底栏「停止」；文案诚实（进行中的做完本阶段）  
- 禁用 reason：未选病人 / 跳过阶段 / 未配模板  

### 6.4 空状态

- 无项目：`01` + 创建/选择项目  
- 有项目无选病人：`02` + 导入或选择；可提示未配模板  

---

## 7. 实施切片（已完成）

- **Sprint A** 皮肤 token + 网格 + 按钮/输入/toast/modal  
- **Sprint B** TopBar / Sidebar / StageNav / StagePanel / StatusBar / Workbench  
- **Sprint C** 批量摘要 / 执行文案 / 空状态 / 模板提示 / Shift 多选  
- **Sprint D** 内容区与全局组件随 token 对齐（field-card、ocr-card、表头等）  

---

## 8. 验收清单

- [x] 与 demo-03 气质：直角、紫、网格、mono  
- [x] 功能名全部中文原样  
- [x] 面包屑可读项目/病人/阶段  
- [x] 多选批量矩阵 + 右栏对 N 人执行  
- [x] 未配模板弱提示  
- [x] 停止/并行文案与批量加速一致  
- [x] macOS 顶栏 padding  

---

## 9. 风险与说明

- 网格过「脏」时可再降 `line2` 透明度或加设置开关（未做开关，默认极淡）  
- 大页 `OcrReviewView` 未单独重写结构，已继承全局 token  
- 旧 `--radius-*` 仍为 0，局部 inline `borderRadius` 可能残留，不影响整体  

---

## 10. 关键路径

| 类型 | 路径 |
|------|------|
| 本文档 | `Clarinora-Lattice-体验改造方案.md` |
| Demo | `测试/demo-03-lattice.html` |
| 样式 | `antigravity/frontend/src/styles/glass.css` |
| 壳 | `Workbench.tsx` `TopBar.tsx` `ProjectSidebar.tsx` `StageNav.tsx` `StagePanel.tsx` `StatusBar.tsx` `BatchView.tsx` `StageContent.tsx` |

*实现以代码为准；本文档为规格与验收依据。*
