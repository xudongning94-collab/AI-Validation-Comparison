# H4 — 飞书机器人与卡片接入

## 本地交付物

- `feishu_card.template.json`：飞书卡片 JSON 2.0 模板
- `schemas/feishu_card_template.schema.json`：模板结构校验
- `examples/report.example.json`：可用于变量映射演练的报告样例
- `ACCEPTANCE_CHECKLIST.md`：平台联调与发布门禁

## 变量映射

| 模板变量 | 来源/规则 |
|---|---|
| `task_id` | HiAgent 任务 ID，不使用文件名拼接 |
| `header_template` | minimal/low=`green`，medium=`orange`，high/critical=`red` |
| `risk_color` | minimal/low=`green`，medium=`orange`，high/critical=`red` |
| `risk_level_label` | 最低/低/中/高/严重 |
| `aggregate_score_100` | `report.scores.aggregate_score_100` |
| `document_count` | `report.documents` 数量 |
| `summary` | `report.summary`，发送前做 Markdown 转义 |
| `top_findings_markdown` | 最多 5 项，每项只含严重度、摘要和定位编号 |
| `recommended_actions_markdown` | 最多 5 项，不显示正文证据 |
| `report_url` | 受控的完整报告地址；没有地址时删除整个按钮列 |

模板变量替换后必须再次解析 JSON。不得通过字符串拼接把未转义的文件名、摘要或 URL 直接注入卡片。

## 发送方式

自定义机器人 Webhook 使用外层消息信封：

```json
{
  "msg_type": "interactive",
  "card": {}
}
```

其中 `card` 替换为渲染后的卡片对象。若使用应用机器人消息 API，则按该接口要求把卡片对象序列化到消息 `content`；两种发送方式不可混用。访问令牌或 Webhook 地址必须保存在 HiAgent 密钥管理中。

## 交互边界

Alpha 卡片只使用打开受控 URL 的按钮，不使用回调按钮，因此不需要在本项目中处理飞书卡片回调签名。以下动作仍由人工完成：

- 判断相似内容是否属于允许引用或统一模板。
- 判断格式异常是否影响投标有效性。
- 判断 AI 风格信号是否需要进一步复核。
- 确认批注文件和完整报告的接收人范围。

## 权限最小化

- 只向目标会话发送消息，不申请通讯录等无关权限。
- 报告 URL 应短时有效或要求再次鉴权。
- 卡片中不展示完整正文、内部文件路径、访问令牌和个人敏感信息。
- 群聊转发场景默认禁用；如业务确需转发，应先做脱敏和权限评估。

## 发布失败处理

1. 记录任务 ID、飞书请求 ID、HTTP 状态码和平台错误码。
2. 日志不记录 Webhook、令牌、完整卡片正文或原始 Findings。
3. 对限流和 5xx 使用平台建议的退避策略；对权限或参数错误不盲目重试。
4. 卡片失败不影响已生成的本地报告和批注文件，应提供安全的补发入口。

## 平台联调前仍需用户提供

- HiAgent 工作区及工作流编辑权限。
- 飞书自建应用或自定义机器人的可用测试环境。
- 目标测试群/测试用户，以及允许发送的内容范围。
- API 服务在该环境中的受控 HTTPS 地址和认证方式。

这些信息目前不是本地开发的阻塞项，但没有它们无法完成真实平台发布验收。
