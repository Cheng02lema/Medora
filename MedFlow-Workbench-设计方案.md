# MedFlow Workbench 完整设计方案

## 一、核心问题诊断与策略

### 1.1 为什么流水线不可用而子工具可用

读完代码后,根因清晰:

| 问题 | 位置 | 原因 |
|------|------|------|
| 流水线耦合过重 | `pipeline_controller.py:80` | `PipelineWorker` 把 8 步焊死在一个 QThread 里,中间任何一步失败要么中止全链要么静默跳过,用户看不到中间产物 |
| 中间产物不可见 | `pipeline_controller.py:241` | OCR 结果直接存盘,用户无法在界面上看到每页识别质量,发现错误时只能重来 |
| 不可单步重跑 | 无 | 想只重跑 OCR 或只重跑抽取?不行,必须重跑整条链 |
| 子工具各自为政 | `app_launcher.py:15` | 独立 GUI 用子进程打开,与主界面无数据通道,产物散落在各处 |
| 病人不是一等公民 | `pipeline_controller.py:262` | 以"输入目录"为单位,没有"病人实例"的概念,无法持续跟踪单个病人的处理状态 |

### 1.2 设计策略

**放弃单体流水线,改为"病人实例 + 分阶段工作台"模式:**

```
旧:  目录 → [一体化流水线] → Excel
          ↑ 黑盒,中间不可见,不可单步控制

新:  病人实例 → 源图 → 预处理 → 切片 → OCR → 合并 → 抽取 → 审核 → 导出
              ↑ 每阶段独立执行、独立查看、独立重跑、可人工编辑
```

**技术栈决策:在现有 `antigravity/` (Electron + React + FastAPI) 上演进**,理由:

| 维度 | PyQt5 重写 | Electron + React 演进 |
|------|-----------|----------------------|
| UI 灵活性 | QTableView/QTextEdit 难做富交互 | Canvas 画遮罩、富文本编辑、表单校验都是原生能力 |
| 已有基础 | PyQt5 归档版已废弃 | 病人模型、WebSocket、玻璃态 UI 已就绪 |
| 子工具复用 | 全部要重写 | 纯逻辑模块(engine/converter/processor/slicer/ocr_client)直接被 FastAPI 调用,PyQt5 可视化工具(遮罩/切片框选)保留为可调起的子进程 |
| 跨平台/部署 | PyQt5 打包复杂 | Electron 成熟 |

**保留 PyQt5 子工具的场景**:仅限需要鼠标在图片上画框的工具(遮罩区域设置、切片区域框选),用 `subprocess` 调起,产物写回病人工作目录。其余全部走 Web UI。

---

## 二、病人实例模型(核心数据结构)

### 2.1 病人 = 一个源文件夹 + 独立工作空间

```
workspace/
└── <patient_id>/                    # 如 "016b50b1776e"
    ├── state.json                   # 完整状态持久化(下面详述)
    ├── log.jsonl                    # 逐条日志(JSON Lines,追加写)
    │
    ├── source/                      # 源图(软链接或路径引用,不复制)
    │   ├── 微信图片_001.jpg
    │   ├── 微信图片_002.jpg
    │   └── ...
    │
    ├── preprocess/                  # 预处理产物
    │   ├── 微信图片_001.jpg
    │   └── ...
    │
    ├── slice/                       # 切片产物
    │   └── 微信图片_001/
    │       ├── 微信图片_001-左表格.jpg
    │       └── 微信图片_001-右表格.jpg
    │
    ├── ocr/                         # OCR 逐页产物
    │   ├── 微信图片_001_0.md         # 每页一个 md
    │   ├── 微信图片_001_0.json       # 原始 OCR JSON(含布局信息)
    │   ├── 微信图片_002_0.md
    │   └── ...
    │
    ├── merged.md                    # 合并后的连续文本
    ├── merged.docx                  # 可选的 Word 版本
    │
    ├── extracted.json               # 抽取结果(结构化字段)
    ├── extracted_raw_response.txt   # LLM 原始响应(可追溯)
    │
    ├── review.json                  # 审核状态(每字段是否已审、备注)
    │
    └── _meta/                       # 元数据
        ├── edit_history.json        # 所有人工编辑历史
        └── llm_prompt.txt           # 抽取时使用的完整 prompt
```

### 2.2 state.json 完整结构

```json
{
  "id": "016b50b1776e",
  "name": "张三_中山医院_2025",
  "source_dir": "/Users/.../病历/张三",
  "work_dir": "/Users/.../workspace/016b50b1776e",
  "created_at": "2026-07-14T10:30:00",
  "updated_at": "2026-07-14T11:45:00",

  "stages": {
    "source": {
      "status": "done",
      "image_count": 12,
      "images": [
        {"name": "微信图片_001.jpg", "size": 245678, "width": 1080, "height": 1920}
      ]
    },

    "preprocess": {
      "status": "done",
      "started_at": "...",
      "finished_at": "...",
      "config_used": {"contrast": 2.0, "sharpness": 2.0, "binarize": true},
      "mask_regions": [{"x": 0, "y": 0, "width": 400, "height": 80, "color": "white"}],
      "output_count": 12,
      "error": null
    },

    "slice": {
      "status": "skipped",
      "regions": [],
      "output_count": 0,
      "error": null
    },

    "ocr": {
      "status": "done",
      "model": "PaddleOCR-VL-1.5",
      "preset": "screen_photo",
      "pages": [
        {
          "source_file": "微信图片_001.jpg",
          "page_index": 0,
          "status": "done",
          "md_path": "ocr/微信图片_001_0.md",
          "char_count": 1245,
          "edited": false,
          "error": null
        }
      ],
      "error": null
    },

    "merge": {
      "status": "done",
      "merged_path": "merged.md",
      "docx_path": "merged.docx",
      "page_count": 12,
      "char_count": 15678,
      "edited": false,
      "page_order": ["微信图片_001_0", "微信图片_002_0"],
      "error": null
    },

    "extract": {
      "status": "done",
      "llm_config": {"provider": "DeepSeek", "model": "deepseek-chat"},
      "fields": {
        "姓名": {"value": "张三", "original_value": "张三", "edited": false},
        "年龄": {"value": 52, "original_value": 52, "edited": false},
        "高血压": {"value": 1, "original_value": 1, "edited": false}
      },
      "raw_response_path": "extracted_raw_response.txt",
      "prompt_path": "_meta/llm_prompt.txt",
      "error": null
    },

    "review": {
      "status": "pending",
      "reviewed_fields": {},
      "reviewer": null,
      "reviewed_at": null,
      "notes": {}
    },

    "export": {
      "status": "pending",
      "exported": false,
      "error": null
    }
  },

  "current_stage": "ocr",
  "stale_downstream": ["merge", "extract"]
}
```

### 2.3 阶段状态机

每个阶段独立遵循以下状态机:

```
                    ┌──────────┐
                    │ pending  │ ← 初始 / 被上游编辑标记为 stale
                    └────┬─────┘
                         │ run()
                    ┌────▼─────┐
              ┌─────►│ running  │◄────── rerun()
              │      └────┬─────┘
              │    ┌───────┼───────┐
              │    │       │       │
         ┌────▼──┐ ┌──▼───┐ ┌──▼──┐
         │  done │ │ error│ │skip │
         └────┬──┘ └──┬───┘ └─────┘
              │       │
     edit()   │       │ rerun()
         ┌────▼──┐    │
         │ stale │────┘
         └───────┘
```

