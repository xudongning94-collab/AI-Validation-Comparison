from __future__ import annotations

from pathlib import Path
from typing import Any

from bid_compare_agent.analysis import analyze_ai_likelihood
from bid_compare_agent.annotate import annotate_docx
from bid_compare_agent.check import check_document_format
from bid_compare_agent.compliance import (
    check_signature_compliance,
    page_evidence_from_document,
    requirements_from_payload,
)
from bid_compare_agent.compare import compare_document_set, compare_image_set
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.parser import parse_document
from bid_compare_agent.preprocess import classify_interference
from bid_compare_agent.reporting import generate_deterministic_report
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

    @staticmethod
    def signature_check(
        path: str | Path,
        requirements_payload: Any,
        evidence_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document = parse_document(path)
        requirements = requirements_from_payload(requirements_payload)
        pages = page_evidence_from_document(document, evidence_payload)
        return check_signature_compliance(
            document.document_id,
            pages,
            requirements,
        ).to_dict()

    def ai_check(self, paths: list[Path]) -> dict[str, Any]:
        documents = [parse_document(path) for path in paths]
        return analyze_ai_likelihood(
            documents,
            load_ai_likelihood_config(self.thresholds_path),
        ).to_dict()

    def analyze(self, paths: list[Path]) -> dict[str, Any]:
        """解析一次并完成全维度分析、评分和确定性报告。"""
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
        scoring = score_document_set(
            documents,
            text_result=text_result,
            image_result=image_result,
            format_results=format_results,
            ai_result=ai_result,
            config=load_unified_scoring_config(self.scoring_path),
        )

        findings_by_id: dict[str, Finding] = {}
        for finding in text_result.findings:
            findings_by_id.setdefault(finding.finding_id, finding)
        for finding in image_result.findings:
            findings_by_id.setdefault(finding.finding_id, finding)
        for result in format_results:
            for finding in result.findings:
                findings_by_id.setdefault(finding.finding_id, finding)
        for finding in ai_result.findings:
            findings_by_id.setdefault(finding.finding_id, finding)
        findings = list(findings_by_id.values())
        report = generate_deterministic_report(scoring, findings)

        return {
            "schema_version": "1.0.0",
            "analysis_type": "complete_analysis",
            "documents": [
                {
                    "document_id": document.document_id,
                    "filename": document.filename,
                    "file_type": document.file_type,
                    "sha256": document.sha256,
                }
                for document in documents
            ],
            "results": {
                "text_comparison": text_result.to_dict(),
                "image_comparison": image_result.to_dict(),
                "format_checks": [result.to_dict() for result in format_results],
                "ai_likelihood": ai_result.to_dict(),
                "scoring": scoring.to_dict(),
            },
            "findings": [finding.to_dict() for finding in findings],
            "report": report,
            "metadata": {
                "report_method": "deterministic-report-v1",
                "parsed_once": True,
                "ai_likelihood_non_diagnostic": True,
            },
        }

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
