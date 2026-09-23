import json
from pathlib import Path

from docx import Document
from jsonschema import Draft202012Validator

from bid_compare_agent.compare import TextCompareConfig, compare_document_set
from bid_compare_agent.parser import parse_document


ROOT = Path(__file__).resolve().parents[2]


def test_text_compare_result_matches_schema(tmp_path: Path):
    common = "本方案通过统一接口和标准化数据模型实现多系统协同，保障项目平稳实施并持续优化运营能力。"
    docs = []
    for name in ("a.docx", "b.docx"):
        path = tmp_path / name
        doc = Document()
        doc.add_paragraph(common)
        doc.save(path)
        docs.append(parse_document(path))

    result = compare_document_set(docs, TextCompareConfig(min_chars=10)).to_dict()
    schema = json.loads((ROOT / "schemas" / "text_compare.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(result)
