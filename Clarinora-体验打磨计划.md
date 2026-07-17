# Clarinora 全量体验打磨计划

> 目标：把「能用」打磨成「好用」——正确性、可逆性、可追溯、零等待无指示。
> 约束：应用内遮罩（不做外置 PyQt）；极简深色风格；桌面 Electron。

---

## 设计原则（贯穿全程）

1. **永不静默失败**：加载/保存/导入失败必须 toast + 可操作提示
2. **操作可逆**：编辑有草稿，阶段可重跑，预处理/切片尽量可恢复
3. **每个数字可追溯**：字段 ↔ 源文证据联动
4. **配置真相唯一**：项目级配置优先；全局仅作默认值
5. **文案克制**：去 emoji，统一中文标签 + 状态色 + 简洁符号

---

## Phase A — P0 正确性与数据安全（先做）

### A1. 编辑保存闭环
- 接入 `useDraft` 到 OCR / Merge / Extract 编辑态
- 监听 `clarinora:save`（Ctrl/Cmd+S）真正保存当前编辑
- contentEditable 离焦/切页/切阶段前：有 dirty 则提示保存或自动草稿
- 离开页面前 `beforeunload` 与 draft key 对齐

**涉及**：`hooks/useDraft.ts`、`useKeyboard.ts`、`OCRStage`、`MergeStage`、`ExtractStage`、`Workbench`

### A2. 源图顺序可持久化（或诚实去掉）
- 方案：后端增加 `PUT /stages/{id}/source/order`，runner 按 order 读图
- 若短期不做后端：去掉拖拽排序 + 虚假警告，避免误导

**涉及**：`SourceStage`、`stage_runner`、`patient`、`routes/stages`

### A3. 抽取字段 → 源文高亮（核心 QC）
- `renderSourceText` 输出可检索节点 / mark 段
- 点击字段：在合并文本中高亮关键词并 scrollIntoView
- 可选：显示命中页码 / 摘录

**涉及**：`ExtractStage.tsx`

### A4. Review 笔记防抖 + 确认
- 笔记输入 debounce 500–800ms 再 `updateReview`
- 「全部标记已审」二次确认
- 增加「仅待查」筛选

**涉及**：`ReviewStage.tsx`

### A5. OCR 缩略图与键盘
- 缩略图用真实源文件名扩展名（或统一 `/files/thumb/...` 已有路径）
- `activeCardIdx` clamp 到 `pages.length-1`
- E/R 快捷键改为 `data-action` 属性，不靠 emoji 文本查找

**涉及**：`OCRStage.tsx`

### A6. 任务可停止 + 崩溃恢复
- WS `stage_started` 携带 `task_id`；前端 `runningTasks` 写入
- 停止按钮始终可用
- 启动时把卡在 `running` 的 stage 改为 `interrupted/error`
- `GET /tasks/active` 供重连后重建进度条

**涉及**：`ws.py`、`stage_runner.py`、`workbench.ts`、`StagePanel`、`useWebSocket`

### A7. 错误可见
- `workbench` 所有 load/import 失败 `addToast("error", ...)`
- 导入按钮 loading / disabled

**涉及**：`store/workbench.ts`、`ProjectSidebar`

### A8. 预处理参数真正生效
- 打平 UI 参数 → `ImagePreprocessor.enhance_params`（或改 mee 读 flat keys）
- StagePanel 与 PreprocessStage 配置单一数据源，避免双写不同步

**涉及**：`stage_runner.py`、`mee/.../processor.py`、`StagePanel`、`PreprocessStage`

### A9. 导出修复
- 修复 preview `store` NameError
- 导出使用**项目**模板与输出路径
- 导出路径默认填入项目 `output_excel`

**涉及**：`routes/export.py`、`ExportStage`

### A10. 删除/重命名（管理闭环）
- 病人/项目删除 UI + 后端清理磁盘
- 重命名 API + 侧栏就地改名

**涉及**：`patients.py`、`project.py`、`ProjectSidebar`、`api/client.ts`

---

## Phase B — 应用内遮罩 + 阶段体验（P1 核心）

### B1. 应用内遮罩画布（替代外置工具）
- 复用 Slice 交互模式：拖拽矩形、移动、缩放、列表编辑
- 写入 `preprocess.mask_regions`（患者级），支持从项目默认复制
- StagePanel 去掉 `launchTool("image_mask")`
- 预览：遮罩叠加半透明块

**涉及**：新建 `MaskEditor` 或扩 `PreprocessStage`；`routes/stages` 已有 config PUT 可复用

### B2. 预处理体验
- zoom 真正作用于图片
- 空状态一键「保存参数并执行」
- 版本恢复后自动刷新对比图
- 进度条：preprocess 按文件 current/total

### B3. 切片体验增强
- 明确文案：**区域为病人级模板，应用于全部源图**
- 键盘 Delete 删除选中区域；撤销最近一次框选（简单 stack）
- 执行后自动拉 preview
- 进度条：slice 按文件

### B4. OCR 精读体验
- 卡片：左图右文并排（可折叠）
- 页状态：pending/running/done/error 占位
- 搜索结果跳转 + 高亮
- 单页重 OCR 后推送 `ocr_page_done` 完整 payload 并刷新卡片
- 单页重跑使用**项目** OCR 配置

