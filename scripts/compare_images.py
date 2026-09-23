from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.compare import compare_image_set
from bid_compare_agent.parser import parse_document
from bid_compare_agent.utils.config import load_image_compare_config


def main() -> int:
    parser = argparse.ArgumentParser(description="解析 2-5 份投标文件并执行图片重复度 Alpha 比对")
    parser.add_argument("files", nargs="+", help="2-5 份 DOCX/PDF 文件")
    parser.add_argument("-o", "--output", default="output/image_compare.json", help="结果 JSON")
    parser.add_argument(
        "--thresholds",
        default=str(ROOT / "configs" / "thresholds.yaml"),
        help="图片相似度阈值配置",
    )
    args = parser.parse_args()

    if not 2 <= len(args.files) <= 5:
        parser.error("图片比对需要 2-5 份文档")

    docs = [parse_document(Path(raw)) for raw in args.files]
    config = load_image_compare_config(args.thresholds)
    result = compare_image_set(docs, config=config)

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK compared={len(docs)} pair_summaries={len(result.pair_summaries)} findings={len(result.findings)}")
    for summary in result.pair_summaries:
        print(
            "PAIR "
            f"{summary.document_a_filename} <-> {summary.document_b_filename} | "
            f"exact={summary.exact_pairs} high_similar={summary.high_similar_pairs} "
            f"max={summary.max_similarity:.3f} "
            f"repeat_a={summary.document_a.repeated_rate:.2%} "
            f"repeat_b={summary.document_b.repeated_rate:.2%}"
        )
    print(f"OUTPUT {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
