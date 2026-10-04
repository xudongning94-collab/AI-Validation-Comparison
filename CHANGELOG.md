# Changelog

## Unreleased — D13.3 签字签章候选校准基础设施

- 新增隐私安全的人工审核契约、3 个 Schema、审核包生成器、静态本地审核页和完整性审计 CLI：印章召回率真值必须先完成全页漏检审核，签字必须依次判断字段存在与手写存在；新增 9 项测试，自动化测试由 129 项增加至 138 项
- 生成 Git 忽略的秣陵 342 页全页漏章审核包和广州 7 字段二阶段签字审核包；初始审计分别为 0/342、0/7，状态保持 `incomplete`，等待人工导出后冻结真值
- 修复签字页筛选把页面级宽泛关键词误当成手写签名证据的问题：新增保留 OCR 几何的局部语义签字字段定位器、配置、Schema、CLI 和 6 项测试，并将“字段存在”与“手写墨迹存在”拆分；秣陵旧版 25 页候选重扫后只保留第 8 页，该页字段存在但手写缺失
- 导入秣陵人工审核：189 个印章候选标注为 129 个真印章、60 个误报；24 个已审核旧版签名页全部无手写。印章审核未逐页标记漏检，只作为候选精确率证据，不报告召回率
- 新增两组独立真实 PDF 验证素材预检：共 393 页全部完成隐私保护渲染与候选扫描，累计 504 个印章候选（214 个达到当前 0.75 阈值）；广州组含视觉确认的手写候选页面，仍需二阶段人工审核后冻结
- 页面渲染 Schema 升级至 v1.1，新增 `--canonical-pdf`：以规范化 64 字符分片做双向同源校验，通过门槛后使用权威 PDF 分页并记录双源 SHA-256、匹配率和显式 warning；不同源 PDF 失败且不发布页面
- 真实 WPS DOCX/PDF 配对回归确认 LibreOffice 261 页对权威 PDF 204 页的分页不兼容；新回退在真实文件上以 0.76/0.76 双向匹配通过 0.7 门槛并输出 204 页，新增 2 项集成测试，自动化测试由 121 项增加至 123 项
- 恢复契约升级为 repository-checkpoint v2：不再把历史 Codex 线程 ID 当作恢复入口，新增逻辑检查点 ID、权威来源校验，并在恢复摘要中输出完整完成范围和下一步动作，避免侧边栏索引与旧线程正文不一致时误恢复旧进度
- 校准 manifest 升级至 v1.1：每个样本必须声明 `document_group_id`，同一源文档及派生页禁止跨 calibration/validation，报告增加文档组计数
- OpenCV 候选 worker 改为字节读取和内存解码，修复 Windows 中文绝对路径图片无法读取的问题
- 完成首个 Git 忽略的真实单文档 calibration-only 运行：21 页、16 个印章真值、10 个负/困难样本页；结果暴露碎片化印章漏检和非印章彩色元素误报，未达到 0.85 最低召回率
- 新增 3 项文档组防泄漏与 Unicode 路径回归测试，自动化测试由 114 项增加至 117 项
- 新增同色近邻印章组件聚类、聚类前细长边框/彩条过滤及 3 项回归测试；单文档 calibration 在阈值 0.75 的召回由 0.50 提升至 0.875，但精确率仍仅 0.203，自动化测试由 117 项增加至 120 项
- 聚类候选新增可配置的相对页面尺度置信度因子，配置由 `vision_worker.yaml` 经客户端传入隔离子进程；保留低阈值候选并抑制过小图标与超大彩色版块，同一单文档 calibration 在阈值 0.75 下保持 TP=14、FN=2，FP 从 55 降至 23，精确率由 0.203 提升至 0.378，F1 由 0.329 提升至 0.528，负样本页误报率由 0.60 降至 0.30；新增 1 项回归测试，自动化测试由 120 项增加至 121 项
- 新增严格的目录级离线模型 manifest v2：拒绝越界、符号链接和未声明文件，并逐文件校验 SHA-256
- 新增 `scripts/build_vision_model_manifest.py` 与必须显式传入 `--allow-network` 的官方模型暂存脚本；生产 worker 不执行隐式下载
- 新增实际 `run_paddleocr.py` 隔离子进程、原始输出 Schema 与 `VisionWorkerClient.ocr_page()`，强制关闭三个额外模型模块并保留低置信度人工复核
- 新增 7 项模型目录、worker、暂存门禁与客户端集成测试，自动化测试由 104 项增加至 111 项
- 官方 PP-OCRv5 server 检测/识别模型已显式暂存并通过完整健康检查；真实中文合成页由 worker 与客户端端到端识别 2 行文字，置信度均约 0.997
- 修复模型暂存目录的 Windows ACL 继承、Paddle 3.3.1 oneDNN/PIR 不兼容、Unicode 绝对模型路径和 NumPy 多边形后处理问题
- 新增 3 项暂存发布、缺失父目录和 ASCII 路径回归测试，自动化测试由 111 项增加至 114 项
- 新增 `requirements-vision-candidates.txt` 与 `scripts/bootstrap_vision_worker.ps1`，分离候选检测/完整 OCR 依赖并支持显式联网或 `--no-index` wheelhouse 安装
- 本机隔离 Python 3.12.10 已安装固定 CV/OCR 依赖；`pip check`、真实模块导入与合成签字/印章候选子进程回归通过
- 固定 Windows 运行时可导入的 `ujson==5.11.0`，避免 PaddleX 因 `ujson 6.0.0` DLL load failure 降级
- DOCX renderer 新增环境变量和 Windows 标准 LibreOffice 路径发现，合成两页 DOCX 已真实渲染为 2 张 PNG
- LibreOffice 子进程输出固定 UTF-8 安全解码，避免 Windows 默认 GBK 触发后台 `UnicodeDecodeError`
- 新增 5 项 bootstrap/依赖拆分/renderer 发现与解码契约测试，自动化测试由 99 项增加至 104 项
- 新增隔离视觉 worker 健康检查，核验 Python 3.12、OpenCV、NumPy、PaddleOCR 与 PaddlePaddle 能力
- 新增 `VisionWorkerClient` 子进程边界、超时、无效输出处理与隐私安全的 unavailable/failed 降级
- 校准 CLI 改为读取 `configs/vision_worker.yaml` 和 `BID_COMPARE_VISION_PYTHON`，禁止把 OpenCV worker 导入主 Python
- 新增离线模型 manifest、相对路径限制和 SHA-256 完整性门禁；OCR 仅在依赖与模型同时就绪时可用
- 新增 `scripts/check_vision_worker.py`、健康 Schema 及 7 项运行时/模型契约测试，自动化测试由 92 项增加至 99 项
- 新增 PyMuPDF PDF 逐页 RGB PNG 渲染、哈希命名、源文件完整性复核和隐私保护结果 Schema
- 新增隔离 LibreOffice 用户配置的 DOCX 临时 PDF 转换契约、超时与明确的 `unavailable`/`failed` 状态
- 新增 `scripts/render_document_pages.py`、`configs/page_rendering.yaml` 及 PDF/DOCX 页面渲染集成测试
- 页面渲染测试使自动化测试由 89 项增加至 92 项
- 新增 `PROJECT_STATE.json` 单一机器状态源、仓库级 `AGENTS.md`、恢复脚本和状态一致性检查
- 新增父目录恢复定位入口，避免把容器目录的空 Git 仓库误认为产品仓库
- 新增仓库目录/父目录双入口恢复契约测试，自动化测试由 87 项增加至 89 项
- 新增隐私保护的本地签署页标注 manifest、calibration/validation 数据切分和示例
- 新增签字/印章候选 IoU 一一匹配、置信度阈值扫描与召回率下限约束的 F1 阈值选择
- 新增 TP/FP/FN、精确率、召回率、F1、误报占比、漏报率与负样本页误报率统计
- 新增校准配置、结果 Schema 与 `scripts/calibrate_signature_candidates.py` CLI
- 校准报告强制不含源路径、文件名、原图或正文，并复核运行前后输入 SHA-256 不变
- 缺少独立 validation 真值时明确输出 `calibration_only`，不把合成回归或训练集指标冒充真实验证结果
- 自动化测试由 81 项增加至 87 项

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
