from __future__ import annotations

from bid_compare_agent.vision.signature_fields import (
    SignatureFieldLocatorConfig,
    locate_signature_fields,
)


def _item(item_id: str, text: str, x: float, y: float, w: float, h: float) -> dict:
    return {
        "id": item_id,
        "text": text,
        "confidence": 0.99,
        "bbox": {"x": x, "y": y, "w": w, "h": h},
    }


def test_locates_explicit_signature_field_with_local_seal_and_date_context() -> None:
    result = locate_signature_fields(
        [
            _item("title", "法定代表人授权委托书及委托代理人的身份证复印件", 283, 167, 730, 28),
            _item("anchor", "法定代表人签字或签章：", 239, 730, 259, 25),
            _item("seal", "供应商名称（公章）：多伦科技股份有限公司", 238, 779, 485, 25),
            _item("date-left", "日", 238, 826, 25, 30),
            _item("date-right", "期：2020年6月19日", 388, 829, 207, 24),
        ],
        page_number=8,
        canvas={"width": 1241, "height": 1754},
    )

    assert result["status"] == "ok"
    assert result["count"] == 1
    field = result["fields"][0]
    assert field["cues"] == ["role_signature_anchor", "company_seal", "date"]
    assert field["field_status"] == "candidate"
    assert field["handwritten_status"] == "not_evaluated"
    assert field["confidence"] >= 0.9
    assert field["signature_roi"]["x"] >= 450
    assert field["signature_roi"]["y"] <= 730
    assert field["signature_roi"]["x"] + field["signature_roi"]["w"] <= 1241
    assert result["metadata"]["handwritten_presence_evaluated"] is False


def test_rejects_page_level_keyword_cooccurrence_without_a_local_field() -> None:
    result = locate_signature_fields(
        [
            _item("role", "法定代表人资格说明", 80, 90, 220, 24),
            _item("instruction", "需签字及供应商单位盖章", 470, 980, 290, 25),
            _item("date", "日期：2020年6月19日", 900, 1500, 220, 24),
        ],
        page_number=2,
        canvas={"width": 1241, "height": 1754},
    )

    assert result["count"] == 0
    assert result["fields"] == []


def test_merges_adjacent_same_line_role_and_signature_text_only() -> None:
    result = locate_signature_fields(
        [
            _item("role", "授权代表人", 200, 700, 140, 30),
            _item("signature", "签字：", 350, 702, 80, 28),
            _item("seal", "投标人名称（盖章）：", 200, 755, 260, 30),
            _item("date", "日期：2026年10月3日", 200, 810, 260, 30),
            _item("far-signature", "签名", 900, 1300, 60, 30),
        ],
        page_number=3,
        canvas={"width": 1241, "height": 1754},
    )

    assert result["count"] == 1
    assert result["fields"][0]["evidence_ids"][:2] == ["role", "signature"]


def test_explicit_anchor_without_field_marker_or_local_context_stays_out() -> None:
    config = SignatureFieldLocatorConfig(minimum_confidence=0.8)
    result = locate_signature_fields(
        [_item("narrative", "法定代表人应当签字确认上述事项", 100, 300, 420, 28)],
        page_number=4,
        canvas={"width": 1241, "height": 1754},
        config=config,
    )

    assert result["count"] == 0


def test_combined_seal_and_date_context_is_listed_once_as_evidence() -> None:
    result = locate_signature_fields(
        [
            _item("anchor", "委托代理人签名：", 180, 700, 220, 30),
            _item("context", "投标人名称（盖章）：某公司 日期：2026年10月3日", 180, 760, 520, 30),
        ],
        page_number=5,
        canvas={"width": 1241, "height": 1754},
    )

    evidence_ids = result["fields"][0]["evidence_ids"]
    assert evidence_ids == ["anchor", "context"]
