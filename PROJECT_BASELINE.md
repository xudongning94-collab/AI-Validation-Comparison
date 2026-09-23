# Project Baseline — v0.1

## 产品目标

面向投标人员，对指定多份 Word/PDF 投标文件进行多维度比对校验，形成结构化问题证据、风险评分与可定位结果；后续由 HiAgent/飞书承担交互和呈现。

## 架构边界

### Codex 工程承担
- 文档解析与结构化
- 干扰去除
- 文本/图片/格式比对
- AI 疑似度辅助分析接口
- 评分
- Finding/Report JSON
- Word 反向定位与批注
- HTTP API
- 自动化测试与 Benchmark

### HiAgent 承担
- 用户文件入口
- 工作流编排
- 并行/串行节点调度
- 少量 LLM 节点
- 飞书机器人发布
- 卡片与结果展示

## 当前版本目标

`v0.1.0-alpha.4 = D0 + D1 + D2 + D3 + D4 + D5 + D6 Alpha`

当前可验收链路：

```text
DOCX/PDF
  → DocumentIR（文本 + 图片特征 + 格式信息）
  → 干扰识别（exclude / downweight）
  → 文本候选召回 / 词法精排 / 干扰降权
  → 图片 SHA-256 / pHash / 颜色与宽高比辅助判断
  → 文本与图片 Finding
  → 文档重复率 / 图片重复率 / 章节分布 JSON
```

## 当前算法边界

D3 Alpha 已完成可解释词法基线，但暂不把它冒充为“语义查重最终版”。
`SemanticReranker` 已冻结接口，后续可接 Embedding 模型，对“改写但语义相同”的段落进行精排。

D6 当前为 pHash Alpha：适合检测完全相同、压缩、缩放及轻微修改图片；对大幅裁剪、重绘、元素重排等复杂视觉变形，后续需接视觉 Embedding 精排。

## 当前新增能力

- D4 格式检测 Alpha：正文主样式与格式离群提示
- D5 干扰识别 Alpha：标题/短文本/标准响应规则；并已接入文本比对
- D6 图片重复检测 Alpha：SHA-256 + pHash + 平均色 + 宽高比过滤

## 尚未完成

- D6 视觉 Embedding 精排（增强项）
- D7 AI 疑似度
- D8 综合评分
- D9 Word 批注
- D10 HTTP API
- D11 端到端 Benchmark
- H1-H4 HiAgent / 飞书配置
