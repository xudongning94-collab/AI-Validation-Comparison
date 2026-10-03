# 当前进度与恢复交接

> 本文件是当前进度的唯一人工可读交接；机器可读状态以 `PROJECT_STATE.json` 为准。`HANDOFF_TO_CODEX.md` 仅保留历史背景，不得覆盖这里的当前状态。

## 1. 恢复摘要

- 更新时间：2026-10-03（Asia/Shanghai）
- 恢复来源：`repository_checkpoint`
- 恢复检查点 ID：`d13.3-recovery-contract-v2`
- 历史起源线程 ID：`01a0cd3c-1267-7101-9b52-0c63eb4df8c7`（仅用于追溯，不作为恢复入口）
- 仓库：`xudongning94-collab/AI-Validation-Comparison`
- 本地恢复检查点分支：`codex/d13-3-calibration-checkpoint`
- 项目版本：`0.1.0-alpha.12`
- D13.3 基线提交：`7afbee3209b0770d21a813eaa4d2b956f3f925b3`
- 当前 HEAD：不得写死；恢复时以 `git rev-parse HEAD` 的输出为准
- 本地标签：`v0.1.0-alpha.12`，解引用到 D13.3 基线提交
- 机器状态：`D13.3 / in_progress`
- 当前阶段：D13.3 校准基础设施、页面渲染、canonical PDF 回退、隔离 CV/OCR worker、真实素材候选扫描及首轮人工标注已完成；新增基于 OCR 几何与局部表单语义的签字字段定位器，将“需要签字的字段”与“已出现手写墨迹”拆分判定。秣陵旧版 25 页关键词候选已收敛为第 8 页 1 个真实字段，且该字段没有手写签名；人工真值冻结、漏章全页审计、独立手写正例审核、validation、更多 DOCX/PDF 配对回归与上线验收未完成
- 产品结论：核心功能闭环已达到 Alpha；尚未完成真实数据验证和生产环境发布，不能称为最终开发完成
- 记录恢复说明：Codex 侧边栏索引与旧线程正文曾出现不一致；旧线程只作为导航记录。任何新窗口都必须以当前 Git 分支、`PROJECT_STATE.json` 和本文件恢复开发状态，不得从线程摘要推断工程进度。

## 2. 恢复时必须先做的事

不要执行 `git reset --hard`、`git checkout -- .` 或清理未跟踪文件。先运行恢复脚本，让脚本从自身位置解析真实仓库根，避免误用父目录的空 Git 仓库。恢复脚本输出的 `history_source` 必须为 `repository_checkpoint`，`checkpoint_id` 必须与本文件一致；旧 Codex 线程能否加载不影响工程恢复结论。

从仓库目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restore_context.ps1 -Verify
```

即使当前工作目录是父目录，也可以直接执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\bid-compare-agent\scripts\restore_context.ps1 -Verify
```

恢复脚本会校验真实 Git 根、分支、版本、基线提交、权威交接是否已经跟踪，以及测试数量。预期测试结果由 `PROJECT_STATE.json` 唯一声明，当前为 `129 passed`。

## 3. 当前已完成范围

### D0–D12 Alpha

- 文档解析与统一 DocumentIR
- 文本重复检测、干扰识别与降权
- 图片 SHA-256/pHash 相似检测
- 格式异常检查
- AI 疑似度非确定性辅助分析
- 统一风险评分
- DOCX 原生批注与反向定位
- FastAPI HTTP API
- 隐私保护的本地真实样本 Benchmark
- 聚合分析、本地确定性报告、SQLite WAL 任务状态、API Key 鉴权和哈希链审计

### H1–H4 本地接入包

- HiAgent API 契约与 OpenAPI 快照
- 平台无关工作流规范、失败分支和重试策略
- 结构化报告 Prompt/Schema
- 飞书卡片 JSON 2.0 模板与验收清单

说明：这些是可版本化的本地接入资产，不代表已经在真实 HiAgent 工作区或飞书租户完成发布。

### D13.1–D13.2

