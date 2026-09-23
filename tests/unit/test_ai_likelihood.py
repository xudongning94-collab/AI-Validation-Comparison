from bid_compare_agent.analysis import AILikelihoodConfig, analyze_ai_likelihood
from bid_compare_agent.models.document_ir import DocumentIR, ParagraphIR, SourceLocator


STRUCTURED = (
    "首先，我们将通过统一平台实现业务协同，全面提升服务效率。"
    "其次，我们将通过统一流程实现资源整合，全面保障项目质量。"
    "此外，我们将通过统一机制实现持续优化，全面提升管理水平。"
    "最后，我们将通过统一标准实现闭环管理，全面保障系统稳定。"
)


def _document(*paragraphs: ParagraphIR) -> DocumentIR:
    return DocumentIR(
        schema_version="1.0.0",
        document_id="doc-test",
        filename="test.docx",
        file_type="docx",
        file_size_bytes=100,
        sha256="a" * 64,
        page_count=1,
        paragraphs=list(paragraphs),
    )


def test_structured_long_paragraph_produces_explainable_signal():
    paragraph = ParagraphIR(
        id="p-1",
        text=STRUCTURED,
        order=0,
        source_locator=SourceLocator(kind="paragraph", paragraph_index=0),
    )
    result = analyze_ai_likelihood([_document(paragraph)], AILikelihoodConfig(min_chars=40))

    assert len(result.paragraph_scores) == 1
    score = result.paragraph_scores[0]
    assert score.score >= 0.55
    assert score.confidence >= 0.35
    assert set(score.signals) == {
        "sentence_uniformity",
        "transition_density",
        "generic_phrase_density",
        "repeated_phrase_ratio",
        "punctuation_uniformity",
    }
    assert result.findings
    assert result.findings[0].metadata["non_diagnostic"] is True


def test_heading_and_short_paragraphs_are_excluded():
    heading = ParagraphIR(
        id="p-heading",
        text="技术方案",
        order=0,
        heading_level=1,
        source_locator=SourceLocator(kind="paragraph", paragraph_index=0),
    )
    short = ParagraphIR(
        id="p-short",
        text="现场实施。",
        order=1,
        source_locator=SourceLocator(kind="paragraph", paragraph_index=1),
    )
    result = analyze_ai_likelihood([_document(heading, short)])

    assert result.paragraph_scores == []
    assert result.documents[0].eligible_paragraphs == 0
    assert result.metadata["excluded_paragraphs"] == 2


def test_finding_id_is_stable():
    paragraph = ParagraphIR(
        id="p-1",
        text=STRUCTURED,
        order=0,
        source_locator=SourceLocator(kind="paragraph", paragraph_index=0),
    )
    config = AILikelihoodConfig(min_chars=40)
    first = analyze_ai_likelihood([_document(paragraph)], config)
    second = analyze_ai_likelihood([_document(paragraph)], config)

    assert first.findings[0].finding_id == second.findings[0].finding_id
