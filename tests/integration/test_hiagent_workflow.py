from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_hiagent_workflow_matches_schema_and_graph() -> None:
    workflow = json.loads(
        (PROJECT_ROOT / "hiagent" / "workflow.spec.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "hiagent_workflow.schema.json").read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator(schema).validate(workflow)

    node_ids = [node["id"] for node in workflow["nodes"]]
    assert len(node_ids) == len(set(node_ids))
    assert workflow["entry_node"] in node_ids
    for transition in workflow["transitions"]:
        assert transition["from"] in node_ids
        assert transition["to"] in node_ids


def test_hiagent_workflow_uses_aggregate_analysis_and_safety_policies() -> None:
    workflow = json.loads(
        (PROJECT_ROOT / "hiagent" / "workflow.spec.json").read_text(encoding="utf-8")
    )
    aggregate = next(node for node in workflow["nodes"] if node["id"] == "analyze_bundle")

    assert aggregate["path"] == "/v1/analyze"
    assert aggregate["file_field"] == "files"
    assert aggregate["report_mode"] == "local_deterministic"
    assert aggregate["provides"] == ["findings", "report", "scoring", "task"]
    assert workflow["policies"]["privacy"]["log_file_content"] is False
    assert workflow["policies"]["privacy"]["retain_uploaded_files"] is False
    assert workflow["policies"]["ai_likelihood"] == {
        "diagnostic": False,
        "requires_human_review": True,
    }
