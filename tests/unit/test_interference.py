from bid_compare_agent.models.document_ir import DocumentIR, FormatMeta, ParagraphIR, SourceLocator
from bid_compare_agent.preprocess import classify_interference


def _doc(paragraphs):
    return DocumentIR(
        schema_version="1.0.0",
        document_id="doc-test",
        filename="x.docx",
        file_type="docx",
        file_size_bytes=1,
        sha256="a" * 64,
        page_count=None,
        paragraphs=paragraphs,
        format_meta=FormatMeta(),
    )


def test_interference_detects_heading_and_standard_response():
    doc = _doc([
        ParagraphIR(id="p1", text="技术方案", order=0, heading_level=1, source_locator=SourceLocator(kind="docx_paragraph", paragraph_index=0)),
        ParagraphIR(id="p2", text="我方完全响应招标要求，并承诺按合同约定完成全部建设内容。", order=1, source_locator=SourceLocator(kind="docx_paragraph", paragraph_index=1)),
    ])
    result = classify_interference(doc)
    assert len(result.items) == 2
    assert {x.category for x in result.items} == {"heading", "standard_response"}
