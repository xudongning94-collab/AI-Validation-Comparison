import json
from pathlib import Path

from jsonschema import validate

from bid_compare_agent.models.document_ir import DocumentIR
from bid_compare_agent.scoring import score_document_set


def test_scoring_result_matches_schema():
    document = DocumentIR(
        schema_version="1.0.0",
        document_id="doc-schema",
        filename="schema.docx",
        file_type="docx",
        file_size_bytes=100,
        sha256="c" * 64,
        page_count=1,
    )
    result = score_document_set([document])
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "scoring.schema.json"
    validate(result.to_dict(), json.loads(schema_path.read_text(encoding="utf-8")))
