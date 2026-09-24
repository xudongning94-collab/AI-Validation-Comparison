# HANDOFF TO CODEX

## 当前基线

- 当前版本：`v0.1.0-alpha.8`
- 已完成：D0–D10 Alpha
- 自动化测试：39/39 通过
- 架构原则：Codex 重开发、HiAgent 轻配置

本地工程由 `bid-compare-agent_v0.1.0-alpha.4.zip` 恢复。恢复包没有 `.git`，因此无法在当前环境核验原交接提交 `ac3ad5086c296a1560764ff98920a97b809368bb`；但恢复包版本、D0–D6 文档与 15 个原始测试一致。在此基础上完成 D7–D10，并将自动化测试扩充至 39 项。

## 已完成能力

- D0：工程基线
- D1：DocumentIR / Finding / Comparison Schema
- D2：DOCX/PDF Parser Alpha
- D3：文本查重 Alpha
- D4：格式检查 Alpha
- D5：干扰识别及文本查重降权
- D6：图片重复检测 Alpha
- D7：AI 疑似度辅助分析 Alpha
- D8：统一风险评分 Alpha
- D9：Word 反向定位与原生批注 Alpha
- D10：HTTP API Alpha

## 不可突破的约束

1. 核心解析、检测和评分逻辑必须保留在 Codex 工程中。
2. HiAgent 只承担文件入口、编排、少量 LLM 复核和展示。
3. Finding 必须携带可追踪的 `source_locator`。
4. 阈值、权重和风险等级必须配置化。
5. AI 疑似度必须标记为非确定性辅助信号，并要求人工复核。
6. 每阶段完成时更新 Schema、测试、README、基线和 CHANGELOG。

## D7 说明

- 方法：`stylometry-heuristic-alpha-v1`
- 信号：句长规则度、连接词密度、通用措辞、重复短语、标点规则度
- 干扰：标题/短文本排除，模板响应降权
- 输出：文档/段落分数、置信度、信号、Finding、限制声明
- Schema：`schemas/ai_likelihood.schema.json`
- CLI：`scripts/analyze_ai_likelihood.py`

## D8 说明

- 默认权重：文本 0.40、图片 0.20、AI 0.15、格式 0.25
- 缺失策略：不适用维度排除后重新归一化
- 汇总策略：文档集风险取最高文档风险，同时记录平均分
- 风险等级：minimal / low / medium / high / critical
- Schema：`schemas/scoring.schema.json`
- CLI：`scripts/score_documents.py`

## D9 说明

- 输入：DOCX 原文件 + Finding JSON
- 定位：正文段落索引、表格/行/单元格索引，支持对端 `peer_source_locator`
- 输出：不覆盖原文件的批注 DOCX + Annotation JSON
- 安全策略：最低严重度、最大批注数、重复项去重、不可定位项记录跳过原因
- 审计：记录源文件/输出文件 SHA-256、批注 ID、Finding ID 和完整定位信息
- Schema：`schemas/annotation.schema.json`
- CLI：`scripts/annotate_docx.py`

## D10 说明

- 框架：FastAPI + Uvicorn，API 版本为 `1.0.0`
- 路由：parse / preprocess / text-compare / image-compare / format-check / ai-check / score / annotate-docx
- 边界：单文件默认 50 MB、每次 1–5 或 2–5 份、仅允许 DOCX/PDF，批注只允许 DOCX
- 错误：统一 `{error: {code, message}}` 响应，并提供 `api_error.schema.json`
- 运行：`python scripts/run_api.py --host 127.0.0.1 --port 8000`
- 文档：启动后访问 `/docs` 或 `/openapi.json`

## 后续路线

1. D11：真实样本文档 Benchmark、误报/漏报和性能基线
2. H1–H4：HiAgent 工作流、飞书机器人与卡片展示

## 继续开发前检查

```powershell
.\.tools\python313\python.exe -m compileall -q src scripts tests
.\.tools\python313\python.exe -m pytest -q --basetemp .pytest-tmp
```
