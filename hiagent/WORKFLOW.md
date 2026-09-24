# H2 — HiAgent 工作流映射

机器可读基线为 `workflow.spec.json`；本文件说明在 HiAgent 页面中的配置顺序和运行策略。

## 主流程

```text
上传 2–5 份文件
  → 本地规则校验
  → API 健康检查
  → 调用 /v1/analyze（单次解析、聚合 Findings/评分、本地确定性报告）
  → 是否需要 Word 批注？
      ├─ 是：逐份 DOCX 调用 annotate-docx
      └─ 否：跳过
  → 渲染飞书卡片
```

## 为什么采用聚合节点

`/v1/analyze` 在服务端只解析一次文件，并统一完成去重、评分、确定性报告、任务落库和审计。分项接口仍保留用于诊断；HiAgent 主流程不再重复上传和解析五次，也不依赖 LLM 才能生成报告。

## 变量映射

| 工作流变量 | 来源 | 用途 |
|---|---|---|
| `uploaded_files` | 上传节点 | `/v1/analyze` 的重复 `files` 字段 |
| `analysis_result.result.findings` | `/v1/analyze` | 已按 Finding ID 去重的全部证据 |
| `analysis_result.result.results.scoring` | `/v1/analyze` | 风险级别、总分与维度贡献 |
| `analysis_result.result.report` | `/v1/analyze` | 本地确定性报告 |
| `analysis_result.result.task` | `/v1/analyze` | 任务 ID 与请求指纹 |

服务端汇总 Finding 时以 `finding_id` 去重，并原样保留定位和关联文档字段。

## 失败分支

- 文件数量、大小、后缀错误：立即结束，不调用 API。
- HTTP 400/413/415/422：视为输入错误，不自动重试。
- 超时或 HTTP 5xx：递增退避，最多尝试 2 次。
- 聚合分析失败：不生成“成功报告”；服务端保存失败状态和审计事件。
- 单份 Word 批注失败：其余报告仍可发布，但卡片必须列出失败文件。

## 日志与隐私

普通运行日志只记录任务 ID、接口、状态码、耗时、文件数量、文件哈希和结果计数。不得记录正文、完整 Findings、二进制文件或访问令牌。临时文件由 API 请求结束时清理；HiAgent 侧也不应长期保留上传件。

## 人工确认点

- AI 疑似度始终是非诊断性辅助信号。
- 高风险不等同于违规结论。
- 对外发送报告或批注文件前，由投标人员确认接收范围。
