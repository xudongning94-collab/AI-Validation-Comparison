# HiAgent 适配目录

原则：**HiAgent 仅做轻配置，核心业务代码不写死在工作流中。**

当前 Codex 工程已具备：

- DOCX/PDF → `DocumentIR`
- 多文档文本重复度 Alpha → `TextComparisonResult`
- 多文档图片重复度 Alpha → `ImageComparisonResult`
- 格式检查与干扰识别 Alpha
- AI 疑似度辅助分析 Alpha → `AILikelihoodResult`
- 统一风险评分 Alpha → `UnifiedScoringResult`
- Finding 中保留原文 `source_locator` / `peer_source_locator`

后续 HiAgent 接入时，这里会逐步生成：

- 工作流节点映射
- API 调用示例
- 输入输出 JSON 示例
- Prompt 发布版本
- 飞书消息卡片 JSON
- 环境变量清单

## 推荐工作流边界

```text
上传文件
  ↓
/parse
  ↓
/preprocess
  ↓
/text-compare ─┐
/image-compare ├→ /score → LLM 报告节点 → /annotate-docx → 飞书卡片
/format-check ─┤
/ai-check ─────┘
```

D10 之前不要求在 HiAgent 中手工复制复杂 Python 代码。D7 的 AI 疑似度只作为辅助信号，HiAgent 展示时必须保留“需人工复核”和非确定性提示。