- 确定性签署规则：签字、签章、主体、签署人、日期、页码和位置锚点
- `POST /v1/signature-check`
- OpenCV 红/蓝印章候选检测
- 显式 ROI 内签字墨迹候选检测
- worker 失败/禁用时输出“证据不可用”，不误判漏签或漏章
- 明确能力边界：只能核对存在性、一致性、位置和明显质量异常，不能鉴定真伪

### D13.3 本轮已实现的基础设施

- 本地人工标注 manifest 与稳定 JSON Schema
- calibration/validation 数据切分
- 每个样本必须声明 `document_group_id`；同一源文档及其派生页禁止跨 calibration/validation
- 候选与人工真值的 greedy IoU 一一匹配
- 签字、印章分别扫描候选置信度阈值
- 在最低召回率约束下按 F1 选择阈值
- 输出 TP、FP、FN、precision、recall、F1、false discovery rate、miss rate 和负样本页误报率
- 校准后在 validation 子集不再调参
- 输入文件运行前后 SHA-256 完整性复核
- 报告不包含源路径、文件名、原图或正文
- 没有独立验证真值时固定输出 `calibration_only`
- PDF 通过 PyMuPDF 生成哈希命名的逐页 RGB PNG，运行前后复核源文件 SHA-256
- DOCX 采用隔离 LibreOffice 用户配置转换临时 PDF；renderer 缺失时输出 `unavailable` 且不生成伪页证据
- 页面渲染结果不包含源路径或文件名，发布失败时清理由本次运行产生的部分页面
- 隔离 worker 健康检查核对 Python 3.12 与 OpenCV/PaddleOCR 依赖，并输出稳定 Schema
- `VisionWorkerClient` 通过子进程调用候选 worker，处理解释器缺失、超时、启动失败和无效输出
- 校准 CLI 未通过 `signature_candidates` 健康门禁时停止，不再把 worker 动态导入主 Python
- OCR 只有在 Python/依赖与离线模型 manifest、相对路径和 SHA-256 全部通过时才标记可用
- 新增候选/完整 OCR 两级依赖与可复现 bootstrap；联网必须显式授权，wheelhouse 固定 `--no-index`
- 本机 Python 3.12.14 隔离环境已通过 `pip check`，CV/OCR 模块真实导入成功；无离线模型时正确停留在 `degraded`
- 自动发现 Windows 标准 LibreOffice，合成两页 DOCX 已真实转换并渲染为 2 张 PNG；输出解码不再依赖系统 GBK
- OpenCV 候选图片使用 Python 字节读取和内存解码，支持 Windows 中文绝对路径
- 同色近邻印章碎片在输出前聚类，极细长边框和彩条在参与传递性聚类前过滤；聚类候选按 `configs/vision_worker.yaml` 中的相对页面尺度锚点对过小图标和超大彩色版块降权，但保留候选供低阈值校准
- 首个真实单文档本地校准集已完成 21 页运行：16 个印章真值、10 个负/困难样本页；报告为 `calibration_only`，没有手写签名正样本，也没有独立 validation
- 2026-10-02 在本地真实业务签署页完成离线 PaddleOCR 与 OpenCV 候选端到端复验：OCR 返回 `ok` 和 120 个文本项，候选检测返回 `ok` 和 2 个印章候选；只记录脱敏计数与状态，不记录正文
- 2026-10-02 完成真实旧版 DOC 分页对照：LibreOffice 直接转 PDF 为 341 页，与现有参考 PDF 一致；同一 DOC 先迁移到 DOCX 后由正式渲染器得到 426 页，证明格式迁移改变了分页，派生 DOCX 不能替代原生业务 DOCX 验收
- 2026-10-02 接入第二个原生真实业务 DOCX：OOXML 结构有效、与既有 341 页文档的双向抽样文本片段重合率均为 0，可作为独立文档组；正式渲染返回 `ok` 和 261 页，261/261 页印章候选预扫描均为 `ok`，44 页共 111 个候选。人工抽查确认既有真实公章正例，也有国徽、网页配色和界面截图等困难负例；尚未形成完整人工真值
- 2026-10-02 取得第二个原生 DOCX 的同源 PDF：PDF 为 204 页，与 DOCX 双向抽样正文重合约 76%，与 LibreOffice 生成 PDF 的正文重合约 99%；LibreOffice 结果为 261 页，较权威 PDF 多 57 页，分页兼容性验收明确未通过。权威 PDF 已由正式渲染器生成 204 页，204/204 页候选扫描均为 `ok`，43 页共 119 个印章候选
- 页面渲染契约升级至 Schema v1.1：DOCX 可传入 `--canonical-pdf`，系统以 64 字符规范化分片执行双向同源校验；真实组合的 DOCX→PDF/PDF→DOCX 匹配率均为 0.76，通过 0.7 门槛，输出 `canonical-pdf+pymupdf`、204 页、双源哈希不变和 `canonical_pdf_used` warning，且不泄露路径
- 2026-10-03 接入两组新增独立 PDF 素材：一个由 10 份 PDF 组成、合计 51 页，另一个为 342 页单 PDF；两组均未加密，正式渲染 393/393 页成功，源 SHA-256 前后不变。342 页组与既有 341 页样本的双向规范化文本片段重合率均为 0，可视为独立文档组
- 新增两组候选预扫描均全部返回 `ok`：51 页组在 23 页产生 74 个印章候选，其中 25 个达到 0.75；342 页组在 158 页产生 430 个候选，其中 189 个达到 0.75。两组共 504 个候选、214 个达到当前阈值
- 已导入秣陵人工审核 JSON：189 个达到阈值的印章候选均已审核，其中 129 个标记为 `true_seal`、60 个标记为 `false_positive`。这些标签可用于候选精确率证据，但因为审核包未要求逐页标记漏检印章，不能据此计算召回率
- 旧版签名页审核的 24 个已标注页面全部为 `signature_absent`，暴露出“页面出现宽泛关键词”与“局部存在必签字段”被混为一谈的根因。新定位器保留 OCR 文本框几何，只接受同一行/相邻同一行的代表人角色与签字/签章锚点，并要求局部公章或日期表单提示；秣陵全 342 页只保留第 8 页
- 第 8 页复核结果明确拆分为：`field_present`（存在“法定代表人签字或签章”字段）和 `handwritten_absent`（字段附近没有手写签名）。本地已生成新的二阶段审核页，先问字段是否存在，再问字段 ROI 中是否已有手写墨迹

