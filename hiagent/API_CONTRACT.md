# H1 — HiAgent API 接入契约

## 目标与边界

HiAgent 只负责上传入口、HTTP 节点编排和结果展示。解析、比对、检测、评分、本地确定性报告与 Word 批注均由 `bid-compare-agent` API 完成；LLM 只允许作为可选复核增强。

本契约对应：

- 应用版本：`0.1.0-alpha.12`
- API 版本：`1.0.0`
- OpenAPI 快照：`hiagent/openapi.json`
- 默认服务地址：`${BID_COMPARE_API_BASE_URL}`

## 通用约定

- `/health` 和任务详情使用 `GET`；其余业务接口使用 `POST multipart/form-data`。
- 文件字段名必须是 `file` 或 `files`，不能改成平台默认的 `upload`。
- 多文件接口通过重复的 `files` 字段上传 1–5 或 2–5 份文件。
- 支持 `.docx`、`.pdf`；单文件默认不超过 50 MB。
- JSON 接口成功响应统一为 `{api_version, operation, result}`。
- JSON 接口失败响应统一为 `{error: {code, message}}`。
- `/v1/annotate-docx` 成功时返回 DOCX 二进制，不使用 JSON 成功信封。
- `/v1/signature-check` 的 `requirements_json` 必填，`evidence_json` 可选；视觉证据缺失时返回待复核而不是伪造漏签结论。
- 签字签章结果只用于合规辅助核对，不能鉴定签名或印章真伪。

## 节点清单

| 节点 | 方法与路径 | 上传字段 | 数量 | 成功结果 |
|---|---|---:|---:|---|
| 健康检查 | `GET /health` | — | — | 服务/API 版本 |
| 文档解析 | `POST /v1/parse` | `file` | 1 | `DocumentIR` |
| 预处理 | `POST /v1/preprocess` | `file` | 1 | 文档与干扰项 |
| 文本比对 | `POST /v1/text-compare` | `files` | 2–5 | 文本重复关系 |
| 图片比对 | `POST /v1/image-compare` | `files` | 2–5 | 图片重复关系 |
| 格式检查 | `POST /v1/format-check` | `files` | 1–5 | 格式 Findings |
| AI 辅助分析 | `POST /v1/ai-check` | `files` | 1–5 | 疑似度、置信度与限制声明 |
| 统一评分 | `POST /v1/score` | `files` | 2–5 | 文档集风险与贡献明细 |
| 聚合分析 | `POST /v1/analyze` | `files` | 2–5 | Findings、评分、确定性报告与任务编号 |
| 签字签章合规 | `POST /v1/signature-check` | `file`, `requirements_json`, `evidence_json` | 1 | 签署规则结果与可定位 Finding |
| Word 批注 | `POST /v1/annotate-docx` | `file`, `findings_json` | 1 | 新 DOCX 文件 |
| 任务详情 | `GET /v1/tasks/{task_id}` | — | — | 状态、审计事件与审计链校验 |

## 最小调用样例

健康检查：

```bash
curl "${BID_COMPARE_API_BASE_URL}/health"
```

聚合分析（HiAgent 主流程节点）：

```bash
curl -X POST "${BID_COMPARE_API_BASE_URL}/v1/analyze" \
  -F "files=@response-a.docx" \
  -F "files=@response-b.docx"
```

生成 Word 批注副本：

```bash
curl -X POST "${BID_COMPARE_API_BASE_URL}/v1/annotate-docx" \
  -F "file=@response-a.docx" \
  -F 'findings_json={"findings":[]}' \
  --output response-a.annotated.docx
```

批注响应头提供 `X-Annotation-Count`、`X-Skipped-Count` 和 `X-Output-SHA256`，工作流应将它们写入运行日志。

## HiAgent HTTP 节点配置规则

1. 启动时先调用 `/health`，`status` 必须为 `ok`，`api_version` 必须为 `1.0.0`。
2. 文件数量、扩展名和大小在进入分析节点前校验，避免无效任务占用 API 资源。
3. `413`、`415`、`422` 属于输入问题，直接向用户展示安全化错误信息，不自动重试。
4. 网络超时和 `5xx` 最多重试 2 次，使用递增退避；不得重复提交已成功的批注下载节点。
5. 不把文件正文、完整 Finding 证据或访问令牌写入普通工作流日志。
6. `ai-check` 结果必须显示“辅助信号、需人工复核”，不得改写为 AI 生成判定。

## 部署安全

API 已支持 `BID_COMPARE_AUTH_MODE=api_key` 和 `BID_COMPARE_API_KEYS`；关闭鉴权时启动器只允许绑定回环地址。跨主机接入必须同时启用 API Key、HTTPS、请求大小限制和访问审计。密钥写入 HiAgent 密钥管理，不进入配置文件、Prompt、日志或 Git。

## 快照更新

API 路由变化后执行：

```powershell
.\.tools\python313\python.exe scripts\export_openapi.py
```

随后运行测试，确认 `hiagent/openapi.json` 与运行时 OpenAPI 完全一致。