**关键规则:**
- `edit()`:用户手动编辑了某阶段的产物(如改了 OCR 文本),则该阶段变为 `stale`,下游所有阶段也标记为 `stale`
- `stale` 阶段可以继续被查看,但 UI 上会显示"⚠ 数据已过期,建议重跑"
- `rerun()`:清除当前阶段产物,重新执行
- `skip()`:用户主动跳过(如不需要预处理),标记为 `skipped`,不算错误
- 下游阶段执行时,自动查找上游最近的产物目录(如 OCR 时按 切片→预处理→源图 顺序找图)

---

## 三、UI 布局设计(四区架构)

### 3.1 整体布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  TopBar                                                                 │
│  MedFlow Workbench     [导入病人] [导出Excel] [⚙设置]    🔍 搜索  筛选▼ │
├──────────┬──────────────────────────────────────┬──────────────────────┤
│          │  StageNav(阶段导航条)                 │                      │
│ Patient  │  ○源图 ●预处理 ○切片 ●OCR ○合并 ○抽取 │  StagePanel          │
│ Sidebar  │  ○审核 ○导出                          │  (右侧操作面板)       │
│ (左侧)   ├──────────────────────────────────────┤                      │
│          │                                      │                      │
│          │  StageContent(主内容区)               │  当前阶段: OCR       │
│          │                                      │                      │
│          │  ┌──────────────────────────────┐    │  [▶ 执行此阶段]      │
│          │  │                              │    │  [▶ 执行到此处]      │
│          │  │   随阶段切换的不同视图:       │    │  [↻ 重新执行]       │
│          │  │                              │    │                      │
│          │  │   源图 → 图片网格             │    │  OCR 设置 ───────    │
│          │  │   OCR  → 左图右文卡片         │    │  接口: paddleocr...  │
│          │  │   合并 → 连续文本阅读器       │    │  模型: PaddleOCR-VL  │
│          │  │   抽取 → 源文+字段表单        │    │  预设: [拍屏 ▼]      │
│          │  │   审核 → 审核表单             │    │  Token: ••••• [测试] │
│          │  │                              │    │  [保存]              │
│          │  └──────────────────────────────┘    │                      │
│          │                                      │  页面进度 ───────    │
│          │                                      │  ✓ p0  1245字        │
│          │                                      │  ✓ p1  2034字        │
│          │                                      │  ⏳ p2  OCR中...     │
│          │                                      │  ○ p3  待识别        │
│          │                                      │                      │
│          │                                      │  实时日志 ───────    │
│          │                                      │  10:32 开始OCR...    │
│          │                                      │  10:33 p0完成        │
├──────────┴──────────────────────────────────────┴──────────────────────┤
│  StatusBar: 共14人 · 待处理3 · 进行中1 · 完成8 · 失败2    CPU 12% RAM 1G│
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 各区域尺寸与行为

| 区域 | 宽度 | 行为 |
|------|------|------|
| **PatientSidebar** | 280px 固定,可折叠至 48px(只显示头像) | 病人列表,搜索,状态筛选 |
| **StageNav** | 高度 48px,占满中间区顶部 | 水平阶段胶囊条,可点击切换视图 |
| **StageContent** | 弹性,占中间区主体 | 随阶段切换内容 |
| **StagePanel** | 340px 固定,可折叠 | 当前阶段的操作按钮 + 设置 + 进度 + 日志 |
| **TopBar** | 高度 52px | 全局操作 |
| **StatusBar** | 高度 28px | 全局统计 |

### 3.3 选中多个病人时的行为

当 PatientSidebar 中选中多个病人时:
- **StageNav** 显示汇总状态(如 OCR 阶段:8/12 完成)
- **StageContent** 显示批量操作视图(表格:每行一个病人,显示该阶段状态)
- **StagePanel** 的"执行此阶段"按钮变为"对选中 N 人执行此阶段"

---

## 四、各阶段视图详细设计

### 4.1 源图阶段(SourceStage)

**主内容区:**

```
┌────────────────────────────────────────────────────────┐
│  📁 源图片 (12 张, 共 23.4 MB)          排序: [文件名▼]  │
│                                                        │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │
│  │      │ │      │ │      │ │      │ │      │         │
│  │ img1 │ │ img2 │ │ img3 │ │ img4 │ │ img5 │  ...    │
│  │      │ │      │ │      │ │      │ │      │         │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘         │
│  001.jpg   002.jpg   003.jpg   004.jpg   005.jpg       │
│  1080×1920 1080×1920 1080×1920 1080×1920 1080×1920     │
│  245 KB    312 KB    198 KB    287 KB    256 KB        │
│                                                        │
│  [在全屏查看] [在文件夹中打开]                           │
└────────────────────────────────────────────────────────┘
```

**交互细节:**
- 点击缩略图 → 全屏 Lightbox(支持 ← → 翻页,滚轮缩放,双击还原)
- 拖拽缩略图 → 重新排序(影响 OCR 页序和合并顺序,在拖拽时显示"⚠ 将影响后续 OCR/合并顺序")
- 缩略图右上角显示页码角标(1, 2, 3...)
- 排序选项:文件名 / 修改时间 / 文件大小
- 鼠标悬停 → 显示尺寸、大小、修改时间

**右侧面板:**
- 图片数量、总大小统计
- 文件列表(可点击跳转到对应图片)
- "导入后自动完成"提示(此阶段无需执行)

### 4.2 预处理阶段(PreprocessStage)

**主内容区 — 对比视图:**

```
┌────────────────────────────────────────────────────────┐
│  ◄ 第 3/12 张 ►                          [100% ▼]      │
│                                                        │
│  ┌─────────────────────┬─────────────────────┐         │
│  │                     │                     │         │
│  │   原始图片           │   预处理后           │         │
│  │                     │                     │         │
│  │  [img3 原图]        │  [img3 增强后]      │         │
│  │                     │                     │         │
│  │                     │                     │         │
│  └─────────────────────┴─────────────────────┘         │
│  对比模式: [并排] [滑动对比] [切换]                      │
└────────────────────────────────────────────────────────┘
```

**交互细节:**
- 顶部翻页器:逐张查看预处理前后对比
- 三种对比模式:
  - **并排**:左右并排(默认)
  - **滑动对比**:中间一条可拖动的分隔线,左侧原图、右侧处理后
  - **切换**:同一位置,按钮切换原图/处理后
- 右下角缩放控制(25% - 400%)
- 如果未执行预处理,显示"尚未预处理,[执行预处理] 后可查看对比"

**右侧面板:**
```
  预处理参数
  ─────────────
  对比度:    [====●====] 2.0
  锐度:      [===●=====] 1.5
  亮度:      [==●======] 1.2
  去噪:      [✓]
  二值化:    [✓]  阈值: [140]
  
  遮罩区域
  ─────────────
  ☐ 启用遮罩
  [✏ 编辑遮罩区域]  ← 打开 PyQt5 子工具或 Web Canvas
  已设 2 个区域:
    · 左上角(0,0,400,80)
    · 右下角(800,1800,280,120)
  [清除遮罩]

  [▶ 执行预处理]
  [↻ 用新参数重新执行]
```