核心文件：

- `src/bid_compare_agent/vision/calibration.py`
- `scripts/calibrate_signature_candidates.py`
- `configs/signature_calibration.yaml`
- `schemas/signature_calibration_manifest.schema.json`
- `schemas/signature_calibration.schema.json`
- `benchmarks/signature_calibration_manifest.example.json`
- `tests/unit/test_signature_calibration.py`
- `tests/integration/test_signature_calibration_contract.py`
- `src/bid_compare_agent/vision/page_rendering.py`
- `scripts/render_document_pages.py`
- `configs/page_rendering.yaml`
- `schemas/page_render.schema.json`
- `tests/integration/test_page_rendering.py`
- `src/bid_compare_agent/vision/worker_client.py`
- `workers/vision_worker_health.py`
- `scripts/bootstrap_vision_worker.ps1`
- `requirements-vision-candidates.txt`
- `scripts/check_vision_worker.py`
- `configs/vision_worker.yaml`
- `schemas/vision_worker_health.schema.json`
- `schemas/vision_model_manifest.schema.json`
- `workers/model_manifest.example.json`
- `workers/offline_models.py`
- `workers/run_paddleocr.py`
- `schemas/ocr_worker_result.schema.json`
- `scripts/build_vision_model_manifest.py`
- `scripts/stage_official_vision_models.py`
- `tests/integration/test_vision_worker_runtime.py`
- `tests/unit/test_vision_worker_health.py`
- `workers/detect_signature_candidates_cv.py`
- `tests/unit/test_signature_candidate_worker.py`
- `src/bid_compare_agent/vision/signature_fields.py`
- `scripts/locate_signature_fields.py`
- `configs/signature_field_locator.yaml`
- `schemas/signature_field_locator.schema.json`
- `tests/unit/test_signature_field_locator.py`
- `tests/integration/test_signature_field_locator_cli.py`

