# 投标文件多文档比对校验智能体（Codex 工程）

本仓库采用“**Codex 重开发、HiAgent 轻配置**”模式：核心解析、比对、评分、批注与 API 均在本工程中开发和测试；HiAgent 只负责文件入口、流程编排、少量模型节点、飞书发布与结果展示。

## 会话恢复

`PROJECT_STATE.json` 是机器可读的当前状态源，`CURRENT_PROGRESS_HANDOFF.md` 是人工可读的当前交接。无论从仓库目录还是其父目录启动，都应先运行：

Codex 线程 ID 和聊天正文只用于导航，不是工程恢复源。即使旧线程显示 `notLoaded`、`interrupted` 或侧边栏时间与正文不一致，也必须以 Git 检查点、`PROJECT_STATE.json` 和权威交接文件为准。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restore_context.ps1 -Verify
```

如果当前目录是父目录，则使用 `.\bid-compare-agent\scripts\restore_context.ps1 -Verify`。恢复脚本会拒绝错误 Git 根、未跟踪的权威交接、版本漂移、分支漂移和测试数量漂移。

## 当前版本

**v0.1.0-alpha.12 — D13 签字签章合规检查 Alpha**

已完成：

- D0：工程基线与目录结构
- D1：统一中间数据模型 / JSON Schema
- D2：DOCX / PDF 解析器 Alpha
- D3：文本查重引擎 Alpha
- D4：格式检查 Alpha
- D5：干扰识别 Alpha，并正式接入文本查重
- D6：图片重复检测 Alpha
- D7：AI 疑似度辅助分析 Alpha
- D8：统一风险评分引擎 Alpha
- D9：Word 反向定位与原生批注 Alpha
- D10：HTTP API Alpha
- D11：隐私保护的真实样本端到端 Benchmark Alpha
- D12：聚合分析、本地确定性报告、任务持久化、鉴权与哈希链审计基础
- D13.1–D13.2：签字/签章/主体名称/签署人/日期/位置规则与 OpenCV 候选检测 Alpha
- D13.3（进行中）：本地人工标注、候选校准、PDF/DOCX 页面渲染、严格离线模型契约，以及可复现的 Python 3.12 PaddleOCR 隔离 worker
- H1：HiAgent API 契约、环境变量与 OpenAPI 快照
- H2：工作流节点、失败分支、重试和隐私策略
- H3：结构化报告 Prompt、Schema 与示例
- H4：飞书卡片 JSON 2.0 模板与端到端验收清单

## 当前核心能力

### 文本重复度

- 2–5 份文档两两比对
- 字符 n-gram 倒排候选召回
- TF-IDF、SequenceMatcher、containment 词法融合评分
- 干扰项 `exclude` / `downweight`
- 文档重复率、重复章节 Top 分布和原文定位
- 预留 `SemanticReranker` 接口，后续接入语义模型

### 图片重复度

- DOCX/PDF 图片 SHA-256、pHash、平均色、尺寸特征
- 字节完全一致与近似图片检测
- 通过平均色、宽高比进行轻量误报过滤
- 图片重复率、图片对和原文位置输出

### 格式与干扰

- 正文主流字体/字号统计和格式离群定位
- 页边距基础异常检查
- 标题、低信息短文本、招标响应/法定模板干扰识别

### AI 疑似度辅助分析

- 基于句长规则度、连接词密度、通用措辞、重复短语和标点规则度形成可解释信号
- 输出段落分数、置信度、触发信号与原文定位
- 标题和短文本排除，模板响应内容降权
- 所有结果固定标记 `non_diagnostic=true` 和 `requires_human_review=true`
- 明确限制：结果不能证明文本由 AI 生成

### 统一风险评分

- 默认权重：文本 40%、图片 20%、AI 疑似度 15%、格式 25%
- 不适用维度自动排除并重新归一化有效权重
- 输出每个维度的原始分、配置权重、有效权重、贡献和证据摘要
- 输出文档级风险与文档集最大风险，等级为 `minimal/low/medium/high/critical`
- AI 疑似度始终作为非确定性辅助维度

### Word 反向定位与批注

- 将 Finding 的 `source_locator` / `peer_source_locator` 映射回 DOCX 正文段落或表格单元格
- 生成 Word 原生批注，保留严重度、类型、Finding ID、分数和证据摘要
- 支持最低严重度、最大批注数、作者和证据长度配置
- 输出结构化批注结果、跳过原因和源/结果文件哈希
- 强制输出到新 DOCX，避免覆盖原始投标文件
- AI 疑似度批注固定附带“非确定性、必须人工复核”提示

### 端到端 Benchmark

- 通过 manifest 区分招标文件、旧版响应文件和新版响应文件的业务角色
- 同时检测段落/表格逻辑内容、图片二进制与感知特征、DOCX 包部件差异
- 统计解析与各分析阶段耗时，并在运行前后复核源文件 SHA-256
- 将新旧版本共同内容追溯到招标文件来源，避免把标准响应内容直接解释为串标证据
- 报告默认且强制不包含正文原文，真实样本和本地 manifest 均不提交 Git

### 签字签章合规检查

- 通过版本化规则核对签字、签章、投标主体、签署人、日期、允许页码与位置锚点
- 原生文本、OCR 文本框和 OpenCV 视觉候选以统一页证据进入确定性规则引擎
- worker 未运行或失败时明确输出“证据不可用”，不会伪装成“漏签/漏章”
- `POST /v1/signature-check` 接收 `file`、`requirements_json` 和可选 `evidence_json`
- OpenCV worker 识别红/蓝印章候选，并仅在显式 ROI 内寻找签字墨迹候选
- 签字字段定位器保留 OCR 文本框几何，只接受局部的代表人角色与签字/签章锚点，并结合附近公章、日期提示生成 ROI；字段是否需要签字与 ROI 内是否已有手写墨迹分开判断
- 当前不能鉴定真实签名或印章真伪；低置信度和质量异常必须人工复核
- DOCX 原生内容暂按伪页 1 汇总，精确页面坐标仍需页面渲染和 OCR worker
- D13.3 使用 calibration/validation 分离的本地标注集，按 IoU 一一匹配候选与人工真值；同一源文档及其派生页必须使用同一 `document_group_id`，禁止跨 split 泄漏
- PDF 可通过 PyMuPDF 输出哈希命名的逐页 RGB PNG；源文件运行前后复核 SHA-256
- DOCX 使用隔离 LibreOffice 配置转换临时 PDF；运行时缺失时明确输出 `unavailable`，不伪造页证据
- DOCX 可通过 `--canonical-pdf` 指定同源权威 PDF；系统以双向规范化文本分片校验同源性，达标后使用 PDF 分页并记录双源 SHA-256、匹配率和 `canonical_pdf_used` warning，不同源 PDF 不发布页面
- 校准 CLI 不再把 OpenCV worker 导入主 Python；候选检测只通过配置的隔离子进程执行
- worker 健康检查核对 Python 3.12、OpenCV、NumPy、PaddleOCR 与 PaddlePaddle，并区分 `ready`、`degraded`、`unavailable` 和 `failed`
- OCR 的 `ready` 还要求离线模型 manifest 声明模型目录内全部文件且 SHA-256 全部通过；实际 worker 明确关闭三个额外模型模块，不允许运行时隐式下载
- 阈值扫描分别输出签字/印章的 TP、FP、FN、精确率、召回率、F1、误报占比、漏报率和负样本页误报率
- 校准报告只保留样本 ID 与 SHA-256，不写源路径、文件名或图像；缺少独立验证集时固定标记 `calibration_only`
- 入口：`python scripts/calibrate_signature_candidates.py benchmarks/signature/local/manifest.json`
- 权威分页回退：`python scripts/render_document_pages.py response.docx --canonical-pdf response.pdf --output-dir output/page-render`

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
```

