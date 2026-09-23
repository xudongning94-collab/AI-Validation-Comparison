# 投标文件多文档比对校验智能体（Codex 工程）

本仓库采用“**Codex 重开发、HiAgent 轻配置**”模式：核心解析、比对、评分、批注与 API 均在本工程中开发和测试；HiAgent 只负责文件入口、流程编排、模型节点、飞书发布与结果展示。

## 当前版本

**v0.1.0-alpha.3 — D4/D5 格式检查 + 干扰识别 Alpha**

已完成：
- D0：工程基线与目录结构
- D1：统一中间数据模型 / JSON Schema
- D2：DOCX / PDF 解析器 Alpha
- D3：文本查重引擎 Alpha
- D4：格式检查 Alpha
- D5：干扰识别 Alpha

### D3 Alpha 能力

- 2-5 份文档两两比对
- 中文/英文/数字统一文本标准化
- 字符 2-gram 倒排索引进行候选召回，避免全量段落笛卡尔积
- 字符 2-4 gram TF-IDF + SequenceMatcher + containment 的可解释词法评分
- 预留 `SemanticReranker` 接口，后续可接 Embedding 服务做语义精排
- `>= 0.85` 高度重复、`0.60-0.85` 中度相似，阈值配置化
- Finding 保留双方文档、章节、段落 ID、原文、原始位置定位
- 按“高度重复段落去重后的字符数 / 可比正文字符数”统计文档重复率
- 输出重复章节 Top 分布
- 结果通过 `schemas/text_compare.schema.json` 校验
- 文档 ID 与 Finding ID 均采用内容哈希派生，支持稳定缓存和结果追踪

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .[dev]
```

仅解析：

```bash
python scripts/run_local.py A.docx -o output/
```

文本查重：

```bash
python scripts/compare_texts.py A.docx B.docx C.docx -o output/text_compare.json
```

结果示例包含：

```json
{
  "compare_type": "text_similarity",
  "pair_summaries": [],
  "findings": [
    {
      "type": "text_similarity",
      "severity": "high",
      "score": 0.93,
      "evidence": {
        "source_section": "技术方案 / 总体架构",
        "peer_section": "技术方案 / 系统架构",
        "source_text": "...",
        "peer_text": "..."
      }
    }
  ]
}
```

## 目录

```text
configs/                 配置与阈值
prompts/                 后续 HiAgent / LLM Prompt
schemas/                 JSON Schema
src/bid_compare_agent/
  parser/                DOCX/PDF 解析
  compare/               文本/后续图片相似度算法
  models/                中间数据模型
  utils/                 通用工具
scripts/                 本地入口
tests/                   单元/集成测试
hiagent/                 HiAgent 适配资料
```

## 开发原则

1. HiAgent 不承载核心算法实现。
2. 所有节点输入输出均使用可版本化 JSON Schema。
3. 原文位置必须可追踪，后续任何 Finding 都能映射回文档。
4. 阈值与评分规则配置化，不硬编码在工作流中。
5. 每一阶段必须先通过本地自动化测试，再接入 HiAgent。
6. 核心对象 ID 尽量内容寻址，便于缓存、重试与审计。

## D4/D5 Alpha 能力

- 统计正文主流字体/字号，并定位格式离群段落
- 页边距基础异常检查
- 识别标题、低信息短文本、招标响应/法定模板类干扰项
- 对干扰项给出 `exclude` / `downweight` 动作，下一轮接入文本查重评分链路

本地检查：

```bash
python scripts/check_document.py A.docx -o output/document_check.json
```

## 下一阶段

**D6：图片重复检测 Alpha**，并同时把 D5 干扰项动作正式接入 D3 文本比对。

随后进入：
- D6 图片重复检测
- D7 AI 疑似度辅助分析
- D8 统一评分
- D9 Word 批注
- D10 HTTP API
- D11 本地端到端验收
- H1-H4 HiAgent / 飞书轻配置接入
