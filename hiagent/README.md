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
- 聚合分析与本地确定性报告 → `/v1/analyze`
- 任务状态、调用者隔离和哈希链审计

HiAgent 接入阶段在这里逐步生成：

- 工作流节点映射
- API 调用示例
- 输入输出 JSON 示例
- Prompt 发布版本
- 飞书消息卡片 JSON
- 环境变量清单

当前已完成 H1–H4 本地接入包：

- `API_CONTRACT.md`：接口、字段、错误处理和安全边界
- `environment.example.env`：无密钥的环境变量模板
- `openapi.json`：可导入平台的运行时 OpenAPI 快照
- `scripts/export_openapi.py`：OpenAPI 快照导出工具
- `workflow.spec.json` / `WORKFLOW.md`：节点、变量、分支和隐私策略
- `prompts/report_generation.md`：可选 LLM 复核增强 Prompt
- `examples/report.example.json`：报告变量映射示例
- `feishu_card.template.json` / `FEISHU.md`：飞书卡片 2.0 模板与发布边界
- `ACCEPTANCE_CHECKLIST.md`：真实平台联调和发布门禁

“已完成”指上述资产已在本地通过契约测试；真实 HiAgent 工作流导入、机器人授权与飞书发送验收仍需平台测试环境。

## 推荐工作流边界

```text
上传文件
  ↓
/v1/analyze → 本地确定性报告 → 可选 /annotate-docx → 飞书卡片
```

D10 之前不要求在 HiAgent 中手工复制复杂 Python 代码。D7 的 AI 疑似度只作为辅助信号，HiAgent 展示时必须保留“需人工复核”和非确定性提示。
