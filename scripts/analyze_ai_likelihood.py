from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.analysis import analyze_ai_likelihood
from bid_compare_agent.parser import parse_document
from bid_compare_agent.utils.config import load_ai_likelihood_config


def main() -> int:
    parser = argparse.ArgumentParser(description="分析投标文档中的 AI 疑似风格信号（辅助分析 Alpha）")
    parser.add_argument("files", nargs="+", help="1-5 份 DOCX/PDF 文档")
    parser.add_argument("-o", "--output", default="output/ai_likelihood.json", help="结果 JSON")
    parser.add_argument(
        "--thresholds",
        default=str(ROOT / "configs" / "thresholds.yaml"),
        help="AI 疑似度阈值配置",
    )
    args = parser.parse_args()

    if not 1 <= len(args.files) <= 5:
        parser.error("AI 疑似度分析需要 1-5 份文档")

    documents = [parse_document(Path(raw)) for raw in args.files]
    result = analyze_ai_likelihood(documents, load_ai_likelihood_config(args.thresholds))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"OK analyzed={len(documents)} paragraphs={len(result.paragraph_scores)} "
        f"findings={len(result.findings)}"
    )
    print("NOTICE AI 疑似度为辅助信号，不构成 AI 生成的确定性结论")
    print(f"OUTPUT {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
