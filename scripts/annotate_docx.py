from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.annotate import annotate_docx
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.utils.config import load_docx_annotation_config


def _finding_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("findings"), list):
        items = payload["findings"]
    else:
        raise ValueError("Finding JSON 必须是数组，或包含 findings 数组的对象")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("findings 数组中的每一项都必须是对象")
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="将 Finding 反向定位到 Word 并生成原生批注副本")
    parser.add_argument("source", help="待批注的原始 DOCX 文件")
    parser.add_argument("findings", help="Finding 数组或含 findings 字段的 JSON 文件")
    parser.add_argument("-o", "--output", required=True, help="批注后的 DOCX 输出文件（不得覆盖源文件）")
    parser.add_argument(
        "--report",
        default="output/annotation.json",
        help="批注结果 JSON",
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "configs" / "annotation.yaml"),
        help="批注作者、严重度和数量配置",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    findings = [Finding.from_dict(item) for item in _finding_items(payload)]
    result = annotate_docx(
        args.source,
        args.output,
        findings,
        config=load_docx_annotation_config(args.config),
    )

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"OK annotated={result.summary['annotated_comments']} "
        f"skipped={result.summary['skipped_findings']}"
    )
    print(f"DOCX {args.output}")
    print(f"REPORT {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
