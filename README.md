# Clarinora

> 诺研 Nuoyen · 澄诺 Clarinora

医疗病历数据提取工作台：图片 / Excel / 文本 → OCR → 合并 → 大模型抽取 → 审核 → Excel 导出。

桌面程序（Electron），**不依赖 mee / PyQt**。所有处理逻辑内置在 `antigravity/engine/`。

## 技术栈

- **后端**：Python + FastAPI + WebSocket
- **前端**：React 18 + TypeScript + Zustand + Vite
- **桌面**：Electron
- **引擎**：`antigravity/engine`（OCR / 预处理 / 切片 / 合并 / 抽取 / 提示词）

## 目录

```
antigravity/
├── backend/     # FastAPI 路由、病人/项目、阶段引擎
├── engine/      # 纯逻辑（无 UI）
├── electron/    # 桌面壳
├── frontend/    # React 工作台
└── scripts/     # 启动 / 打包
```

## 开发启动

```bash
pip install -r antigravity/requirements.txt
cd antigravity
npm install
npm run dev
```

## 打包

```bash
cd antigravity
npm run build:frontend
npm run dist:mac
```

## 功能

- 项目管理：每项目独立 OCR/LLM/模板/提示词
- 三种数据源：图片 / Excel / 文本
- 8 阶段：源图 → 预处理（含应用内遮罩）→ 切片 → OCR → 合并 → 抽取 → 审核 → 导出
- 提示词工程、批量流水线、拖拽导入
