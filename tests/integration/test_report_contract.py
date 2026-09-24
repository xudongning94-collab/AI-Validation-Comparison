from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_report_example_matches_structured_output_schema() -> None:
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "report.schema.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (PROJECT_ROOT / "hiagent" / "examples" / "report.example.json").read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    assert report["requires_human_review"] is True
    assert all(len(item["related_finding_ids"]) <= 5 for item in report["recommended_actions"])


def test_report_prompt_contains_non_diagnostic_and_traceability_guardrails() -> None:
    prompt = (PROJECT_ROOT / "prompts" / "report_generation.md").read_text(
        encoding="utf-8"
    )

    assert "不得创建新 ID" in prompt
    assert "非诊断性" in prompt
    assert "不等同于抄袭、串标、违规" in prompt
    assert "不得大段复述原文" in prompt
    assert "schemas/report.schema.json" in prompt