### 4.3 切片阶段(SliceStage)

**主内容区 — 区域预览:**

```
┌────────────────────────────────────────────────────────┐
│  ◄ 第 3/12 张 ►                                        │
│                                                        │
│  ┌──────────────────────────────────────────┐          │
│  │                                          │          │
│  │    ┌──────────────┐                      │          │
│  │    │ 左表格        │                      │          │
│  │    │ (绿框)       │  ┌──────────────┐   │          │
│  │    │              │  │ 右表格        │   │          │
│  │    │              │  │ (蓝框)       │   │          │
│  │    └──────────────┘  │              │   │          │
│  │                      └──────────────┘   │          │
│  │  [原始图片,叠加区域框]                   │          │
│  └──────────────────────────────────────────┘          │
│                                                        │
│  区域列表:                                              │
│  ● 左表格  (50,120)→(520,800)    预览 →  [缩略图]       │
│  ● 右表格  (560,120)→(1030,800)  预览 →  [缩略图]       │
└────────────────────────────────────────────────────────┘
```

**交互细节:**
- 在原图上叠加彩色矩形显示每个切片区域
- 鼠标悬停区域 → 高亮 + 显示区域名
- 点击区域的"预览"→ 查看该区域的切片结果图片
- "编辑区域"按钮 → 打开 PyQt5 切片工具(`image_slicer_qt5.py`)或 Web Canvas 编辑器
- 如果未配置区域,显示"未配置切片区域,此阶段将自动跳过"

**右侧面板:**
- 区域列表(名称、坐标)
- [执行切片] / [清除区域] / [编辑区域]

### 4.4 OCR 阶段(OCRStage)— 最核心的交互视图

**主内容区 — 逐页卡片列表:**

```
┌────────────────────────────────────────────────────────┐
│  OCR 识别结果 (12 页)                  [全部展开▼]      │
│                                                        │
│  ┌─────────────┬───────────────────────────────────┐   │
│  │             │ ✓ page 0 · 1245 字 · 已编辑       │   │
│  │  [缩略图]   │ ┌─────────────────────────────┐  │   │
│  │  img1       │ │入院日期: 2025-03-15          │  │   │
│  │  001.jpg    │ │姓名: 张三                    │  │   │
│  │             │ │年龄: 52岁                    │  │   │
│  │             │ │...                           │  │   │
│  │             │ │[可点击编辑]                   │  │   │
│  │             │ └─────────────────────────────┘  │   │
│  │             │ [↻ 重新OCR此页] [✓ 保存修改]     │   │
│  └─────────────┴───────────────────────────────────┘   │
│                                                        │
│  ┌─────────────┬───────────────────────────────────┐   │
│  │             │ ⏳ page 1 · OCR 识别中...          │   │
│  │  [缩略图]   │ ┌─────────────────────────────┐  │   │
│  │  img2       │ │  [进度条 ████░░░░ 45%]      │  │   │
│  │  002.jpg    │ │  正在调用 OCR API...         │  │   │
│  │             │ └─────────────────────────────┘  │   │
│  └─────────────┴───────────────────────────────────┘   │
│                                                        │
│  ┌─────────────┬───────────────────────────────────┐   │
│  │             │ ○ page 2 · 待识别                 │   │
│  │  [缩略图]   │  [点击执行OCR]                     │   │
│  │  img3       │                                    │   │
│  └─────────────┴───────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

**交互细节(极其重要,这是用户最常用的工作区):**

1. **卡片布局**:每页一个卡片,左侧缩略图(可点击放大),右侧 OCR 文本
2. **文本编辑**:点击文本区域进入编辑模式,直接修改 OCR 错误(如 `(一)` → `(-)`,错别字修正)
3. **编辑标记**:编辑过的页面显示"✏ 已编辑"标记,并在 `state.json` 中记录 `edited: true`
4. **单页重 OCR**:每张卡片右上角有"↻ 重新OCR此页"按钮,只重跑这一页
5. **批量操作**:顶部"全部展开/折叠"切换,可批量"重新OCR所有未完成页"
6. **实时更新**:OCR 进行中时,卡片状态从 `○待识别` → `⏳识别中(进度条)` → `✓完成(字数)`,通过 WebSocket 推送
7. **HTML 渲染**:OCR 文本中的 HTML 表格自动渲染为可视化表格(复用 `converter.py` 的 `clean_html_tags` 逻辑)
8. **搜索**:顶部搜索框,在所有页文本中搜索关键词,高亮匹配,跳转到对应卡片
9. **字号控制**:文本区可调字号(小/中/大),长病历可舒适阅读

**右侧面板:**
```
  OCR 配置
  ─────────────
  接口地址:  https://paddleocr...
  模型:      PaddleOCR-VL-1.5
  预设:      [拍摄电脑屏幕 ▼]
             · 默认(原始)
             · 屏幕截图
             · 拍摄电脑屏幕  ✓
             · 拍摄纸质报告
             · 最强通用
  Token:     •••••••• [测试连接]

  [保存配置]
  [▶ 执行OCR(未完成页)]
  [↻ 重新OCR全部]

  页面进度
  ─────────────
  ✓ page 0   1245字  已编辑
  ✓ page 1   2034字
  ⏳ page 2   识别中 45%
  ○ page 3   待识别
  ...
  统计: 8/12 完成 · 平均 1567 字/页

  实时日志
  ─────────────
  10:32 开始OCR batch...
  10:33 ✓ img1 → 1245字
  10:35 ✓ img2 → 2034字
  10:36 ⏳ img3 上传中...
```

### 4.5 合并阶段(MergeStage)

**主内容区 — 连续文本阅读器:**

```
┌────────────────────────────────────────────────────────┐
│  📄 合并文档 (12 页 · 15678 字)     [字号: 中▼] [搜索] │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  ── 第 1 页 (微信图片_001) ──                    │  │
│  │                                                  │  │
│  │  入院日期: 2025-03-15                            │  │
│  │  姓名: 张三                                      │  │
│  │  年龄: 52岁                                      │  │
│  │  主诉: 反复头晕、头痛伴四肢无力3月               │  │
│  │                                                  │  │
│  │  ┌─────────────────────────────────┐            │  │
│  │  │ 检验项目 │ 结果 │ 参考值 │ 单位 │  ← HTML表格  │  │
│  │  │──────────┼──────┼────────┼──────│   渲染      │  │
│  │  │ 血红蛋白 │ 97   │ 130-175│ g/L  │            │  │
│  │  │ 白细胞   │ 8.5  │ 3.5-9.5│10^9/L│            │  │
│  │  └─────────────────────────────────┘            │  │
│  │                                                  │  │
│  │  ── 第 2 页 (微信图片_002) ──                    │  │
│  │                                                  │  │
│  │  现病史: 患者于3月前无明显诱因出现...            │  │
│  │  ...                                             │  │
│  │                                                  │  │
│  │  [点击任意位置可编辑文本]                         │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  [◀ 上一页]  第 1/12 页  [下一页 ▶]   [跳转到页▼]     │
└────────────────────────────────────────────────────────┘
```

**交互细节:**
- **分页标记**:页与页之间用淡色分隔线 + 页码标注(如"── 第 2 页 (微信图片_002) ──"),不使用 `---PAGE_BREAK---` 原始标记
- **HTML 表格渲染**:OCR 产生的 HTML 表格自动渲染为可视化表格,不是原始 HTML 代码
- **行内编辑**:点击文本任意位置进入编辑模式,修改后显示"✏ 已编辑"标记,需点击"保存修改"
- **页码导航**:底部翻页器 + "跳转到页"下拉框
- **搜索**:顶部搜索框,在合并文本中搜索关键词,高亮所有匹配,可跳转
- **字号控制**:小(12px)/中(14px)/大(16px)/特大(18px)
- **LaTeX 渲染**:`\times` → ×, `\mu` → μ(复用 `converter.py` 的 `convert_latex_symbols`)
- **OCR 错误修正高亮**:自动应用 `fix_ocr_errors` 的规则(如 `(一)` → `(-)`),修改处用淡黄色背景标记

**右侧面板:**
```
  合并设置
  ─────────────
  页数: 12 页
  字数: 15678 字
  生成 Word: [✓]

  页序
  ─────────────
  1. 微信图片_001_0
  2. 微信图片_002_0
  3. 微信图片_003_0
  ...
  [拖拽可调整顺序]

  [▶ 执行合并]
  [📄 生成 Word 文档]
  [💾 保存修改]
  [↻ 重新合并(丢弃编辑)]

  编辑历史
  ─────────────
  10:45 修改 第2页 "旦白"→"蛋白"
  10:47 修改 第5页 "(一)"→"(-)"