### B5. 合并阅读器
- 搜索 next/prev 匹配（currentMatch 真正工作）
- dirty 指示 + Ctrl+S
- 监听 clarinora:next/prev 或去掉 KeyboardHelp 虚假声明

### B6. 抽取/审核闭环
- 字段分组：优先读模板/提示词字段顺序，硬编码疾病分组作 fallback
- 源文搜索框
- 审核：跳转到抽取对应字段；异常值（-1/空/越界）默认 flagged 建议
- Tab 下一字段（可选实现）

### B7. 导出体验
- 成功后：复制路径 / 打开所在文件夹（Electron shell）
- 预览列可展开「全部字段」
- 范围「已审核」对齐 review_status 而非仅 patient.status

---

## Phase C — 布局与配置心智（P1）

### C1. 统一视觉语言
- 全局去 emoji（Settings / Prompt / StagePanel / stages）
- PathInput 按钮文案「浏览」
- 状态统一：待处理 / 进行中 / 完成 / 失败 / 待审核 / 待更新
- 过滤芯片用完整短词：全部/待处理/进行中…

### C2. 侧栏管理
- 删除病人/项目（确认）
- 重命名
- 导入 loading
- Shift 范围多选（可选）
- 删除无用 `PatientSidebar.tsx` 或合并

### C3. 顶栏与导航
- 「更多」保留，但未配模板时顶栏弱提示条：「项目未配模板 → 去设置」
- StageNav：文本源灰掉 preprocess/slice/ocr 并标注跳过
- 手动刷新按钮；断线「重新连接」

### C4. StagePanel 真相
- 显示**当前项目** OCR/LLM 配置态，不是全局
- 日志：自动滚底、清空、按级别着色
- 运行中显示 current/total + message

### C5. 设置分层
- 全局设置：仅「默认值 / 连接测试」；模板路径移出或标明「仅无项目时」
- 项目设置：补 OCR/LLM 测试连接；preprocess 默认；「应用到当前全部病人」
- 自定义 OCR 参数真正写入后端

### C6. 提示词工程
- 字段搜索；dirty 标记；保存态
- 生成/增强 loading 防重复点击（已有则强化失败详情）

### C7. 批量
- BatchView：列表接口返回各 stage 摘要，不再全是 "—"
- 批量流水线：失败列表可点击跳转病人
- 进度实时更新（已有 WS 则对齐 UI）

### C8. 快捷键诚实化
- KeyboardHelp 只列已实现项
- 实现或删除：Ctrl+N（data-role=import-input）、Ctrl+S、OCR J/K/E/R
- 合并/抽取未实现项从帮助中移除或补齐

### C9. 拖拽导入
- 校验与项目 source_type 匹配
- 浏览器环境引导用「导入」面板
- 去 emoji

---

## Phase D — 后端体验底座（支撑 A–C）

| 项 | 说明 |
|----|------|
| D1 | preprocess 参数映射修复 |
| D2 | preprocess/slice 进度回调 + stop 检查点 |
| D3 | 崩溃 `running` → interrupted |
| D4 | `task_id` on WS start；`GET /tasks/active`；`GET /patients/{id}/logs` |
| D5 | 图片 width/height；真实缩略图（可选缓存） |
| D6 | 删除清理磁盘；rename API |
| D7 | 导出用项目配置；preview bug |
| D8 | OCR 单页 rerun 用项目设置 + 完整 WS 事件 |
| D9 | 项目密钥隔离（至少 namespace key：`ocr_api:{project_id}`）或明确「全局共用密钥」文案 |
| D10 | 弱化/保留 tools.py；前端不再依赖 launchTool |

---

## Phase E — P2 精致与性能

- 病人列表 / OCR 卡片虚拟列表（>100 时）
- prefers-reduced-motion
- 环境变量 `API_BASE`（非写死 127.0.0.1 可选）
- 导出后 shell.showItemInFolder
- 空状态统一 CTA（导入/配置模板/执行）
- 清理 `glass` 命名与死代码
- 一键「从本阶段重跑下游」
- 新手引导条：创建项目 → 模板 → 提示词 → 导入 → 批量

---

## 建议实施顺序（可交付切片）

```
Sprint 1 (正确性)
  A1 保存/草稿  A3 字段高亮  A4 Review防抖  A5 OCR修复
  A6 停止/恢复  A7 错误toast  A8 预处理参数  A9 导出

Sprint 2 (内置工具 + 阶段)
  B1 应用内遮罩  B2–B7 各阶段体验  D1–D5 后端支撑

Sprint 3 (心智与管理)
  C1–C9 布局配置  A10 删除重命名  D6–D10
  E 性能与收尾
```

---

## 验收标准（体验）

1. 任意编辑 Ctrl+S 可保存；刷新不丢未提交草稿提示
2. 预处理调参后图片肉眼可见变化
3. 遮罩/切片全在 app 内完成，无外置窗口
4. 抽取点击字段能在源文定位证据
5. 长任务有 current/total；可停止；崩溃后不永久「进行中」
6. 删除病人不留幽灵目录；可重命名
7. 界面无业务 emoji；状态文案中文一致
8. 快捷键帮助与真实行为一致
9. 项目配置与运行实际使用配置一致
10. 导出成功可定位文件

---

## 明确不做（本轮）

- 重做玻璃拟态/大动效体系
- 多用户协作 / 云端
- 完整 i18n
- 继续依赖 PyQt 外置 mask/slicer 作为主路径
