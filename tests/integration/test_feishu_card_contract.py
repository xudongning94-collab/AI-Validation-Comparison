from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_feishu_card_template_matches_v2_contract() -> None:
    template = json.loads(
        (PROJECT_ROOT / "hiagent" / "feishu_card.template.json").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "feishu_card_template.schema.json").read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(template)
    assert template["schema"] == "2.0"
    assert template["body"]["elements"]


def test_feishu_card_keeps_safety_notice_and_no_secrets() -> None:
    content = (PROJECT_ROOT / "hiagent" / "feishu_card.template.json").read_text(
        encoding="utf-8"
    )

    assert "不构成违规结论" in content
    assert "非诊断性辅助信号" in content
    assert "人工复核" in content
    assert "access_token" not in content
    assert "webhook" not in content.lower()


def test_feishu_acceptance_checklist_covers_release_gates() -> None:
    checklist = (PROJECT_ROOT / "hiagent" / "ACCEPTANCE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )

    assert "源文件运行前后 SHA-256 不变" in checklist
    assert "PC 和移动端" in checklist
    assert "Prompt、工作流和卡片模板版本" in checklist
    assert "回滚方式" in checklist