仅解析：

```bash
python scripts/run_local.py A.docx -o output/
```

文本、图片和 AI 辅助分析：

```bash
python scripts/compare_texts.py A.docx B.docx -o output/text_compare.json
python scripts/compare_images.py A.docx B.docx -o output/image_compare.json
python scripts/analyze_ai_likelihood.py A.docx B.docx -o output/ai_likelihood.json
```

执行全部检测并生成统一评分：

```bash
python scripts/score_documents.py A.docx B.docx -o output/scoring.json
```

将检测结果中的 Finding 写回 Word 副本：

```bash
python scripts/annotate_docx.py A.docx findings.json -o output/A.annotated.docx --report output/annotation.json
```

启动本地 HTTP API：

```bash
python scripts/run_api.py --host 127.0.0.1 --port 8000 --data-dir data
```

局域网或跨主机访问必须启用 API Key：

```powershell
$env:BID_COMPARE_API_KEYS="replace-with-at-least-16-characters"
python scripts/run_api.py --host 0.0.0.0 --port 8000 --auth-mode api_key --data-dir data
```

交互式接口文档位于 `http://127.0.0.1:8000/docs`。主流程使用 `/v1/analyze`，一次解析即可返回 Findings、评分、本地确定性报告和任务编号；`/v1/tasks/{task_id}` 可查询状态与审计链。上传文件默认限制为单文件 50 MB、单次最多 5 份。