## 4. 恢复检查点

D13.3 实现、测试、配置、文档和恢复基础设施属于同一检查点，必须整体保存。恢复基础设施包括：

- `AGENTS.md`：仓库启动规则
- `PROJECT_STATE.json`：机器可读的唯一当前状态
- `CURRENT_PROGRESS_HANDOFF.md`：唯一人工可读的当前交接
- `scripts/check_recovery_state.py`：状态一致性检查
- `scripts/restore_context.ps1`：从任意工作目录恢复并可选全量验证
- `tests/integration/test_recovery_contract.py`：覆盖仓库目录和父目录两种启动方式

检查点提交后，`git status --short --branch` 应保持干净。若不干净，必须先辨认改动归属，不得在恢复时自动丢弃。

## 5. 最新验证证据

2026-10-03 在 Python 3.13.15 主环境恢复并复验：

```powershell
.\.tools\python313\python.exe -m compileall -q src scripts tests workers
.\.tools\python313\python.exe -m pytest --basetemp .pytest-tmp
git diff --check
```

结果：

- `compileall`：退出码 0
- `pytest`：`129 passed`
- `git diff --check`：通过；只有 Git 的 LF/CRLF 提示，无空白错误
- 隔离 worker：原虚拟环境引用的旧 Python 3.12 安装已不存在；使用当前 CPython 3.12.14 执行标准 `venv --upgrade` 重新绑定后，`pip check` 及 OpenCV/NumPy/Paddle/PaddleOCR/PaddleX 真实导入通过
- 候选子进程：合成页返回 1 个印章候选和 1 个签字候选
- DOCX renderer：合成两页文档返回 `status=ok`、`page_count=2`
- PaddleOCR 健康检查：配置本地模型后返回 `ready`，`ocr=true`，manifest 有效且模型数为 2
- PaddleOCR 真实冒烟：中文合成页识别 2 行，置信度约 0.9971/0.9976；worker 与客户端 Schema 均通过
- 中文绝对路径候选批处理：21 个真实校准样本全部返回 `ok`，输入文件运行前后哈希不变
- 真实单文档校准基线：聚类前最高召回 0.50；组件聚类与细长元素预过滤后达到 TP=14、FP=55、FN=2；尺度感知置信度降权后在同一 0.75 阈值达到 TP=14、FP=23、FN=2、召回率 0.875、精确率 0.378、F1 0.528、误发现率 0.622、负样本页误报率 0.30。召回保持配置下限以上，但报告仍为 `calibration_only`，这些数字不得表述为独立验证效果
- 本地真实业务签署页端到端复验：离线 PaddleOCR 返回 `status=ok`、120 个文本项，OpenCV 候选 worker 返回 `status=ok`、2 个印章候选；输入均带 SHA-256，未在版本化记录中保留正文
- 同一 21 页本地 manifest 重跑返回 `calibration_only`，输入完整性复核通过，印章推荐阈值与上述指标一致
- 真实旧版 DOC 分页诊断：直接 DOC→PDF 为 341 页，与参考 PDF 相同；派生 DOCX 经项目正式渲染器返回 `status=ok`、426 页且输入哈希不变。85 页差异定位在 DOC→DOCX 格式迁移层，因此该派生文件不计为原生 DOCX 分页验收通过
- 第二个原生业务 DOCX：源文件约 10.5 MiB，由 WPS Office 保存，内置页数元数据为 156；LibreOffice 正式渲染返回 `status=ok`、261 页、261 张页面图，源文件 SHA-256 前后不变，清单不含源路径。同源导出 PDF 已确认是 204 页，因此内置元数据不作为页数基准，LibreOffice 分页兼容性判定为未通过
- 第二个独立文档组候选预扫描：261/261 页成功，44 页共 111 个印章候选；抽查确认第 46 页含真实公章，第 233、259 页含典型彩色语义干扰。16 个“签字/签名”关键词邻域 ROI 均产生墨迹候选，但抽查以印刷文字为主，不能视为手写签名正例
- 第二个文档组的同源权威 PDF：`status=ok`、204 页、源 SHA-256 前后不变、清单不含源路径；204/204 页印章候选扫描成功，43 页共 119 个候选。后续人工真值必须使用这套 204 页 PDF 页码，不再使用 261 页 LibreOffice 页码
- 两组新增独立 PDF：393/393 页正式渲染成功，候选扫描无失败页；51 页组为扫描件密集材料并含视觉确认的手写签名候选页面，342 页组有 131 个稀疏/无文本层页面
- 秣陵人工审核结果已导入：189 个印章候选中 129 个真印章、60 个误报；该候选审核不包含全页漏检标记，因此只支持候选精确率分析，不支持召回率结论
- 秣陵旧版宽泛关键词签名候选共 25 页，其中 24 个已审核页面全部没有手写；几何/局部语义重扫后只命中第 8 页 1 个必签字段，OCR 与页面复核均确认字段存在但手写缺失。新结果不包含 OCR 正文或源路径
- 分页根因证据：同源 PDF 与 LibreOffice PDF 正文约 99% 重合，代表内容基本完整；两者均包含楷体、宋体、仿宋、微软雅黑和 Times New Roman 等核心字体，单纯缺字体替换不是主因。DOCX 使用 Office 15 兼容模式、东亚版式及固定行网格，视觉抽查显示 LibreOffice 行距/换行更松，差异随文档逐步累积

