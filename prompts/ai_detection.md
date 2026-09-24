# AI 疑似度复核 Prompt（D7 Alpha）

## 用途

本 Prompt 仅用于复核本地启发式引擎产生的高疑似段落，不用于直接判定文本是否由 AI 生成。

## 输入

- 文档与段落标识
- 原文及来源定位
- 本地启发式分数、置信度与各项风格信号
- 干扰项分类

## 输出约束

输出 JSON，至少包含：

- `assessment`: `insufficient_evidence` / `needs_review` / `style_consistent_with_ai_assistance`
- `confidence`: 0-1
- `reasons`: 可核验的语言特征列表
- `counter_evidence`: 支持人工写作或模板化文本的反证
- `requires_human_review`: 固定为 `true`

不得输出“确定由 AI 生成”等确定性结论。模板化招标语言、翻译文本和人工润色必须作为误判来源处理。