```

### 4.6 抽取阶段(ExtractStage)— 第二核心视图

**主内容区 — 源文与字段表单分屏对照:**

```
┌────────────────────────────────────────────────────────┐
│  🔍 抽取结果                           [字段筛选▼]      │
│ ┌────────────────────────┬───────────────────────────┐ │
│ │ 源文本(可滚动)         │ 提取字段表单              │ │
│ │                        │                           │ │
│ │  入院日期: 2025-03-15  │ 基本信息                  │ │
│ │  姓名: 张三            │ ┌─────────────────────┐  │ │
│ │  年龄: 52岁            │ │ 姓名: [张三        ]│  │ │
│ │  主诉: 反复头晕...     │ │ 年龄: [52          ]│  │ │
│ │                        │ │住院号:[-1          ]│  │ │
│ │  既往史:               │ └─────────────────────┘  │ │
│ │  高血压病史8年余       │ 既往史                    │ │
│ │  否认糖尿病            │ ┌─────────────────────┐  │ │
│ │                        │ │高血压: [1 ▼]  ← 有  │  │ │
│ │  ┌─ 检验 ──────────┐  │ │糖尿病: [0 ▼]  ← 无  │  │ │
│ │  │ 血红蛋白: 97g/L │  │ │高脂血症:[-1▼] ←未提及│  │ │
│ │  │ 白细胞: 8.5     │  │ │冠心病: [-1▼]        │  │ │
│ │  └─────────────────┘  │ └─────────────────────┘  │ │
│ │                        │                           │ │
│ │  治疗方案:             │ 实验室检查                │ │
│ │  泼尼松60mg/日         │ ┌─────────────────────┐  │ │
│ │  环磷酰胺0.8g/月       │ │血红蛋白: [97    ]g/L │  │ │
│ │                        │ │白细胞:   [8.5   ]    │  │ │
│ │                        │ │血沉:     [85    ]↑   │  │ │
│ │                        │ │CRP:      [32.5  ]↑   │  │ │
│ │                        │ │IL-10:    [5.2   ]    │  │ │
│ │                        │ │cTnT:     [-1    ]    │  │ │
│ │                        │ └─────────────────────┘  │ │
│ │                        │                           │ │
│ │  [点击字段可高亮源文]  │ [💾 保存修改]             │ │
│ └────────────────────────┴───────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

**交互细节(极其重要):**

1. **分屏对照**:左 50% 源文本(只读,可滚动),右 50% 字段表单(可编辑)
2. **字段高亮联动**:点击右侧某个字段 → 左侧源文本自动滚动到相关段落并高亮(基于关键词匹配)
3. **字段类型感知**:
   - **存在性判断**(0/1/-1):下拉框 `[有 ▼] [无 ▼] [未提及 ▼]`
   - **数值提取**:数字输入框 + 单位标注 + 异常标记(↑高于参考值 / ↓低于参考值)
   - **文本提取**:多行文本框
   - **日期**:日期选择器
4. **异常值标记**:数值字段旁自动显示 ↑/↓ 标记(如果有参考值范围),异常值用橙色背景
5. **未提及标记**:`-1` 的字段用灰色背景 + "未提及"标签
6. **编辑追踪**:用户修改过的字段显示蓝色左边框 + "✏ 已编辑"tooltip
7. **字段分组**:按模板分组(基本信息/既往史/个人史/主诉/现病史/实验室/影像/诊疗),可折叠
8. **字段搜索**:输入框搜索字段名,快速定位
9. **验证提示**:
   - 类型不匹配(如数字字段填了文字)→ 红色边框 + 提示
   - 必填字段为空 → 黄色边框
   - 超出合理范围(如年龄 200)→ 橙色边框
10. **LLM 原始响应**:可展开查看 LLM 的原始 JSON 响应和完整 prompt(追溯用)

**右侧面板:**
```
  抽取配置
  ─────────────
  Provider: [DeepSeek ▼]
  模型:     [deepseek-chat]
  API Key:  •••••••• [测试]
  Temperature: [0.0]
  Max Tokens:  [8000]

  抽取模板
  ─────────────
  当前: 中山医院戴老师.json
  字段数: 80
  [更换模板]

  [▶ 执行抽取]
  [↻ 重新抽取]

  字段统计
  ─────────────
  总字段: 80
  有值:   52
  未提及: 23  (-1)
  已编辑: 5
  异常值: 3   (↑/↓)
  空白:   0

  [查看LLM原始响应]
  [查看完整Prompt]
```

### 4.7 审核阶段(ReviewStage)

**主内容区 — 与抽取阶段类似但增加审核功能:**

```
┌────────────────────────────────────────────────────────┐
│  ✓ 审核模式    审核进度: 52/80 字段 (65%)               │
│ ┌────────────────────────┬───────────────────────────┐ │
│ │ 源文本                 │ 字段审核表                 │ │
│ │                        │                           │ │
│ │  ...                   │ ✓ 姓名: 张三        [已审]│ │
│ │  高血压病史8年余        │ ✓ 年龄: 52          [已审]│ │
│ │  ...                   │ ✓ 高血压: 1         [已审]│ │
│ │                        │ ○ 糖尿病: 0     [待审][📝]│ │
│ │                        │ ○ 血红蛋白: 97  [待审][📝]│ │
│ │                        │                           │ │
│ │                        │ 备注:                     │ │
│ │                        │ ┌─────────────────────┐  │ │
│ │                        │ │血红蛋白值与源文一致  │  │ │
│ │                        │ └─────────────────────┘  │ │
│ │                        │                           │ │
│ │                        │ [✓ 标记已审] [✗ 标记待查]│ │
│ └────────────────────────┴───────────────────────────┘ │
│  [全部标记已审]  [仅审核未编辑字段]                      │
└────────────────────────────────────────────────────────┘
```

