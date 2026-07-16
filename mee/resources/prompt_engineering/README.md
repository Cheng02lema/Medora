# PromptForge for IgG4-style Prompt Engineering

该工具把 Excel 模版中的字段列表自动转换为结构化的提示词工程文档（Markdown），并支持对接多种主流大模型 API 进行字段规则的自动扩充。

## 核心能力

- **Excel→提示词工程**：读取工作簿中的字段，按照既定模板渲染成《IgG4相关疾病电子病历数据提取规范》风格的说明文档。
- **字段规则引擎**：`config/auto_rules.yaml` 内置了 52 个字段的同义词、规则、示例，可根据字段名称自动填充，也可自行新增/覆写。
- **LLM 扩展**：可选用 `openai`、`azure`、`dashscope`（或 `offline`）等 provider，给每个字段生成更细致的说明，提升可移植性。
- **模板系统**：使用 Jinja2 渲染，`templates/prompt.md.jinja` 可自由调整整体结构、样式，满足其他科室/疾病的需求。

## 快速开始

```bash
# 1. 生成提示词规范（默认使用内置规则，不调用LLM）
python -m promptforge.cli \
  --excel Igg4模版.xlsx \
  --output generated/IgG4_auto.md \
  --auto-rules config/auto_rules.yaml \
  --blueprint config/prompt_blueprint.yaml \
  --template promptforge/templates/prompt.md.jinja \
  --dry-run
```

运行结束后，在 `generated/IgG4_auto.md` 中即可看到完整文档。

### 启用 LLM 自动写作

```bash
export OPENAI_API_KEY=sk-xxxxx
python -m promptforge.cli \
  --excel Igg4模版.xlsx \
  --llm-provider openai \
  --model gpt-4o-mini \
  --temperature 0.15 \
  --output generated/IgG4_llm.md
```

常见 provider 参数：

| Provider | 说明 | 需要的额外参数 |
|----------|------|----------------|
| `openai` | OpenAI API 兼容接口 | `--api-key` 或环境变量 `OPENAI_API_KEY`；可选 `--base-url` |
| `azure`  | Azure OpenAI | `--api-key`、`--base-url`、`--deployment`、`--api-version` 或对应环境变量 |
| `dashscope` | 阿里云通义千问 | `DASHSCOPE_API_KEY` 环境变量 |
| `offline` | 本地/调试模式 | 不调用网络，直接返回空 JSON |

> **提示**：`config/prompt_blueprint.yaml` 中的 `llm.user_template` 控制了发送给大模型的提示，可根据任务改写。

## Excel 模版要求

- 默认读取首个 sheet，可通过 `--sheet Sheet1` 指定。
- 支持两种格式：
  1. **表格模式**：首行包含列名（字段、分类、类型、同义词、规则、单位、示例......），后续每行描述一个字段。
  2. **宽表模式**：只有表头（如 `Igg4模版.xlsx`），每一列即一个字段，名称会作为字段 ID。
- 如果 Excel 中提供了更详细的描述/同义词/规则，将覆盖 `auto_rules` 的默认值。

## 配置文件说明

- `config/auto_rules.yaml`：
  - `defaults`：全局默认类型、同义词分隔符、兜底规则文本。
  - `exact_fields`：根据字段名准确匹配的配置，本仓库已经从示例 markdown 自动抽取了 52 条。
  - `patterns`：模糊匹配策略，可按需新增（如匹配所有“*报告”字段）。
- `config/prompt_blueprint.yaml`：
  - `project`：文档标题、版本、简介。
  - `categories`：每个大章节的标题、排序、附加说明。
  - `llm`：调用大模型时的 system prompt 与 user prompt 模板。
- `promptforge/templates/*.jinja`：
  - `prompt.md.jinja`：整份文档的骨架。
  - `variable_block.md.jinja`：单个字段的渲染片段，可在此微调展示格式。

## 典型扩展方式

1. **新增疾病/业务场景**：在 Excel 中维护新的字段表头，同时在 `auto_rules.yaml` 添加或修改对应条目。
2. **换用其他 LLM**：在 `promptforge/llm_providers.py` 中新增 provider 类，然后通过 `--llm-provider custom` 使用。
3. **改写输出模板**：复制 `prompt.md.jinja` 并修改段落/表格结构，再在命令行通过 `--template` 指向新的模板。
4. **混合模式**：先用 `--dry-run` 生成骨架，然后针对缺少定义的字段使用 `--llm-provider` 再运行，或者手工补完。

## 开发提示

- 所有代码只依赖 Python 标准库 + `PyYAML` + `Jinja2`，无需额外安装 Excel 读写库。
- 新增字段时，可使用 `tools/extract_from_md.py`、`tools/build_auto_rules.py` 从已有 markdown 中反向生成 `auto_rules`。
- 建议将生成的 Markdown 纳入版本管理，便于多疾病、多模型、多阶段的提示词工程对比。
