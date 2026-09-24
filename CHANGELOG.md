# Changelog

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