执行本地 Benchmark：

```bash
python scripts/run_benchmark.py benchmarks/local/case.json -o output/benchmark/report.json
```

可复制 `benchmarks/manifest.example.json` 建立本地样本清单；`benchmarks/local/` 与 `output/benchmark/` 已被 Git 忽略。

创建隔离视觉 worker（不得把 OpenCV/PaddleOCR 安装进主 Python 3.13）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_vision_worker.ps1 `
  -Python312 "C:\path\to\python3.12.exe" `
  -Profile candidates `
  -AllowNetwork
$env:BID_COMPARE_VISION_PYTHON = (Resolve-Path .\.tools\vision-worker\Scripts\python.exe).Path
python scripts\check_vision_worker.py --require signature
```

生产/离线复现时使用 `-Wheelhouse C:\path\to\wheelhouse`，脚本会强制 `--no-index`；不传 `-Wheelhouse` 时必须显式给出 `-AllowNetwork`。`-Profile all` 安装完整 OCR 依赖，但只有离线模型 manifest 与文件哈希通过后，OCR capability 才会变为可用。

官方模型只能通过显式暂存命令下载；生产 OCR worker 本身不联网：

```powershell
& .\.tools\vision-worker\Scripts\python.exe scripts\stage_official_vision_models.py --allow-network
$env:BID_COMPARE_PADDLEOCR_MODEL_DIR = (Resolve-Path .\workers\models).Path
python scripts\check_vision_worker.py --require all
```

## 目录

```text
configs/                 阈值和评分配置
prompts/                 HiAgent / LLM Prompt 版本基线
schemas/                 JSON Schema
src/bid_compare_agent/
  parser/                DOCX/PDF 解析
  preprocess/            干扰识别
  compare/               文本/图片相似度
  analysis/              AI 疑似度辅助分析
  check/                 格式检查
  scoring/               统一风险评分
  annotate/              Word 反向定位与原生批注
  api/                   FastAPI HTTP API 与流水线编排
  benchmark/             隐私保护端到端 Benchmark
  models/                中间数据模型
scripts/                 本地入口
tests/                   单元/集成测试
  reporting/             本地确定性报告
  tasks/                 任务状态、审计与恢复基础
  vision/                OCR/视觉 worker 证据契约
hiagent/                 HiAgent 适配资料
benchmarks/              Benchmark manifest 示例；local/ 不入库
```

## 开发原则

1. HiAgent 不承载核心算法实现。
2. 所有节点输入输出使用可版本化 JSON Schema。
3. Finding 必须能映射回原文位置。
4. 阈值、权重和风险等级配置化。
5. 每一阶段先通过本地自动化测试，再接入 HiAgent。
6. 核心对象 ID 尽量内容寻址，便于缓存、重试和审计。
7. AI 疑似度不得作为确定性结论或唯一否决依据。

## 当前验证状态

