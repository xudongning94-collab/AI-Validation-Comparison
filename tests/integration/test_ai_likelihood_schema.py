import json
from pathlib import Path

from jsonschema import validate

from bid_compare_agent.analysis import AILikelihoodConfig, analyze_ai_likelihood
from bid_compare_agent.models.document_ir import DocumentIR, ParagraphIR, SourceLocator


def test_ai_likelihood_result_matches_schema():
    text = (
        "首先，我们通过统一机制实现协同，全面提升执行效率。"
        "其次，我们通过统一流程实现整合，全面保障实施质量。"
        "此外，我们通过统一平台持续优化，全面提升管理水平。"
        "最后，我们通过统一标准形成闭环，全面保障系统稳定。"
    )
    document = DocumentIR(
        schema_version="1.0.0",
        document_id="doc-schema",
        filename="schema.docx",
        file_type="docx",
        file_size_bytes=100,
        sha256="b" * 64,
        page_count=1,
        paragraphs=[
            ParagraphIR(
                id="p-schema",
                text=text,
                order=0,
                source_locator=SourceLocator(kind="paragraph", paragraph_index=0),
            )
        ],
    )
    result = analyze_ai_likelihood([document], AILikelihoodConfig(min_chars=40))
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "ai_likelihood.schema.json"
    validate(result.to_dict(), json.loads(schema_path.read_text(encoding="utf-8")))
