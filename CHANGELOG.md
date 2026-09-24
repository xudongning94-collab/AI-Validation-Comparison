# Changelog

## 0.1.0-alpha.12 — D13.1–D13.2 签字签章合规检查 Alpha

- 新增确定性签署规则引擎，覆盖签字、签章、主体名称、签署人、日期、页码和位置锚点
- 新增 `/v1/signature-check`，接收版本化签署规则和可选 OCR/视觉页证据
- 区分“未发现签章”和“OCR/视觉证据不可用”，worker 失败时不生成伪缺失结论
- 新增 OpenCV 独立候选检测 worker，支持红/蓝印章及限定 ROI 内的签字墨迹候选
- 候选输出包含页码、坐标、置信度、质量标志、输入哈希、引擎状态和稳定 Schema
- 新增签署规则示例、合规结果 Schema、候选结果 Schema 及 HiAgent OpenAPI 契约
- 使用现有 Python 3.12/OpenCV 运行时完成合成签署页正向回归，识别出印章与签字候选
- 明确当前只核对存在性、一致性、位置和明显质量异常，不能鉴定签名或印章真伪
- DOCX 当前仅提供原生文本伪页证据；真实分页渲染、PaddleOCR 离线封装和真实样本阈值校准留待 D13.3
- 自动化测试由 68 项增加至 81 项

## 0.1.0-alpha.11 — D12 本地确定性闭环基础

- 新增 `/v1/analyze` 聚合分析接口，单次解析后完成文本、图片、格式、AI 辅助分析和统一评分
- 新增本地确定性报告生成器，不依赖 LLM，不复制正文，并固定保留人工复核与能力边界声明
- 新增 SQLite WAL 任务状态、不可变上下文、输入指纹、失败状态和进程重启中断恢复基础
- 新增 API Key 鉴权、调用者隔离和追加式哈希链审计；关闭鉴权时只允许本机回环地址
- 新增任务详情接口，返回任务状态、审计事件和审计链完整性结果
- HiAgent 主流程改为调用聚合接口，不再重复上传并解析五次；报告由本地确定性生成器提供
- 新增 PaddleOCR 兼容证据契约、OCR JSON Schema 和独立 Python 3.12 视觉 worker 依赖清单
- 明确 OCR/视觉结果只能作为可追溯证据，低置信度和 worker 失败必须进入人工复核
- 新增产品自闭环架构说明，覆盖上下文联动、持久化、鉴权、审计、失败恢复及签字签章路线
- 自动化测试由 51 项增加至 68 项

## 0.1.0-alpha.10 — H1–H4 本地接入包

- 新增 HiAgent API 接入契约、无密钥环境变量模板和可重复导出的 OpenAPI 快照
- 新增平台无关的 HiAgent 工作流规范，覆盖并行分析、Finding 汇总、重试、错误与隐私策略
- 强化结构化报告 JSON Schema，新增报告生成 Prompt、示例与禁止虚构/确定性结论约束
- 新增飞书卡片 JSON 2.0 模板、变量映射、权限边界及端到端验收清单
- 新增工作流、报告与卡片契约自动化测试，防止版本、路由和安全提示漂移
- 明确本地接入资产已完成，真实 HiAgent/飞书发布仍需平台权限、测试会话和受控 HTTPS API 地址
- 保持“Codex 重开发、HiAgent 轻配置”，不在平台工作流内复制核心算法
- 自动化测试由 42 项增加至 51 项，当前 51/51 通过

## 0.1.0-alpha.9 — D11

- 新增隐私保护的本地端到端 Benchmark runner、CLI、manifest 示例和结果 Schema
- 明确区分招标文件、旧版响应文件、新版响应文件和普通响应文件角色
- 新增段落序列、表格内容、图片二进制/pHash 和 DOCX 包部件差异分析
- 新增版本关系阈值验收、各阶段性能统计及源文件运行前后 SHA-256 完整性校验
- 新增招标文件来源归因，避免将标准响应内容直接解释为不同投标人之间的异常关联
- Benchmark 报告强制不含正文；真实样本、本地 manifest 和运行结果均不入库
- 首组 3 份真实样本 Benchmark 通过，识别出正文相同但媒体分辨率和 DOCX 包部件不同
- 自动化测试由 39 项增加至 42 项，当前 42/42 通过

## 0.1.0-alpha.8 — D10