- Python 3.13.15 `compileall` 通过
- `pytest`：当前期望数量以 `PROJECT_STATE.json` 为准，并由恢复脚本复核
- 文本、图片、AI 疑似度、评分和批注结果均通过各自 JSON Schema 校验
- 批注 DOCX 可重新打开，并包含有效的 OOXML 原生评论部件和定位标记
- 签署规则、候选 worker 的成功/失败契约和 `/v1/signature-check` 通过 Schema/集成测试
- D13.3 标注 manifest、校准报告 Schema、阈值选择、隐私约束和输入哈希完整性通过自动化测试
- 页面渲染结果通过 Schema 校验，覆盖 PDF 双页输出、DOCX renderer 缺失和隔离转换路径
- 页面渲染 Schema v1.1 覆盖 canonical PDF 同源回退、不同源拒绝、双源完整性与路径隐私；真实 WPS DOCX/PDF 组合以 0.76/0.76 双向匹配通过 0.7 门槛并输出 204 个权威页面
- 新增两组相互独立的真实 PDF 验证素材，共 393 页全部完成只读渲染和印章候选扫描；秣陵组 189 个阈值内候选已人工标为 129 个真印章和 60 个误报，但尚未逐页审计漏检，因此不能据此报告召回率
- 旧版秣陵签名页审核的 24 个已标注页面全部无手写。采用几何与局部表单语义重扫后，25 页宽泛关键词候选只保留第 8 页；该页存在必签字段但没有手写签名，验证了字段存在与手写存在必须拆分
- Windows 标准路径的 LibreOffice 可自动发现；合成两页 DOCX 已真实转换并渲染为 2 张 PNG，未修改源文件
- 隔离 worker 健康检查、缺失解释器降级、子进程候选检测和校准 CLI 拒绝主进程导入通过契约测试
- 离线模型 manifest 的目录边界、符号链接拒绝、全文件声明和 SHA-256 完整性通过自动化测试
- 官方 PP-OCRv5 server 检测/识别模型已显式暂存并通过逐文件校验；真实中文合成页由正式 worker 与客户端识别出 2 行文字，置信度均约 0.997，原始结果与产品证据 Schema 均通过
- Windows CPU 冒烟固定关闭存在 PIR 兼容问题的 oneDNN 路径，并使用 ASCII 相对模型路径与内存图像输入，规避 Unicode 绝对路径缺陷
- Python 3.12.14 隔离环境已通过 `pip check`，OpenCV、NumPy、PaddlePaddle、PaddleOCR 与 PaddleX 均可真实导入
- 现有 Python 3.12/OpenCV 环境完成合成签署页回归，返回 1 个印章候选和 1 个签字候选
- 首个本地真实单文档校准集已导入 21 页（16 个印章真值、10 个负/困难样本页），报告正确保持 `calibration_only`；组件聚类与 `configs/vision_worker.yaml` 中可配置的尺度感知置信度后，0.75 阈值 TP=14、FP=23、FN=2、召回 0.875、精确率 0.378、F1 0.528、负样本页误报率 0.30，召回达到校准下限但整体质量与独立验证仍未达到发布门槛
- OpenCV 图片入口改为 Python 字节读取后内存解码，真实中文绝对路径批量候选检测通过
- 首组 3 份真实样本 Benchmark 通过，观测耗时 15.3–38.8 秒（受缓存与并发负载影响），且源文件哈希保持不变
- HiAgent OpenAPI、工作流、报告和飞书卡片本地契约通过自动化校验

## 下一阶段

- D13.3：完成秣陵印章全页漏检审计，并用“字段存在/手写存在”二阶段流程审核广州组手写候选；按文档组冻结真值后，在不重新调参的前提下形成独立 validation 统计
- 在真实 HiAgent 工作区导入 H1–H4 配置，并与飞书测试机器人联调
- 扩充人工标注样本集，持续校准误报/漏报率
- 扩充代表性 WPS/Word DOCX/PDF 配对回归；已确认一个真实样本 LibreOffice 为 261 页、同源权威 PDF 为 204 页，并已通过 canonical PDF 回退避免错误页码进入标注
