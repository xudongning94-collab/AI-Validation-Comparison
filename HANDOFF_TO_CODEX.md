# HANDOFF TO CODEX

## 当前基线

- 当前版本：`v0.1.0-alpha.12`
- 已完成：D0–D12 Alpha + D13.1–D13.2 规则/候选检测 Alpha + H1–H4 本地接入包 Alpha
- 自动化测试：81/81 通过
- 架构原则：Codex 重开发、HiAgent 轻配置

本地工程由 `bid-compare-agent_v0.1.0-alpha.4.zip` 恢复。恢复包没有 `.git`，因此无法在当前环境核验原交接提交 `ac3ad5086c296a1560764ff98920a97b809368bb`；但恢复包版本、D0–D6 文档与 15 个原始测试一致。在此基础上完成 D7–D12、D13.1–D13.2 和 H1–H4 本地接入包，并将自动化测试扩充至 81 项。

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
- D11：隐私保护端到端 Benchmark Alpha
- D12：聚合分析、本地确定性报告、任务持久化、API Key 鉴权、哈希链审计与 OCR 证据契约基础
- D13.1–D13.2：签署规则、证据状态、合规 API 与 OpenCV 签字/印章候选检测
- H1：HiAgent API 契约与 OpenAPI 快照
- H2：工作流节点、分支、重试与隐私策略
- H3：结构化报告 Prompt、Schema 与示例
- H4：飞书卡片 JSON 2.0 模板与联调验收清单

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
- 路由：parse / preprocess / text-compare / image-compare / format-check / ai-check / signature-check / analyze / score / annotate-docx / tasks
- 边界：单文件默认 50 MB、每次 1–5 或 2–5 份、仅允许 DOCX/PDF，批注只允许 DOCX
- 错误：统一 `{error: {code, message}}` 响应，并提供 `api_error.schema.json`
- 运行：`python scripts/run_api.py --host 127.0.0.1 --port 8000`
- 文档：启动后访问 `/docs` 或 `/openapi.json`

## D13.1–D13.2 说明

- 规则：签字、签章、主体名称、签署人、日期、允许页码和位置锚点
- 接口：`POST /v1/signature-check`，输入文档、签署规则和可选 OCR/视觉页证据
- 视觉：独立 OpenCV worker 识别红/蓝印章和显式 ROI 内的签字墨迹候选
- 失败语义：worker 未运行/失败时标记证据不可用，不误判为漏签或漏章
- 边界：只能做存在性、一致性、位置和明显异常核对，不能鉴定签名或印章真伪
- 待办：DOCX/PDF 页面渲染、PaddleOCR worker、离线模型权重和真实样本 D13.3 校准

## D11 说明

- 输入：本地 manifest，明确 tender_reference / response_old / response_new / response 角色
- 差异：正文段落序列、表格内容、图片二进制与 pHash、DOCX 包部件
- 验收：版本关系阈值、阶段耗时、源文件运行前后 SHA-256 完整性
- 归因：统计新旧版本高相似段落中同时可追溯到招标文件的比例
- 隐私：报告强制不含正文，真实文件、本地 manifest 和运行结果不入库
- Schema：`schemas/benchmark.schema.json`
- CLI：`scripts/run_benchmark.py`
- 首组真实样本：3 份文件观测耗时 15.3–38.8 秒，706 组版本高相似段落中 114 组与招标文件来源相关

## H1–H4 说明

- API：`hiagent/API_CONTRACT.md`、`environment.example.env`、`openapi.json`
- 工作流：`hiagent/workflow.spec.json`、`WORKFLOW.md`、`schemas/hiagent_workflow.schema.json`
- 报告：`prompts/report_generation.md`、`schemas/report.schema.json`、报告示例
- 飞书：`hiagent/feishu_card.template.json`、`FEISHU.md`、`ACCEPTANCE_CHECKLIST.md`
- OpenAPI 导出：`scripts/export_openapi.py`
- 状态：本地接入资产已完成并测试；尚未在真实 HiAgent/飞书环境发布


## 后续路线

1. D13.3 使用真实签署页样本标注并校准误报/漏报
2. 完成页面渲染和 PaddleOCR 独立 worker，封装离线模型权重
3. 获取 HiAgent 工作区、飞书测试机器人、测试会话和受控 HTTPS API 地址
4. 扩充人工标注样本集，持续校准误报/漏报率

## 继续开发前检查

```powershell
.\.tools\python313\python.exe -m compileall -q src scripts tests
.\.tools\python313\python.exe -m pytest -q --basetemp .pytest-tmp
```