**交互细节:**
- 每个字段旁有审核状态:✓已审 / ○待审 / ✗待查(有疑问)
- 可为每个字段添加备注
- "全部标记已审"一键完成
- "仅审核未编辑字段"过滤出 LLM 原始结果(跳过用户已编辑的)
- 审核完成后,病人状态变为"已审核",可导出

### 4.8 导出阶段(ExportStage)

**主内容区 — 导出预览:**

```
┌────────────────────────────────────────────────────────┐
│  📊 导出预览                                            │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 姓名 │ 年龄 │ 高血压 │ 血沉 │ CRP │ ... │ 状态  │  │
│  │──────┼──────┼────────┼──────┼──────┼─────┼───────│  │
│  │ 张三 │ 52   │ 1      │ 85   │ 32.5 │ ... │ ✓已审 │  │ ← 当前行
│  │ 李四 │ 45   │ 0      │ 42   │ 12.0 │ ... │ ✓已审 │  │
│  │ 王五 │ 67   │ 1      │ -1   │ -1   │ ... │ ⚠待审 │  │
│  │ ...  │      │        │      │      │     │       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  导出范围:                                             │
│  ○ 仅当前病人(张三)                                    │
│  ○ 所有已审核病人(8人)                                 │
│  ○ 所有已完成抽取的病人(12人,含未审核)                  │
│  ○ 手动选择                                            │
│                                                        │
│  输出路径: /Users/.../结果.xlsx            [浏览]      │
│  [▶ 导出 Excel]                                        │
└────────────────────────────────────────────────────────┘
```

---

## 五、病人侧边栏详细设计

### 5.1 布局

```
┌──────────────────────────┐
│ 病人实例          [◀折叠] │
│ 🔍 [搜索病人...]          │
│                          │
│ 筛选                     │
│ ┌──────────────────────┐ │
│ │ ● 全部 (14)           │ │
│ │   待处理 (3)          │ │
│ │   进行中 (1)          │ │
│ │   已完成 (8)          │ │
│ │   失败 (2)            │ │
│ │   待审核 (5)          │ │
│ └──────────────────────┘ │
│                          │
│ ┌──────────────────────┐ │
│ │ ●  张三               │ │ ← 选中(蓝色边框)
│ │   中山医院_2025       │ │
│ │   OCR中 · 8/12页      │ │ ← 当前阶段 + 进度
│ │   ▓▓▓▓▓▓░░░░ 67%     │ │ ← 进度条
│ └──────────────────────┘ │
│                          │
│ ┌──────────────────────┐ │
│ │ ○  李四               │ │
│ │   华山医院_2025       │ │
│ │   待处理              │ │
│ └──────────────────────┘ │
│                          │
│ ┌──────────────────────┐ │
│ │ ✓  王五               │ │
│ │   中山医院_2024       │ │
│ │   已完成 · 已审核     │ │
│ └──────────────────────┘ │
│                          │
│ ┌──────────────────────┐ │
│ │ ✗  赵六               │ │
│ │   OCR失败             │ │
│ │   ⚠ Token未配置       │ │ ← 错误提示
│ └──────────────────────┘ │
│                          │
│ [＋ 录入病人文件夹]       │
└──────────────────────────┘
```

### 5.2 病人卡片元素

| 元素 | 说明 |
|------|------|
| 头像(左上) | 首字母 + 哈希颜色(复用 antigravity 的 `colorForName`) |
| 名称 | 文件夹名 |
| 副标题 | 来源标识(可从文件夹名提取) |
| 当前阶段 | "OCR中" / "待处理" / "已完成" / "失败" |
| 进度条 | 当前阶段内进度(如 OCR 8/12 页) |
| 状态点 | pending(灰) / running(蓝脉冲) / done(青) / error(红) |
| 错误提示 | 失败时显示简短错误原因 |

### 5.3 筛选逻辑

| 筛选项 | 条件 |
|--------|------|
| 待处理 | 所有阶段都是 pending |
| 进行中 | 任一阶段是 running |
| 已完成 | 所有阶段是 done 或 skipped |
| 失败 | 任一阶段是 error 且没有 running |
| 待审核 | 抽取完成但审核未完成 |

### 5.4 多选行为

- 单击:选中一个病人,中间区显示该病人的当前阶段视图
- Ctrl/Cmd+点击:追加选中,中间区显示批量操作视图
- Shift+点击:范围选中
- 选中多个时,侧边栏底部显示"已选 N 人" + "全选" + "取消选择"

---

## 六、后端架构设计

### 6.1 目录结构

```
antigravity/
├── electron/
│   ├── main.js              # Electron 主进程(已有,微调)
│   └── preload.js           # 预加载(加 IPC:打开 PyQt5 子工具)
│
├── backend/
│   ├── __init__.py
│   ├── app.py               # FastAPI 入口(已有,加路由)
│   ├── state.py             # 全局单例(已有,增强)
│   ├── patient.py           # 病人模型(重写,加 per-stage 状态)
│   ├── stage_runner.py      # 阶段执行引擎(新,替代 tasks.py)
│   ├── ws.py                # WebSocket(已有,增强消息类型)
│   │
│   ├── routes/
│   │   ├── patients.py      # 病人 CRUD(重写)
│   │   ├── stages.py        # 阶段执行 + 产物读写(新)
│   │   ├── settings.py      # 配置(已有,增强)
│   │   ├── files.py         # 文件服务(已有,增强)
│   │   └── export.py        # 导出(新)
│   │
│   └── tools/               # 封装 mee 纯逻辑(新)
│       ├── __init__.py
│       ├── preprocess.py    # 封装 image_preprocess/processor.py
│       ├── slice.py         # 封装 image_slicer/slicer.py
│       ├── ocr.py           # 封装 ocr_client.py + ocr_presets.py
│       ├── merge.py         # 封装 markdown_converter/converter.py
│       ├── extract.py       # 封装 medical_extractor/engine.py
│       ├── export.py        # 封装 export_rows_to_excel
│       └── cleanup.py       # 封装 cleanup/__init__.py
│
├── frontend/
│   └── src/
│       ├── api/
│       │   └── client.ts    # API 客户端(重写,加阶段 API)
│       ├── store/
│       │   └── workbench.ts # Zustand 状态管理(新)
│       ├── hooks/
│       │   ├── usePatient.ts
│       │   ├── useStage.ts
│       │   └── useWebSocket.ts
│       ├── components/
│       │   ├── Workbench.tsx          # 四区根布局
│       │   ├── TopBar.tsx
│       │   ├── PatientSidebar.tsx     # 左侧
│       │   ├── StageNav.tsx           # 阶段导航条
│       │   ├── StagePanel.tsx         # 右侧操作面板
│       │   ├── StatusBar.tsx
│       │   └── stages/
│       │       ├── SourceStage.tsx    # 源图网格
│       │       ├── PreprocessStage.tsx # 对比视图
│       │       ├── SliceStage.tsx     # 区域预览
│       │       ├── OCRStage.tsx       # 逐页卡片
│       │       ├── MergeStage.tsx     # 文本阅读器
│       │       ├── ExtractStage.tsx   # 源文+表单
│       │       ├── ReviewStage.tsx    # 审核表单
│       │       └── ExportStage.tsx    # 导出预览
│       └── styles/
│           └── glass.css              # 已有,扩展
│
└── workspace/               # 病人工作目录(已有)
```

