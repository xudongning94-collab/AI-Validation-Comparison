# 投标文件多文档比对校验智能体（Codex 工程）

本仓库采用“**Codex 重开发、HiAgent 轻配置**”模式：核心解析、比对、评分、批注与 API 均在本工程中开发和测试；HiAgent 只负责文件入口、流程编排、少量模型节点、飞书发布与结果展示。

## 当前版本

**v0.1.0-alpha.8 — D10 HTTP API Alpha**

已完成：

- D0：工程基线与目录结构
- D1：统一中间数据模型 / JSON Schema
- D2：DOCX / PDF 解析器 Alpha
- D3：文本查重引擎 Alpha
- D4：格式检查 Alpha
- D5：干扰识别 Alpha，并正式接入文本查重
- D6：图片重复检测 Alpha
- D7：AI 疑似度辅助分析 Alpha
- D8：统一风险评分引擎 Alpha
- D9：Word 反向定位与原生批注 Alpha
- D10：HTTP API Alpha

## 当前核心能力

### 文本重复度

- 2–5 份文档两两比对
- 字符 n-gram 倒排候选召回
- TF-IDF、SequenceMatcher、containment 词法融合评分
- 干扰项 `exclude` / `downweight`
- 文档重复率、重复章节 Top 分布和原文定位
- 预留 `SemanticReranker` 接口，后续接入语义模型

### 图片重复度

- DOCX/PDF 图片 SHA-256、pHash、平均色、尺寸特征
- 字节完全一致与近似图片检测
- 通过平均色、宽高比进行轻量误报过滤
- 图片重复率、图片对和原文位置输出

### 格式与干扰

- 正文主流字体/字号统计和格式离群定位
- 页边距基础异常检查
- 标题、低信息短文本、招标响应/法定模板干扰识别

### AI 疑似度辅助分析

- 基于句长规则度、连接词密度、通用措辞、重复短语和标点规则度形成可解释信号
- 输出段落分数、置信度、触发信号与原文定位
- 标题和短文本排除，模板响应内容降权
- 所有结果固定标记 `non_diagnostic=true` 和 `requires_human_review=true`
- 明确限制：结果不能证明文本由 AI 生成

### 统一风险评分

- 默认权重：文本 40%、图片 20%、AI 疑似度 15%、格式 25%
- 不适用维度自动排除并重新归一化有效权重
- 输出每个维度的原始分、配置权重、有效权重、贡献和证据摘要
- 输出文档级风险与文档集最大风险，等级为 `minimal/low/medium/high/critical`
- AI 疑似度始终作为非确定性辅助维度

### Word 反向定位与批注

- 将 Finding 的 `source_locator` / `peer_source_locator` 映射回 DOCX 正文段落或表格单元格
- 生成 Word 原生批注，保留严重度、类型、Finding ID、分数和证据摘要
- 支持最低严重度、最大批注数、作者和证据长度配置
- 输出结构化批注结果、跳过原因和源/结果文件哈希
- 强制输出到新 DOCX，避免覆盖原始投标文件
- AI 疑似度批注固定附带“非确定性、必须人工复核”提示

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
```

仅解析：

```bash
python scripts/run_local.py A.docx -o output/
```

文本、图片和 AI 辅助分析：

```bash
python scripts/compare_texts.py A.docx B.docx -o output/text_compare.json
python scripts/compare_images.py A.docx B.docx -o output/image_compare.json
python scripts/analyze_ai_likelihood.py A.docx B.docx -o output/ai_likelihood.json
```

执行全部检测并生成统一评分：

```bash
python scripts/score_documents.py A.docx B.docx -o output/scoring.json
```

将检测结果中的 Finding 写回 Word 副本：

```bash
python scripts/annotate_docx.py A.docx findings.json -o output/A.annotated.docx --report output/annotation.json
```

启动本地 HTTP API：

```bash
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

交互式接口文档位于 `http://127.0.0.1:8000/docs`。版本化接口覆盖解析、预处理、文本/图片比对、格式检查、AI 辅助分析、统一评分与 DOCX 批注；上传文件默认限制为单文件 50 MB、单次最多 5 份。

## 目录

```text
configs/                 阈值和评分配置
prompts/                 HiAgent / LLM Prompt 版本基线
schemas/                 JSON Schema
src/bid_compare_agent/
  parser/                DOCX/PDF 解析
  preprocess/            干扰识别
  compare/               文本/图片相似度
  analysis/              AI 疑似度辅助分析
  check/                 格式检查
  scoring/               统一风险评分
  annotate/              Word 反向定位与原生批注
  api/                   FastAPI HTTP API 与流水线编排
  models/                中间数据模型
scripts/                 本地入口
tests/                   单元/集成测试
hiagent/                 HiAgent 适配资料
```

## 开发原则

1. HiAgent 不承载核心算法实现。
2. 所有节点输入输出使用可版本化 JSON Schema。
3. Finding 必须能映射回原文位置。
4. 阈值、权重和风险等级配置化。
5. 每一阶段先通过本地自动化测试，再接入 HiAgent。
6. 核心对象 ID 尽量内容寻址，便于缓存、重试和审计。
7. AI 疑似度不得作为确定性结论或唯一否决依据。

## 当前验证状态

- Python 3.13.15 `compileall` 通过
- `pytest`：**39/39 通过**
- 文本、图片、AI 疑似度、评分和批注结果均通过各自 JSON Schema 校验
- 批注 DOCX 可重新打开，并包含有效的 OOXML 原生评论部件和定位标记

## 下一阶段

- D11：本地端到端验收 / Benchmark
- H1–H4：HiAgent / 飞书轻配置接入
