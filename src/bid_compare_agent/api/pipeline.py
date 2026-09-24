from __future__ import annotations

from pathlib import Path
from typing import Any

from bid_compare_agent.analysis import analyze_ai_likelihood
from bid_compare_agent.annotate import annotate_docx
from bid_compare_agent.check import check_document_format
from bid_compare_agent.compare import compare_document_set, compare_image_set
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.parser import parse_document
from bid_compare_agent.preprocess import classify_interference
from bid_compare_agent.scoring import score_document_set
from bid_compare_agent.utils.config import (
    load_ai_likelihood_config,
    load_docx_annotation_config,
    load_image_compare_config,
    load_text_compare_config,
    load_unified_scoring_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def findings_from_payload(payload: Any) -> list[Finding]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("findings"), list):
        items = payload["findings"]
    else:
        raise ValueError("Finding JSON 必须是数组，或包含 findings 数组的对象")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("findings 数组中的每一项都必须是对象")
    return [Finding.from_dict(item) for item in items]


class ApiPipeline:
    def __init__(
        self,
        *,
        thresholds_path: str | Path | None = None,
        scoring_path: str | Path | None = None,
        annotation_path: str | Path | None = None,
    ) -> None:
        config_dir = PROJECT_ROOT / "configs"
        self.thresholds_path = Path(thresholds_path or config_dir / "thresholds.yaml")
        self.scoring_path = Path(scoring_path or config_dir / "scoring.yaml")
        self.annotation_path = Path(annotation_path or config_dir / "annotation.yaml")

    @staticmethod
    def parse(path: str | Path) -> dict[str, Any]:
        return parse_document(path).to_dict()

    @staticmethod
    def preprocess(path: str | Path) -> dict[str, Any]:
        document = parse_document(path)
        return {
            "document": document.to_dict(),
            "interference": classify_interference(document).to_dict(),
        }

    def text_compare(self, paths: list[Path]) -> dict[str, Any]:
        documents = [parse_document(path) for path in paths]
        return compare_document_set(
            documents,
            load_text_compare_config(self.thresholds_path),
        ).to_dict()

    def image_compare(self, paths: list[Path]) -> dict[str, Any]:
        documents = [parse_document(path) for path in paths]
        return compare_image_set(
            documents,
            load_image_compare_config(self.thresholds_path),
        ).to_dict()

    @staticmethod
    def format_check(paths: list[Path]) -> dict[str, Any]:
        results = [check_document_format(parse_document(path)).to_dict() for path in paths]
        return {
            "schema_version": "1.0.0",
            "check_type": "format_check",
            "documents": results,
            "summary": {
                "document_count": len(results),
                "finding_count": sum(len(result["findings"]) for result in results),
            },
        }

    def ai_check(self, paths: list[Path]) -> dict[str, Any]:
        documents = [parse_document(path) for path in paths]
        return analyze_ai_likelihood(
            documents,
            load_ai_likelihood_config(self.thresholds_path),
        ).to_dict()

    def score(self, paths: list[Path]) -> dict[str, Any]:
        documents = [parse_document(path) for path in paths]
        text_result = compare_document_set(
            documents,
            load_text_compare_config(self.thresholds_path),
        )
        image_result = compare_image_set(
            documents,
            load_image_compare_config(self.thresholds_path),
        )
        format_results = [check_document_format(document) for document in documents]
        ai_result = analyze_ai_likelihood(
            documents,
            load_ai_likelihood_config(self.thresholds_path),
        )
        return score_document_set(
            documents,
            text_result=text_result,
            image_result=image_result,
            format_results=format_results,
            ai_result=ai_result,
            config=load_unified_scoring_config(self.scoring_path),
        ).to_dict()

    def annotate(
        self,
        source_path: str | Path,
        output_path: str | Path,
        findings: list[Finding],
    ) -> dict[str, Any]:
        return annotate_docx(
            source_path,
            output_path,
            findings,
            load_docx_annotation_config(self.annotation_path),
        ).to_dict()