### 6.2 API 端点设计(完整)

```
# ─── 病人管理 ───
GET    /patients
  → [{id, name, status, current_stage, progress, error}]

POST   /patients/import
  body: {path: str}
  → [{id, name, ...}]  # 新录入的病人

GET    /patients/{id}
  → 完整 state.json

DELETE /patients/{id}
  → {ok: true}

# ─── 阶段状态 ───
GET    /patients/{id}/stages
  → {source: {status, ...}, preprocess: {...}, ...}

GET    /patients/{id}/stages/{stage}
  → 该阶段的完整状态 + 产物列表

# ─── 阶段执行 ───
POST   /patients/{id}/stages/{stage}/run
  → {task_id: str}  # 异步执行,通过 WebSocket 推进度

POST   /patients/{id}/stages/{stage}/rerun
  → {task_id: str}  # 清除旧产物,重新执行

POST   /batch/stages/{stage}/run
  body: {patient_ids: [str]}
  → {task_id: str}  # 批量执行同一阶段

POST   /tasks/{task_id}/stop
  → {ok: true}

# ─── 阶段产物读写 ───

# 源图
GET    /patients/{id}/stage/source/images
  → [{name, path, size, width, height, thumb_url}]

# 预处理
GET    /patients/{id}/stage/preprocess/images
PUT    /patients/{id}/stage/preprocess/config
  body: {contrast, sharpness, brightness, denoise, binarize, threshold}
PUT    /patients/{id}/stage/preprocess/mask-regions
  body: {regions: [{x, y, width, height, color}]}

# 切片
GET    /patients/{id}/stage/slice/regions
PUT    /patients/{id}/stage/slice/regions
  body: {regions: [{name, x1, y1, x2, y2}]}
GET    /patients/{id}/stage/slice/preview/{image_name}
  → 切片预览图

# OCR
GET    /patients/{id}/stage/ocr/pages
  → [{page_index, source_file, status, text, char_count, edited}]
GET    /patients/{id}/stage/ocr/page/{page_index}
  → {page_index, text, html_tables, status}
PUT    /patients/{id}/stage/ocr/page/{page_index}
  body: {text: str}  # 人工编辑 OCR 文本

# 合并
GET    /patients/{id}/stage/merge/text
  → {text, page_count, char_count, page_order}
PUT    /patients/{id}/stage/merge/text
  body: {text: str}  # 人工编辑合并文本
PUT    /patients/{id}/stage/merge/page-order
  body: {order: [str]}

# 抽取
GET    /patients/{id}/stage/extract/fields
  → {fields: {name: {value, original_value, edited}}, validation: {...}}
PUT    /patients/{id}/stage/extract/fields
  body: {fields: {name: value}}  # 人工编辑字段
GET    /patients/{id}/stage/extract/raw-response
  → LLM 原始响应文本
GET    /patients/{id}/stage/extract/prompt
  → 使用的完整 prompt

# 审核
GET    /patients/{id}/stage/review
  → {reviewed_fields, notes, progress}
PUT    /patients/{id}/stage/review
  body: {field_name: {reviewed: bool, note: str}}

# ─── 导出 ───
POST   /export/excel
  body: {patient_ids: [str], output_path: str}
  → {path: str, row_count: int}

GET    /export/preview
  query: patient_ids=a,b,c
  → [{name, fields: {...}, review_status}]

# ─── 文件服务 ───
GET    /files/image/{id}/{stage}/{filename}
  → 原图(源图/预处理/切片)

GET    /files/thumb/{id}/{stage}/{filename}
  → 缩略图(200x200)

# ─── 设置 ───
GET    /settings
PUT    /settings/ocr
PUT    /settings/extract_llm
PUT    /settings/pipeline
PUT    /settings/preprocess
PUT    /settings/slice

# ─── 工具调起 ───
POST   /tools/launch/image_mask
  → 启动 PyQt5 遮罩工具(子进程)

POST   /tools/launch/image_slicer
  → 启动 PyQt5 切片工具(子进程)

# ─── WebSocket ───
WS     /ws/progress
  消息类型:
    {type: "stage_started", patient_id, stage}
    {type: "stage_progress", patient_id, stage, message, progress}
    {type: "stage_done", patient_id, stage, status, message}
    {type: "patient_update", patient: summary}
    {type: "task_done", task_id, summary}
    {type: "log", patient_id, stage, level, message, timestamp}
```

### 6.3 阶段执行引擎(stage_runner.py)

替代现有 `tasks.py` 的 `TaskRunner`,核心变化:

```python
class StageRunner:
    """执行单个病人单个阶段,或批量执行。
    
    与旧 TaskRunner 的区别:
    - 一次只执行一个阶段(不是全链路)
    - 每个阶段有独立的 handler
    - 产物写入病人工作目录的约定子目录
    - 实时通过 on_progress 回调推送进度
    - 失败不传染其他病人
    """
    
    STAGE_HANDLERS = {
        "preprocess": "_run_preprocess",
        "slice": "_run_slice", 
        "ocr": "_run_ocr",
        "merge": "_run_merge",
        "extract": "_run_extract",
        "cleanup": "_run_cleanup",
    }
    
    def run_single(self, patient_id: str, stage: str):
        """执行单个病人的单个阶段。"""
        patient = self.store.get(patient_id)
        patient.stages[stage].status = "running"
        self._broadcast(patient, stage, "started")
        try:
            handler = getattr(self, self.STAGE_HANDLERS[stage])
            result = handler(patient)
            patient.stages[stage].status = "done"
            self._broadcast(patient, stage, "done", result)
        except SkipStage as skip:
            patient.stages[stage].status = "skipped"
            self._broadcast(patient, stage, "skipped", str(skip))
        except Exception as exc:
            patient.stages[stage].status = "error"
            patient.stages[stage].error = str(exc)
            self._broadcast(patient, stage, "error", str(exc))
        patient.save()
    
    def run_batch(self, patient_ids: List[str], stage: str):
        """批量执行同一阶段,串行,continue-on-error。"""
        for pid in patient_ids:
            if self.is_stopped:
                break
            self.run_single(pid, stage)
```

**各阶段 handler 封装 mee 纯逻辑的方式:**

