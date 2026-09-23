from bid_compare_agent.models.ai_likelihood import AILikelihoodResult, DocumentAILikelihoodStats
from bid_compare_agent.models.document_ir import DocumentIR
from bid_compare_agent.models.text_compare import (
    DocumentTextStats,
    TextComparisonResult,
    TextPairSummary,
)
from bid_compare_agent.scoring import UnifiedScoreConfig, classify_risk, score_document_set


def _document(document_id: str, filename: str, sha: str) -> DocumentIR:
    return DocumentIR(
        schema_version="1.0.0",
        document_id=document_id,
        filename=filename,
        file_type="docx",
        file_size_bytes=100,
        sha256=sha * 64,
        page_count=1,
    )


def _text_result() -> TextComparisonResult:
    stats_a = DocumentTextStats(
        document_id="doc-a",
        filename="a.docx",
        eligible_paragraphs=10,
        total_chars=1000,
        repeated_paragraphs_high=4,
        repeated_chars_high=600,
        repeated_rate_high=0.60,
    )
    stats_b = DocumentTextStats(
        document_id="doc-b",
        filename="b.docx",
        eligible_paragraphs=10,
        total_chars=1000,
        repeated_paragraphs_high=4,
        repeated_chars_high=600,
        repeated_rate_high=0.60,
    )
    return TextComparisonResult(
        schema_version="1.0.0",
        compare_type="text_similarity",
        documents=[],
        pair_summaries=[
            TextPairSummary(
                document_a_id="doc-a",
                document_b_id="doc-b",
                document_a_filename="a.docx",
                document_b_filename="b.docx",
                high_pairs=4,
                medium_pairs=0,
                max_similarity=1.0,
                document_a=stats_a,
                document_b=stats_b,
            )
        ],
    )


def _ai_result() -> AILikelihoodResult:
    return AILikelihoodResult(
        schema_version="1.0.0",
        analysis_type="ai_likelihood",
        method="test",
        documents=[
            DocumentAILikelihoodStats("doc-a", "a.docx", 3, 1, 0, 500, 0.30, 0.70),
            DocumentAILikelihoodStats("doc-b", "b.docx", 3, 1, 0, 500, 0.30, 0.70),
        ],
    )


def test_missing_dimensions_are_excluded_and_weights_are_renormalized():
    documents = [_document("doc-a", "a.docx", "a"), _document("doc-b", "b.docx", "b")]
    result = score_document_set(documents, text_result=_text_result(), ai_result=_ai_result())
    dimensions = result.documents[0].dimensions
    applicable = [item for item in dimensions if item.applicable]

    assert {item.name for item in applicable} == {"text_similarity", "ai_likelihood"}
    assert abs(sum(item.effective_weight for item in applicable) - 1.0) < 1e-6
    assert result.documents[0].score == 0.518182
    assert result.metadata["missing_dimension_policy"] == "renormalize_applicable_weights"


def test_no_applicable_dimension_is_minimal_zero():
    document = _document("doc-a", "a.docx", "a")
    result = score_document_set([document])

    assert result.documents[0].score == 0.0
    assert result.documents[0].risk_level == "minimal"
    assert all(item.effective_weight == 0.0 for item in result.documents[0].dimensions)


def test_risk_threshold_boundaries():
    config = UnifiedScoreConfig()
    assert classify_risk(0.19, config) == "minimal"
    assert classify_risk(0.20, config) == "low"
    assert classify_risk(0.40, config) == "medium"
    assert classify_risk(0.65, config) == "high"
    assert classify_risk(0.85, config) == "critical"


def test_invalid_scoring_thresholds_are_rejected():
    try:
        UnifiedScoreConfig(low_threshold=0.5, medium_threshold=0.4)
    except ValueError as exc:
        assert "风险阈值" in str(exc)
    else:
        raise AssertionError("invalid thresholds must be rejected")