## 6. 远端状态与限制

最近一次成功通过 GitHub 页面核验的远端状态：

- 核验日期：2026-09-25
- 远端 `main`：`87ae1d3c9dfda847e564a16a77eab37947f1a9a7`
- 提交说明：同步经验证的 `v0.1.0-alpha.12` 项目树，包含 D11–D13.2，81 tests
- 当时 GitHub 页面显示：0 Tags

本地提交历史与远端同步提交不是同一提交 ID；本地 `7afbee3` 是 D13.1–D13.2 提交，远端 `87ae1d3` 是将完整项目树同步到另一条远端历史的提交。

2026-09-28 再次执行 `git fetch --tags origin main` 时 GitHub 连接被重置；应用内浏览器插件也出现版本不匹配。因此恢复后必须重新核验远端，不能仅依据本文宣称远端仍未变化。

## 7. 尚未完成与上线阻断项

### P0：D13.3 真实验证闭环

1. PDF、合成 DOCX 和第二个原生业务 DOCX 的逐页渲染已完成；同源权威 PDF 为 204 页，LibreOffice DOCX 渲染为 261 页，分页稳定性验收未通过。canonical PDF 双向校验与权威分页回退契约已实现并通过真实文件；仍需扩充更多 WPS/Word 配对回归。
2. 隔离 worker、Python 3.12、固定 CV/OCR 依赖、官方模型、合成页冒烟以及本地真实业务签署页 OCR/候选端到端复验已完成；仍需在独立文档组上重复验证。
3. 目录级离线模型完整性门禁与无隐式下载加载契约已完成；`workers/models/` 为 Git 忽略的本机资产，换机恢复时需重新运行显式暂存脚本。
4. 已收集并标注首个真实源文档；第二个独立文档组已取得同源权威 PDF 并完成 204 页候选预扫描；另有两组独立 PDF 完成 393 页预扫描。秣陵组已完成 189 个印章候选审核，但仍需全页漏检审计；其签字字段复核没有手写正例。广州组存在视觉确认的手写候选，必须使用新的“字段存在/手写存在”二阶段流程复核并冻结。
5. 组件聚类与尺度感知置信度已在单文档 calibration 上保持 0.875 召回并把 FP 从 55 降至 23；第二个独立组已出现国徽、网页配色和界面截图等目标困难负例，应先完成冻结真值，再验证现有阈值，禁止依据 validation 结果继续调参。
6. 按文档组完成签字/印章 calibration 与独立 validation 标注，禁止同源页面跨 split。
7. 重新运行校准 CLI，锁定真实阈值并生成独立验证集误报/漏报统计。
8. 将真实阈值和可脱敏的统计结论纳入回归测试及版本文档。