```python
def _run_ocr(self, patient: Patient):
    """OCR 阶段:查找上游最新图片 → 逐页 OCR → 存 md + json。"""
    from mee.modules.ocr_client import AsyncOCRClient, save_layout_results
    
    # 1. 确定输入目录(切片 → 预处理 → 源图,取第一个有图的)
    for candidate in [patient.slice_dir, patient.preprocess_dir, patient.source_dir]:
        files = list_image_files(candidate)
        if files:
            break
    if not files:
        raise Exception("没有可 OCR 的图片")
    
    # 2. 创建 OCR 客户端
    client = AsyncOCRClient(
        url=self.settings["ocr_url"],
        token=self.settings["ocr_token"],
        model=self.settings["ocr_model"],
        preset=self.settings["ocr_preset"],
        log_callback=lambda msg: self._emit_log(patient, "ocr", msg),
    )
    
    # 3. 逐页 OCR,每页完成后立即保存 + 推送进度
    patient.ocr_dir.mkdir(parents=True, exist_ok=True)
    for idx, file_path in enumerate(files):
        if self.is_stopped:
            break
        self._emit_progress(patient, "ocr", idx, len(files), f"OCR {file_path.name}")
        results = client.process_file(file_path)
        if results:
            save_layout_results(results, patient.ocr_dir / file_path.stem)
            # 更新 state 中的 page 状态
            patient.stages["ocr"].pages[idx].status = "done"
            patient.stages["ocr"].pages[idx].md_path = f"ocr/{file_path.stem}_0.md"
            patient.save()  # 实时持久化
    
    # 4. 检查结果
    done_count = sum(1 for p in patient.stages["ocr"].pages if p.status == "done")
    if done_count == 0:
        raise Exception("所有图片 OCR 失败")
    return f"OCR: {done_count}/{len(files)} 页成功"
```

### 6.4 WebSocket 消息协议

```typescript
// 前端收到的消息类型
type WSMessage =
  // 阶段开始
  | { type: "stage_started"; patient_id: string; stage: string }
  // 阶段进度(如 OCR 第 3/12 页)
  | { type: "stage_progress"; patient_id: string; stage: string; current: number; total: number; message: string }
  // 阶段完成
  | { type: "stage_done"; patient_id: string; stage: string; status: "done" | "error" | "skipped"; message: string }
  // 病人状态更新(推送给左侧栏更新卡片)
  | { type: "patient_update"; patient: PatientSummary }
  // 任务完成汇总
  | { type: "task_done"; task_id: string; summary: { done: number; error: number } }
  // 日志行
  | { type: "log"; patient_id: string; stage: string; level: "info" | "warn" | "error"; message: string; timestamp: string }
```

---

## 七、前端状态管理

### 7.1 使用 Zustand(轻量,无需 Provider)

```typescript
// store/workbench.ts
interface WorkbenchState {
  // ─── 数据 ───
  patients: PatientSummary[]
  selectedIds: string[]
  currentPatientId: string | null  // 单选时查看的病人
  currentStage: StageKey           // 当前查看的阶段
  
  // 各阶段的详细数据(按需加载,缓存)
  stageData: Map<string, StageDetail>  // key: `${patientId}:${stage}`
  
  // ─── 运行状态 ───
  runningTasks: Map<string, RunningTask>  // task_id → {patient_id, stage, progress}
  logs: LogEntry[]
  
  // ─── 设置 ───
  settings: SettingsPayload | null
  
  // ─── Actions ───
  loadPatients: () => Promise<void>
  importPatients: (path: string) => Promise<void>
  selectPatient: (id: string, multi: boolean) => void
  loadStageData: (patientId: string, stage: StageKey) => Promise<void>
  runStage: (patientId: string, stage: StageKey) => Promise<void>
  runBatchStage: (patientIds: string[], stage: StageKey) => Promise<void>
  stopTask: (taskId: string) => Promise<void>
  editOcrPage: (patientId: string, pageIndex: number, text: string) => Promise<void>
  editMergedText: (patientId: string, text: string) => Promise<void>
  editExtractField: (patientId: string, fieldName: string, value: any) => Promise<void>
  saveReview: (patientId: string, reviewData: ReviewData) => Promise<void>
  exportExcel: (patientIds: string[], outputPath: string) => Promise<void>
  
  // ─── WebSocket ───
  onWSMessage: (msg: WSMessage) => void
}
```

### 7.2 WebSocket 驱动的状态更新流

```
后端 StageRunner 执行
    ↓ on_progress 回调
后端 ws.py broadcast_threadsafe()
    ↓ WebSocket
前端 onWSMessage(msg)
    ↓ 根据 msg.type
    ├── "stage_progress" → 更新 runningTasks + logs + 右侧面板进度
    ├── "stage_done" → 更新 stageData + patients 列表状态 + 触发 toast 通知
    ├── "patient_update" → 更新 patients 列表
    └── "log" → 追加到 logs + 右侧面板日志区
```

### 7.3 按需加载策略

- **病人列表**:启动时加载一次,之后靠 WebSocket 增量更新
- **阶段详情**:切换到某病人某阶段时才加载(`loadStageData`),加载后缓存
- **大文本**(合并文档):分段加载,前端虚拟滚动
- **图片**:缩略图按需请求(`/files/thumb/...`),全屏查看时请求原图

---

## 八、子工具抽离与集成方案

### 8.1 纯逻辑模块(直接被 FastAPI 调用,无需修改)

| mee 模块 | 封装到 | 改动 |
|----------|--------|------|
| `image_preprocess/processor.py` | `backend/tools/preprocess.py` | 无需改,直接 import |
| `image_slicer/slicer.py` | `backend/tools/slice.py` | 无需改 |
| `ocr_client.py` | `backend/tools/ocr.py` | 无需改 |
| `ocr_presets.py` | `backend/tools/ocr.py` | 无需改 |
| `markdown_converter/converter.py` | `backend/tools/merge.py` | 无需改 |
| `medical_extractor/engine.py` | `backend/tools/extract.py` | 无需改 |
| `cleanup/__init__.py` | `backend/tools/cleanup.py` | 无需改 |
| `payment_ocr/__init__.py` | `backend/tools/payment_ocr.py` | 无需改 |

### 8.2 PyQt5 可视化工具(保留为子进程)

| 工具 | 用途 | 集成方式 |
|------|------|---------|
| `image_slicer_qt5.py` | 鼠标框选切片区域 | Electron `preload.js` 加 IPC,前端调 `POST /tools/launch/image_slicer` → 后端 `subprocess.Popen` → 用户画框保存 `slice_config.json` → 前端轮询配置更新 |
| 遮罩工具(新建或复用 `image_mask_window.py`) | 鼠标框选遮罩区域 | 同上,保存 `mask_config.json` |

### 8.3 不再需要的组件

| 组件 | 原因 |
|------|------|
| `mee/main.py` | 被 Electron + React 替代 |
| `mee/views/*` | 被 React 组件替代 |
| `mee/controllers/pipeline_controller.py` | 被 `stage_runner.py` 替代 |
| `mee/controllers/app_launcher.py` | 被 `backend/routes/tools` 替代 |
| `mee/controllers/prompt_controller.py` | 保留但独立,不在工作台主流程中 |
| `mee/modules/medical_extractor/Medical_Excel_Agent_Pro.py` | 3366 行的独立 GUI,功能已被工作台覆盖;保留作为备用 |
| `mee/modules/ocr_batch/ocr_batch_gui.py` | 功能已被工作台 OCR 阶段覆盖 |
| `mee/modules/markdown_converter/merge_and_convert_gui.py` | 功能已被工作台合并阶段覆盖 |
| `mee/modules/file_extractor.py` | 功能已被工作台导入功能覆盖 |

### 8.4 保留 mee 的部分

| 保留 | 原因 |
|------|------|
| `mee/config/manager.py` | 配置管理 + keyring,antigravity 已在复用 |
| `mee/core/secrets.py` | 密钥存储 |
| `mee/resources/prompt_engineering/` | 提示词工程,独立功能,未来可集成 |
| `mee/modules/` 下的所有纯逻辑文件 | 被后端 tools 封装调用 |

