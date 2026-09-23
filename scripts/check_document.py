from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.check import check_document_format
from bid_compare_agent.parser import parse_document
from bid_compare_agent.preprocess import classify_interference


def main() -> int:
    parser = argparse.ArgumentParser(description="解析文档并执行格式检查/干扰项识别 Alpha")
    parser.add_argument("file", help="DOCX/PDF 文件")
    parser.add_argument("-o", "--output", default="output/document_check.json")
    args = parser.parse_args()

    document = parse_document(Path(args.file))
    result = {
        "document": {"document_id": document.document_id, "filename": document.filename, "sha256": document.sha256},
        "format_check": check_document_format(document).to_dict(),
        "interference": classify_interference(document).to_dict(),
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {document.filename} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
