# OCR / 视觉 Worker

该目录放置与主 API 隔离的 Python 3.12 worker。主 API 保持轻量运行时；PaddleOCR、PaddlePaddle、OpenCV 和 NumPy 使用 `requirements-vision-worker.txt` 单独安装。

## 签字签章候选检测

`detect_signature_candidates_cv.py`：

- 红色/蓝色区域和轮廓用于生成印章候选；
- 签字只在调用方明确提供的 ROI 中检查墨迹，避免把正文误判为签字；
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

## OCR

OCR 页证据使用 `schemas/ocr_evidence.schema.json`。PaddleOCR worker 必须输出文字、四边形或边界框、置信度、模型配置、页码和图片哈希；低于阈值的文字只能进入人工复核。

当前仓库已经固定 OCR 证据契约和依赖版本；模型权重离线封装与页面渲染流水线仍属于下一项开发任务。