在上述工作完成前，不得把 D13.3 标记为完成，也不得把合成样本结果或单文档 calibration 集指标表述为真实验证效果。

### P1：真实平台发布验收

1. 部署受控 HTTPS API，并启用 API Key。
2. 在真实 HiAgent 工作区导入 H1–H4 配置。
3. 接入飞书测试机器人与测试会话。
4. 验证上传、分析、报告、卡片、失败重试、任务恢复、调用者隔离和审计链。
5. 完成隐私、日志和人工发布门禁验收。

### P2：持续增强

- 扩充人工标注数据集并持续监控阈值漂移
- D3 文本 Embedding 语义精排
- D6 视觉 Embedding 精排
- 更完整的性能、并发和长时间运行测试

## 8. D13.3 下一步直接执行方式

先配置并检查隔离视觉 worker：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_vision_worker.ps1 `
  -Python312 "C:\path\to\python3.12.exe" -Profile all -AllowNetwork
$env:BID_COMPARE_VISION_PYTHON = (Resolve-Path .\.tools\vision-worker\Scripts\python.exe).Path
& $env:BID_COMPARE_VISION_PYTHON scripts\stage_official_vision_models.py --allow-network
$env:BID_COMPARE_PADDLEOCR_MODEL_DIR = (Resolve-Path .\workers\models).Path
python scripts\check_vision_worker.py --require all
```

只有健康检查返回 `ready` 且退出码为 0，才进入真实 OCR/候选校准。`degraded` 仅表示候选检测可用，不代表 OCR 已就绪。

先将 PDF 渲染为本地逐页图片：

```powershell
python scripts\render_document_pages.py document.pdf `
  --output-dir output\page-render
```

DOCX 使用同一命令；renderer 按 `BID_COMPARE_DOCX_RENDERER`、配置值、PATH、Windows 标准安装目录依次发现。仍未发现时返回 `docx_renderer_unavailable`，不能继续生成视觉结论。

若 DOCX 有同源 WPS/Word 导出 PDF，必须优先使用权威分页回退：

```powershell
python scripts\render_document_pages.py document.docx `
  --canonical-pdf document.pdf `
  --output-dir output\page-render
```

只有双向文本分片匹配率均达到 `configs/page_rendering.yaml` 的 `canonical_pdf_minimum_text_match` 才会发布页面；不同源 PDF 返回 `canonical_pdf_content_mismatch` 且不生成页面。

真实图片和本地 manifest 必须放在 Git 忽略目录：

```text
benchmarks/signature/local/
```

同一源文档（包括转换后的 PDF、逐页图片和其他派生物）必须使用同一个 `document_group_id`，并整体进入 calibration 或 validation，不能拆分到两侧。

复制示例并填写真实标注：

```powershell
Copy-Item benchmarks\signature_calibration_manifest.example.json `
  benchmarks\signature\local\manifest.json
```

运行校准：

```powershell
python scripts\calibrate_signature_candidates.py `
  benchmarks\signature\local\manifest.json `
  --config configs\signature_calibration.yaml `
  --output output\signature-calibration\report.json
