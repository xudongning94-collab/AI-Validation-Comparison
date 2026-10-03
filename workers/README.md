# OCR / 视觉 Worker

该目录放置与主 API 隔离的 Python 3.12 worker。主 API 保持轻量运行时；PaddleOCR、PaddlePaddle、OpenCV 和 NumPy 使用 `requirements-vision-worker.txt` 单独安装。

## 运行时健康检查

不要在主 Python 3.13 中导入或安装 OpenCV/PaddleOCR。使用 bootstrap 创建隔离环境：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_vision_worker.ps1 `
  -Python312 "C:\path\to\python3.12.exe" `
  -Profile candidates `
  -AllowNetwork
```

`candidates` 只安装 OpenCV/NumPy；`all` 安装完整 OCR 依赖。离线部署传入 `-Wheelhouse`，脚本固定使用 `--no-index`；联网安装必须显式传入 `-AllowNetwork`。然后将环境变量指向独立 CPython 3.12：

```powershell
$env:BID_COMPARE_VISION_PYTHON = "C:\path\to\vision-worker\python.exe"
python scripts\check_vision_worker.py --require all
```

健康结果通过 `schemas/vision_worker_health.schema.json` 约束：

- `ready`：候选检测和 OCR 均可用；
- `degraded`：OpenCV 候选可用，但 OCR 依赖不完整；
- `unavailable`：解释器版本或核心依赖不满足；
- `failed`：健康子进程超时、无法启动或输出无效。

`configs/vision_worker.yaml` 不提交本机绝对路径；优先使用 `BID_COMPARE_VISION_PYTHON` 或不跟踪的本地覆盖配置。当前已验证 Python 3.12.10、OpenCV 4.10.0.84、PaddlePaddle 3.3.1、PaddleOCR 3.7.0 与 PaddleX 3.7.2；没有模型时健康状态仍应为 `degraded/offline_models_unavailable`。

离线模型目录必须包含 `model_manifest.json`。每个检测/识别模型以目录为单位声明，目录内每个普通文件都必须列入清单并通过 SHA-256；绝对路径、`..`、符号链接和未声明文件都会使健康检查失败。可对已有本地模型运行 `scripts/build_vision_model_manifest.py`，或显式暂存固定的官方模型：

```powershell
& .\.tools\vision-worker\Scripts\python.exe scripts\stage_official_vision_models.py --allow-network
```

暂存命令是唯一允许联网的模型准备步骤，下载到临时目录、安全解包、记录归档哈希并完整复验后，才移动到 Git 忽略的 `workers/models/`。生产 worker 不执行下载。然后配置：

```powershell
$env:BID_COMPARE_PADDLEOCR_MODEL_DIR = "C:\private\paddleocr-models"
python scripts\check_vision_worker.py --require all
```

模型文件和真实 manifest 放在 Git 忽略目录 `workers/models/` 或仓库外部；健康输出只报告是否配置、manifest 是否有效和模型数量，不输出目录与文件名。

## 签字签章候选检测

`detect_signature_candidates_cv.py`：

- 红色/蓝色区域和轮廓用于生成印章候选；
- 签字只在显式 ROI 中检查墨迹；ROI 可由调用方提供，或由 `scripts/locate_signature_fields.py` 按 OCR 几何、代表人签字/签章锚点及附近公章/日期提示生成；
- 字段定位与墨迹检测分两阶段执行，字段存在不能直接解释为已有手写签名；
- 输出页码、坐标、置信度、质量标志、输入 SHA-256 和检测器版本；
- 只判断候选存在性和明显质量问题，不鉴定签名或印章真伪。

示例：

```powershell
python workers\detect_signature_candidates_cv.py page-1.png \
  --page 1 \
  --signature-roi 100,1200,900,300 \
  --out output\page-1-candidates.json
```

worker 输出通过 `schemas/signature_candidates.schema.json` 约束，再作为 `/v1/signature-check` 的 `evidence_json.pages[].candidates` 输入。

## 逐页图像渲染

`scripts/render_document_pages.py` 将 PDF 直接通过 PyMuPDF 渲染为 RGB PNG；DOCX 通过隔离的 LibreOffice 用户配置先转换为临时 PDF，再进入相同渲染链。输出文件使用源文件哈希、页码和 DPI 命名，manifest 不包含源路径或源文件名，并复核运行前后源文件 SHA-256。

```powershell
python scripts\render_document_pages.py document.pdf `
  --output-dir output\page-render
```

renderer 可通过 `BID_COMPARE_DOCX_RENDERER`、配置值、PATH 或 Windows 标准 LibreOffice 安装目录发现。没有可用的 LibreOffice/`soffice` 时，DOCX 固定返回 `unavailable` 和 `docx_renderer_unavailable`，不生成页面，也不得据此推断签字或印章缺失。配置见 `configs/page_rendering.yaml`，结果契约见 `schemas/page_render.schema.json`。

## OCR

OCR 页证据使用 `schemas/ocr_evidence.schema.json`。PaddleOCR worker 必须输出文字、四边形或边界框、置信度、模型配置、页码和图片哈希；低于阈值的文字只能进入人工复核。

`run_paddleocr.py` 在导入 PaddleOCR 前先复核全部模型文件，使用模型根目录内的 ASCII 相对路径，并关闭文档方向、去畸变和文本行方向三个额外模型模块。Windows CPU 固定 `enable_mkldnn=False`，图片先解码为内存数组，避免 Paddle 3.3.1 的 oneDNN/PIR 与 Unicode 绝对路径问题。输出先通过 `schemas/ocr_worker_result.schema.json` 约束，再由 `VisionWorkerClient.ocr_page()` 归一化为 `schemas/ocr_evidence.schema.json`。官方 PP-OCRv5 模型、真实中文合成页 worker/客户端冒烟已通过；代表性真实 DOCX 与真实签署页验证仍未完成。

## D13.3 候选阈值校准

真实签署页与人工标注保存在 Git 忽略目录 `benchmarks/signature/local/`。先复制并填写 `benchmarks/signature_calibration_manifest.example.json`，再执行：

```powershell
python scripts\calibrate_signature_candidates.py `
  benchmarks\signature\local\manifest.json `
  --config configs\signature_calibration.yaml `
  --output output\signature-calibration\report.json
```

校准集用于选择阈值，验证集仅用于独立度量。报告不会包含源路径、文件名、原图或正文；若没有同时覆盖签字和印章真值的 validation 样本，状态保持 `calibration_only`。该流程评估候选存在性与定位效果，不提供签名或印章真伪鉴定。

校准 CLI 会先要求隔离 worker 具备 `signature_candidates` 能力，未通过健康检查时直接停止，不会退回到主 Python 内执行 OpenCV。
