# Project Baseline — v0.1.0-alpha.8

## 产品目标

面向投标人员，对 2–5 份 Word/PDF 投标文件进行多维度比对校验，形成结构化问题证据、风险评分与可定位结果；后续由 HiAgent/飞书承担交互和呈现。

## 架构边界

### Codex 工程承担

- 文档解析与结构化
- 干扰去除
- 文本、图片和格式比对
- AI 疑似度辅助分析
- 统一风险评分
- Finding / Report JSON
- Word 反向定位与批注
- HTTP API
- 自动化测试与 Benchmark

### HiAgent 承担

- 用户文件入口
- 工作流编排
- 并行/串行节点调度
- 少量 LLM 复核和报告节点
- 飞书机器人发布、卡片和结果展示

## 当前已完成

`v0.1.0-alpha.8 = D0 + D1 + D2 + D3 + D4 + D5 + D6 + D7 + D8 + D9 + D10 Alpha`

```text
DOCX/PDF
  → DocumentIR（文本 + 图片特征 + 格式信息）
  → 干扰识别（exclude / downweight）
  → 文本候选召回 / 词法精排 / 干扰降权
  → 图片 SHA-256 / pHash / 颜色与宽高比辅助判断
  → 格式异常检查
  → AI 疑似度辅助分析（分数 + 置信度 + 信号 + 限制声明）
  → 统一风险评分（适用维度重归一化 + 贡献明细）
  → Finding / Comparison / Scoring JSON
  → DOCX 反向定位与原生批注副本 + Annotation JSON
  → FastAPI 版本化 HTTP 接口 / OpenAPI 文档
```

## 算法边界

- D3 是可解释词法基线，尚未接入 Embedding 语义精排。
- D6 pHash 适合相同、压缩、缩放和轻微修改图片；复杂裁剪/重绘待视觉 Embedding。
- D7 是启发式风格辅助信号，不是 AI 检测证明，必须人工复核。
- D8 当前格式维度使用格式异常风险，跨文档格式相似度仍是增强项。
- D8 对不适用维度重新归一化权重，文档集总风险取最高文档风险，同时保留平均分。
- D9 当前仅写回 DOCX；PDF Finding 可以参与检测和评分，但不在 Alpha 阶段直接写入 PDF。
- D9 依赖 Finding 中的正文段落或表格单元格 locator；无法可靠定位的项会记录跳过原因，不做猜测式批注。
- D10 API 默认单文件上限 50 MB、每次最多 5 份，只接受 DOCX/PDF；批注接口只接受 DOCX，并始终返回新文件。

## 当前验证

- `python -m compileall` 通过
- `pytest`：39/39 通过
- D3、D6、D7、D8、D9 输出及 D10 错误响应通过对应 JSON Schema 校验
- D9 输出包含有效 Word 原生批注 OOXML，并验证源文件哈希保持不变
- D10 的 8 个版本化业务接口、健康检查、OpenAPI 和输入边界通过集成测试

## 尚未完成

- D3 Embedding 语义精排（增强项）
- D6 视觉 Embedding 精排（增强项）
- D11 端到端 Benchmark
- H1–H4 HiAgent / 飞书配置
