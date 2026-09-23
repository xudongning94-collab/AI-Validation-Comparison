from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.parser import parse_document


def main() -> int:
    parser = argparse.ArgumentParser(description="解析投标文件并输出统一 DocumentIR JSON")
    parser.add_argument("files", nargs="+", help="DOCX/PDF 文件")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    args = parser.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    for raw in args.files:
        source = Path(raw)
        doc = parse_document(source)
        target = out_dir / f"{source.stem}.document_ir.json"
        target.write_text(json.dumps(doc.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK {source} -> {target} | paragraphs={len(doc.paragraphs)} tables={len(doc.tables)} images={len(doc.images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
