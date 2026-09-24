from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.analysis import analyze_ai_likelihood
from bid_compare_agent.check import check_document_format
from bid_compare_agent.compare import compare_document_set, compare_image_set
from bid_compare_agent.parser import parse_document
from bid_compare_agent.scoring import score_document_set
from bid_compare_agent.utils.config import (
    load_ai_likelihood_config,
    load_image_compare_config,
    load_text_compare_config,
    load_unified_scoring_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="执行多文档比对并生成统一风险评分")
    parser.add_argument("files", nargs="+", help="2-5 份 DOCX/PDF 文档")
    parser.add_argument("-o", "--output", default="output/scoring.json", help="评分结果 JSON")
    parser.add_argument(
        "--thresholds",
        default=str(ROOT / "configs" / "thresholds.yaml"),
        help="检测阈值配置",
    )
    parser.add_argument(
        "--scoring",
        default=str(ROOT / "configs" / "scoring.yaml"),
        help="评分权重与风险等级配置",
    )
    args = parser.parse_args()
    if not 2 <= len(args.files) <= 5:
        parser.error("统一多文档评分需要 2-5 份文档")

    documents = [parse_document(Path(raw)) for raw in args.files]
    text_result = compare_document_set(documents, load_text_compare_config(args.thresholds))
    image_result = compare_image_set(documents, load_image_compare_config(args.thresholds))
    format_results = [check_document_format(document) for document in documents]
    ai_result = analyze_ai_likelihood(documents, load_ai_likelihood_config(args.thresholds))
    result = score_document_set(
        documents,
        text_result=text_result,
        image_result=image_result,
        format_results=format_results,
        ai_result=ai_result,
        config=load_unified_scoring_config(args.scoring),
    )

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"OK scored={len(documents)} aggregate={result.aggregate_score_100:.2f} "
        f"risk={result.aggregate_risk_level}"
    )
    print(f"OUTPUT {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