- 新增 FastAPI HTTP API Alpha 与 Uvicorn 本地启动入口
- 暴露解析、预处理、文本/图片比对、格式检查、AI 辅助分析、统一评分和 DOCX 批注接口
- 核心能力通过 `ApiPipeline` 复用既有 D2–D9 实现，HiAgent 继续只承担轻量编排
- 上传文件采用分块落盘、文件名净化、类型/数量校验和单文件 50 MB 默认限制
- DOCX 批注接口返回原生 Word 文件，并通过响应头提供批注数量、跳过数量和输出哈希
- 新增统一 API 错误 Schema，覆盖框架字段校验、无效文档与业务输入错误
- 新增 OpenAPI、完整流水线、批注、上传边界和错误响应集成测试
- 自动化测试由 30 项增加至 39 项，当前 39/39 通过

## 0.1.0-alpha.7 — D9

- 新增 Word Finding 反向定位与原生批注 Alpha
- 支持正文段落、表格单元格及对端文档 `peer_source_locator` 定位
- 批注包含严重度、Finding 类型/ID、分数、证据摘要和关联文档
- AI 疑似度批注固定附带非确定性和人工复核提示
- 最低严重度、最大批注数、作者、缩写和证据长度配置化
- 强制输出到新 DOCX，保留源/输出 SHA-256，并结构化记录所有跳过原因
- 新增 `annotation.schema.json`、`annotate_docx.py` 和 `annotation.yaml`
- 新增 Word comments OOXML、Schema 和 CLI 端到端测试
- 自动化测试由 25 项增加至 30 项，当前 30/30 通过

## 0.1.0-alpha.6 — D7 / D8

- 新增 AI 疑似度辅助分析 Alpha：句长规则度、连接词密度、通用措辞、重复短语和标点规则度
- 输出段落级分数、置信度、可解释信号和原文定位
- 标题/短文本排除，模板响应降权
- 所有 AI 疑似度结果标记为非确定性并要求人工复核
- 新增 `ai_likelihood.schema.json`、`analyze_ai_likelihood.py` 和复核 Prompt
- 新增统一风险评分引擎：文本、图片、AI、格式四维贡献
- 不适用维度按策略排除并重新归一化有效权重
- 输出原始分、配置权重、有效权重、贡献、风险等级和关联 Finding ID
- 新增 `scoring.schema.json` 和 `score_documents.py`
- PDF 解析器迁移至当前 `pymupdf` 模块名，并增加解析回归测试
- 自动化测试由 15 项增加至 25 项，当前 25/25 通过

## 0.1.0-alpha.4 — D5 integration / D6

- 将 D5 干扰识别正式接入 D3 文本查重：`exclude` 项不参与正文重复率，`downweight` 项按配置系数降权
- 文本 Finding 新增原始相似度、干扰系数、双方干扰分类与动作元数据
- 新增图片特征提取：SHA-256、pHash、平均 RGB、尺寸
- DOCX 图片定位增强：尽量映射到正文段落索引，同时保留 relationship part
- PDF 图片提取补齐 SHA-256、pHash 与颜色特征
- 新增图片重复检测 Alpha：字节完全一致 + pHash 汉明距离 + 平均色 + 宽高比辅助过滤
- 新增图片重复率、图片对摘要、`image_compare.schema.json`
- 新增 `scripts/compare_images.py`
- 新增图片相似度、Schema、干扰降权自动化测试
- 当前自动化测试 15/15 通过

## 0.1.0-alpha.3 — D4/D5

- 新增格式检查 Alpha：正文主样式统计、字体/字号离群段落识别、左右页边距异常提示
- 新增干扰项识别 Alpha：标题、低信息短文本、招标响应/法定模板规则识别
- 干扰项输出 `exclude` / `downweight` 动作，为后续文本查重接入降权策略
- 新增 `scripts/check_document.py` 本地检查入口
- 新增格式检查与干扰识别自动化测试
- 当前自动化测试 10/10 通过

## 0.1.0-alpha.2 — D3

- 新增 2–5 文档文本两两比对
- 新增字符 n-gram 倒排候选召回，避免直接全量笛卡尔积
- 新增 TF-IDF / SequenceMatcher / containment 词法融合相似度
- 新增高度重复 / 中度相似 Finding 输出
- 新增按唯一重复段落字符数计算的重复率
- 新增重复章节 Top 聚合
- 新增 `SemanticReranker` 接口，为 Embedding 精排预留稳定边界
- 新增 `text_compare.schema.json`
- Document ID / Finding ID 改为稳定哈希派生，便于缓存与审计
- 新增文本比对 CLI、Schema 校验与集成测试

## 0.1.0-alpha.1 — D0/D1/D2

- 创建工程基线与目录结构
- 建立 DocumentIR / Finding / Report 三类 Schema
- 实现 DOCX Parser Alpha
- 实现 PDF Parser Alpha
- 增加统一 Dispatcher 与本地 CLI
- 增加基础测试
- 固化 HiAgent 轻配置边界