```

验收要求：

- worker 对所有样本返回 `ok`
- 输入 SHA-256 运行前后不变
- 签字和印章在 calibration 集均有人工真值
- 签字和印章在 validation 集均有人工真值
- 报告状态为 `validated`，不能是 `calibration_only`
- 推荐阈值满足配置中的最低召回率要求
- 报告不出现路径、文件名、原图或正文
- 人工复核误报和漏报实例后才能固化阈值

## 9. 已知环境问题

- 主 Python 3.13 环境没有 `cv2`；不要把 PaddleOCR/OpenCV 安装进主 API 环境。
- 当前机器已发现 LibreOffice 标准安装并完成合成两页 DOCX 冒烟；代表性真实业务 DOCX 尚未验证。
- 当前机器使用 Python 3.12.14，`.tools/vision-worker` 中完整依赖已安装；环境曾因原始基础解释器被移除而失效，已用当前 3.12 执行 `venv --upgrade` 修复。该环境为 Git 忽略的本机资产，恢复后必须重新运行健康检查。
- 当前配置本地模型时完整健康状态为 `ready`；若 Git 忽略的 `workers/models/` 缺失，则正确降级为 `degraded/offline_models_unavailable`。
- 首轮真实印章校准显示 OpenCV HSV 轮廓法会把低透明印章拆成碎片并误报国徽、交通标志、认证标识和网页配色；组件聚类已修复大部分碎片漏检，尺度感知置信度已抑制多数过小图标和超大版块，但同尺度语义干扰仍存在，在独立 validation 前不得固化阈值。
- 官方模型归档约 88.3 MB + 84.9 MB，归档 SHA-256 记录在本机 `workers/models/model_sources.json`；模型不提交 Git。
- PaddlePaddle 3.3.1 在当前 Windows CPU 上启用 oneDNN 会触发 PIR 属性转换错误；worker 已固定 `enable_mkldnn=False`。
- Paddle 运行时无法可靠处理当前中文父目录的绝对模型路径；worker 在校验后切换模型根目录并使用 ASCII 相对路径，同时将图像解码为内存数组。
- 视觉 worker 必须使用独立 Python 3.12 环境；不得把 OpenCV/PaddleOCR 安装进主 Python 3.13。
- 曾尝试用隐藏 Word COM 将两份约 38 MB 的本地响应文档导出 PDF；转换长时间无输出后已终止，未生成衍生文件，源文件未修改。不要把 Word COM 视为稳定页面渲染方案。
- 98 MB 真实旧版 DOC 在 LibreOffice 26.8.0.3 中直接导出 PDF 可保持参考文件的 341 页；先转为 DOCX 会扩展为 426 页。该差异属于格式迁移，不得用于宣称原生 DOCX 分页稳定；仍需独立的原生业务 DOCX 样本。
- 第二个原生 DOCX 的同源导出 PDF 已确认是 204 页；LibreOffice 26.8.0.3 渲染为 261 页，正文约 99% 重合但分页多 57 页。该兼容性失败主要表现为行距/换行膨胀，并与 Office 15 东亚版式及固定行网格有关；现已实现 `--canonical-pdf` 同源校验回退，正式标注必须使用其输出的权威 PDF 页码。
- GitHub CLI 未安装；Git HTTPS 当前可能被网络策略重置。

## 10. 不可突破的约束

1. 核心解析、检测、校准和评分逻辑保留在本工程中；HiAgent 只负责编排和展示。
2. Finding 必须保留可追踪 `source_locator`。
3. 阈值、权重和风险等级必须配置化。
4. AI 疑似度始终是非确定性辅助信号，必须人工复核。
5. 签字/印章能力不得宣称鉴定真伪。
6. worker 未运行或失败时不得据此判定漏签/漏章。
7. 真实文档、页面图像、本地标注 manifest 和校准报告不得提交 Git。
8. 每一阶段同步 Schema、测试、README、PROJECT_BASELINE、HANDOFF 和 CHANGELOG。

## 11. 建议的下一版本门槛

在以下条件同时满足后，再考虑将版本推进到下一 Alpha：

- D13.3 真实 validation 数据集完成
- 可复现地输出 `validated` 报告
- 阈值写入版本化配置并有回归测试
- 页面渲染和隔离视觉 worker 能端到端运行
- 全量自动化测试通过
- 文档更新完成
- 远端 `main` 已重新核验并完成受控提交/推送

在此之前保持 `0.1.0-alpha.12` 和 `Unreleased — D13.3` 状态。
