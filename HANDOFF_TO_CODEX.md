# AI-Validation-Comparison — Work / Codex 续接说明

## 项目目标

开发“投标文件多文档比对校验智能体”。

总体原则：

- **Codex 重开发，HiAgent 轻配置**
- 核心解析、比对、评分、批注、API、测试全部在本仓库维护
- HiAgent 仅承担文件入口、流程编排、少量 LLM 节点、飞书发布与结果展示
- 所有核心节点使用版本化 JSON Schema
- 所有 Finding 必须可反向定位到原文
- 阈值、权重、风险规则必须配置化
- 每个开发阶段先通过本地测试，再接入 HiAgent

## GitHub

Repository:

`https://github.com/xudongning94-collab/AI-Validation-Comparison.git`

当前主分支：`main`

当前工程版本：

`v0.1.0-alpha.4`

本轮同步后的主线提交：

`efc074bde3dff43ef2b5646f0ac8385b2e3f5259`

后续又补充了完整同步文件与测试，继续开发时应以 **main 最新 HEAD** 为准，而不是以旧 ZIP 为准。

## 已完成阶段

### D0 工程基线
- 项目目录
- README / PROJECT_BASELINE / CHANGELOG
- pyproject / requirements
- 配置目录
- HiAgent 适配目录

### D1 数据协议
- DocumentIR
- Finding
- TextComparisonResult
- ImageComparisonResult
- Report Schema
- JSON Schema 校验

### D2 文档解析 Alpha
支持：
- DOCX
- PDF
- 段落
- 标题层级
- 表格
- 图片
- 字体 / 字号
- 页边距
- 页眉页脚
- source_locator
- 稳定 document_id / SHA-256

### D3 文本查重 Alpha
- 2–5 文档两两比对
- 中文 / 英文 / 数字标准化
- char n-gram 倒排召回
- TF-IDF + SequenceMatcher + containment 融合
- 高度重复 / 中度相似
- Finding 双向定位
- 重复率
- Top 章节
- SemanticReranker 扩展接口

### D4 格式检查 Alpha
- 正文主流字体 / 字号识别
- 格式离群检测
- 页边距基础异常

### D5 干扰识别 Alpha
- 标题排除
- 短文本排除
- 招标响应 / 法定模板识别
- exclude / downweight
- 已接入 D3 文本查重

### D6 图片重复检测 Alpha
- 图片 SHA-256
- pHash
- 汉明距离
- 平均 RGB
- 宽高比辅助过滤
- DOCX 图片尽量映射回正文段落
- PDF 图片定位
- 图片重复率
- 图片 Finding
- image_compare.schema.json

## 当前验证

本地开发快照验证：

- compileall 通过
- pytest：15/15 通过
- TextComparisonResult Schema 通过
- ImageComparisonResult Schema 通过

继续开发前建议第一步重新运行：

```bash
python -m compileall src scripts tests
pytest -q
```

如果 GitHub main 的测试结果与 15/15 不一致，优先排查同步遗漏，不要直接进入下一阶段。

## 下一阶段

### D7 — AI 疑似度辅助分析 Alpha

注意：禁止将结果设计为“AI 作者识别事实”。

统一使用：

- `ai_likelihood_score`
- “AI 疑似度”
- “仅供辅助判断”

建议实现：

1. 文本统计特征
   - 句长分布
   - 词汇多样性
   - 过渡词密度
   - 标点节奏
   - 段落结构一致性
2. LLM Judge 抽象接口
   - 默认可关闭
   - 后续可从 HiAgent 或 HTTP 模型服务调用
3. 每段输出 0–1 疑似度
4. 文档级加权汇总
5. 明确置信度与免责声明
6. 新增 ai_detection.schema.json
7. 新增单元和集成测试

### D8 — 统一评分引擎

整合：

- text_similarity
- image_similarity
- format_similarity / format risk
- ai_likelihood

要求：

- 权重来自 `configs/scoring.yaml`
- 不在代码里硬编码
- 输出维度分、总分、风险级别
- 保留原始指标与归一化过程
- 评分结果可解释
- 新增 scoring / report builder
- 新增 report.schema 扩展与测试

## 后续路线

D7 → D8 → D9 Word 批注 → D10 HTTP API → D11 本地端到端 Benchmark → H1-H4 HiAgent / 飞书

### D9 Word 批注
- 文本重复：高亮 + 批注
- AI 疑似：另一种高亮
- 格式问题：下划线 / 批注
- 图片重复：尽量定位相关段落 / 图位置
- 原文件另存，不破坏原件

### D10 HTTP API
预期接口：

```text
POST /parse
POST /preprocess
POST /text-compare
POST /image-compare
POST /format-check
POST /ai-check
POST /score
POST /annotate-docx
```

最终供 HiAgent 以 HTTP / 自定义插件方式调用。

## 关键技术约束

1. 不把大量 Python 代码复制进 HiAgent。
2. HiAgent 不成为代码唯一来源。
3. Prompt 文件必须保存在 repo 中。
4. Schema 是接口契约。
5. source_locator 是后续批注功能的基础，不得破坏。
6. 任何算法升级必须保留版本号或 algorithm metadata。
7. 不删除测试来让 CI 变绿。
8. 发现当前实现缺陷可以直接修，不留下明显技术债。
9. 优先工程完整性，不要反复只跑测试却不推进功能。
10. 每个阶段完成后更新 README、CHANGELOG、PROJECT_BASELINE。

## 推荐给 Codex 的首条任务

> 打开当前仓库 main 分支，先核验工程完整性并运行全部测试。确认 D0-D6 Alpha 状态与 HANDOFF_TO_CODEX.md 一致后，直接开发 D7 AI 疑似度辅助分析 Alpha。保持“Codex 重开发、HiAgent 轻配置”，新增配置、Schema、实现、CLI 和自动化测试；不要把 AI 检测描述为确定性 AI 作者识别。D7 完成且测试通过后更新 README、CHANGELOG、PROJECT_BASELINE，并提交到 GitHub。随后继续 D8 统一评分引擎。

## 推荐给 ChatGPT Work 的首条任务

> 接管 GitHub 仓库 AI-Validation-Comparison 的持续开发。先读取 HANDOFF_TO_CODEX.md、README.md、PROJECT_BASELINE.md、CHANGELOG.md，核验 main 分支当前代码和测试。然后按 D7 → D8 → D9 → D10 → D11 的路线持续执行，每完成一个阶段都运行测试、更新文档并提交 GitHub。HiAgent 只做轻配置，核心能力始终保留在仓库中。