---

## 九、关键交互流程(用户视角)

### 9.1 典型工作流:从导入到导出

```
1. 点击 [导入病人] → 选择父目录 → 自动扫描子文件夹 → 12 个病人录入
   → 左侧栏出现 12 张卡片,状态"待处理"

2. 点击"张三"卡片 → 中间区显示源图阶段 → 看到 12 张病历图片
   → 确认图片顺序正确(拖拽调整)

3. 点击阶段导航条的"预处理" → 右侧面板配置参数
   → 点击 [执行预处理] → 12 张图片逐张处理 → 对比视图查看效果
   → 如果效果不好,调整参数,点 [重新执行]

4. 跳到"OCR"阶段 → 点击 [执行OCR] 
   → 逐页卡片实时更新:○→⏳→✓
   → OCR 完成后逐页检查文本,发现第 3 页有错别字
   → 点击文本区域,直接修改,点 [保存修改]
   → 第 3 页标记"✏ 已编辑",合并阶段标记"stale"

5. 跳到"合并"阶段 → 查看连续文本 → 确认页序和内容
   → 搜索"旦白"→ 全部替换为"蛋白" → 保存

6. 跳到"抽取"阶段 → 点击 [执行抽取]
   → LLM 返回结构化字段 → 表单填充
   → 点击"高血压"字段 → 左侧源文自动滚动到"高血压病史8年余"并高亮
   → 检查字段值,修改"血沉"从 80 到 85(原文确实是 85)
   → 保存修改

7. 跳到"审核"阶段 → 逐字段审核 → 标记已审 → 添加备注

8. 选中所有已审核病人 → 跳到"导出" → 点击 [导出 Excel]
   → 下载结果.xlsx
```

### 9.2 批量操作流

```
1. 在左侧栏 Ctrl+点击选中 5 个"待处理"病人
2. 中间区显示批量视图(表格:5 行,每行一个病人的阶段状态)
3. 点击 [对所有选中执行 OCR]
4. 5 个病人依次执行 OCR,左侧栏卡片实时更新进度
5. 完成后,切换到单选模式逐个检查 OCR 质量
```

### 9.3 错误恢复流

```
1. "赵六"OCR 失败 → 卡片显示红色 + "Token未配置"
2. 点击"赵六" → 跳到 OCR 阶段 → 右侧面板显示错误详情
3. 在右侧面板填写 Token → 点击 [测试连接] → 成功
4. 点击 [重新执行] → OCR 重新跑
```

---

## 十、实现路线图(分 4 期)

### Phase 1: 基础框架(1-2 周)

**目标:四区布局 + 病人管理 + 源图查看 + OCR 基础**

后端:
- [ ] 重写 `patient.py`:加 per-stage 状态、state.json 结构
- [ ] 新建 `stage_runner.py`:单阶段执行引擎
- [ ] 新建 `routes/stages.py`:阶段执行 + 产物读取 API
- [ ] 增强 `ws.py`:增加 stage_progress / log 消息类型
- [ ] 封装 `tools/ocr.py`

前端:
- [ ] 四区根布局(`Workbench.tsx` → `TopBar` / `PatientSidebar` / `StageNav` + `StageContent` / `StagePanel`)
- [ ] `PatientSidebar`:病人列表 + 卡片 + 搜索 + 筛选 + 导入
- [ ] `StageNav`:水平阶段胶囊条
- [ ] `SourceStage`:图片网格 + Lightbox
- [ ] `OCRStage`:逐页卡片基础版(图片 + 文本,无编辑)
- [ ] `StagePanel`:OCR 设置 + 执行按钮 + 页面进度 + 日志
- [ ] Zustand store + WebSocket hook
- [ ] `api/client.ts`:完整 API 客户端

### Phase 2: 核心阶段(2-3 周)

**目标:OCR 编辑 + 合并 + 抽取完整功能**

后端:
- [ ] 封装 `tools/merge.py`、`tools/extract.py`
- [ ] 阶段产物读写 API(OCR page edit, merge text edit, extract fields edit)
- [ ] `routes/export.py`:导出 API

前端:
- [ ] `OCRStage`:增加行内编辑 + 单页重 OCR + 搜索 + HTML 表格渲染
- [ ] `MergeStage`:连续文本阅读器 + 行内编辑 + 页码导航 + 搜索 + LaTeX 渲染
- [ ] `ExtractStage`:分屏对照 + 字段表单 + 高亮联动 + 编辑追踪 + 验证提示
- [ ] `ExportStage`:导出预览 + 范围选择
- [ ] 批量操作视图(选中多人时)

### Phase 3: 交互增强(3-4 周)

**目标:预处理 + 切片 + 审核 + 可视化工具集成**

后端:
- [ ] 封装 `tools/preprocess.py`、`tools/slice.py`、`tools/cleanup.py`
- [ ] 子工具调起 API(`routes/tools.py`)
- [ ] Electron `preload.js` 加 IPC

前端:
- [ ] `PreprocessStage`:对比视图(并排/滑动/切换) + 参数调节
- [ ] `SliceStage`:区域预览 + 区域编辑入口
- [ ] `ReviewStage`:审核表单 + 备注 + 批量审核
- [ ] PyQt5 子工具调起(遮罩/切片)
- [ ] 错误处理与 toast 通知
- [ ] stale 标记 UI

### Phase 4: 打磨(4-5 周)

**目标:批量导出 + 性能优化 + 细节打磨**

- [ ] 虚拟滚动(大文本/长列表)
- [ ] 图片懒加载
- [ ] 病人状态统计仪表盘(TopBar 或独立页)
- [ ] 字段验证规则引擎(从模板 JSON 加载参考值范围)
- [ ] 导出字段选择
- [ ] 快捷键支持(J/K 翻页,E 编辑,Ctrl+S 保存)
- [ ] 暗色/亮色主题切换
- [ ] 多语言(中/英)
- [ ] Electron 打包

---

## 十一、技术选型补充

| 维度 | 选择 | 理由 |
|------|------|------|
| 前端框架 | React 18 + TypeScript | 已有基础 |
| 状态管理 | Zustand | 轻量,无需 Provider,适合中等复杂度 |
| 样式 | CSS Variables + glass.css | 已有玻璃态设计,扩展即可 |
| 图片查看 | react-zoom-pan-pinch | 缩放/平移 |
| 富文本编辑 | contentEditable + 自定义 | OCR 文本编辑不需要重型编辑器 |
| 表格渲染 | 自定义(HTML table) | 避免引入重型表格库 |
| 虚拟滚动 | @tanstack/react-virtual | 长列表性能 |
| 后端 | FastAPI | 已有基础 |
| WebSocket | FastAPI 原生 | 已有基础 |
| 配置/密钥 | mee ConfigManager + keyring | 复用 |
| OCR | PaddleOCR-VL API | 复用 |
| LLM | OpenAI 兼容 + Claude | 复用 engine.py |
| 桌面壳 | Electron | 已有基础 |

---

这个方案的核心思想是:**把"黑盒流水线"拆成"病人实例 × 可见可控的阶段"**,每个阶段都能独立执行、查看、编辑、重跑,病人作为一等公民贯穿全程。技术上在现有 antigravity 基础上演进,最大化复用 mee 已验证的纯逻辑模块。
