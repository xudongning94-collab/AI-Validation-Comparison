from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from bid_compare_agent.models.document_ir import DocumentIR

from .models import PageEvidence, SignatureRequirement, VisualCandidate


def _tuple_strings(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} 必须是字符串数组")
    return tuple(item.strip() for item in value if item.strip())


def _tuple_pages(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("allowed_pages 必须是正整数数组")
    try:
        pages = tuple(int(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError("allowed_pages 必须是正整数数组") from exc
    if any(page < 1 for page in pages):
        raise ValueError("allowed_pages 必须是正整数数组")
    return pages


def _optional_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD") from exc


def _boolean(value: Any, field: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{field} 必须是布尔值")
    return value


def _number(value: Any, field: str, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是数字")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是数字") from exc


def requirements_from_payload(payload: Any) -> list[SignatureRequirement]:
    if isinstance(payload, dict):
        raw_rules = payload.get("requirements")
    else:
        raw_rules = payload
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("签署规则必须是非空 requirements 数组")
    requirements: list[SignatureRequirement] = []
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ValueError(f"requirements[{index}] 必须是对象")
        requirements.append(
            SignatureRequirement(
                rule_id=str(raw.get("rule_id", "")).strip(),
                title=str(raw.get("title", "")).strip(),
                expected_company_names=_tuple_strings(
                    raw.get("expected_company_names"),
                    f"requirements[{index}].expected_company_names",
                ),
                expected_signer_names=_tuple_strings(
                    raw.get("expected_signer_names"),
                    f"requirements[{index}].expected_signer_names",
                ),
                signer_role=(
                    str(raw["signer_role"]).strip()
                    if raw.get("signer_role") not in (None, "")
                    else None
                ),
                require_signature=_boolean(
                    raw.get("require_signature"),
                    f"requirements[{index}].require_signature",
                    True,
                ),
                require_seal=_boolean(
                    raw.get("require_seal"),
                    f"requirements[{index}].require_seal",
                    True,
                ),
                require_date=_boolean(
                    raw.get("require_date"),
                    f"requirements[{index}].require_date",
                    True,
                ),
                allowed_pages=_tuple_pages(raw.get("allowed_pages")),
                anchor_terms=_tuple_strings(
                    raw.get("anchor_terms"),
                    f"requirements[{index}].anchor_terms",
                ),
                date_not_before=_optional_date(
                    raw.get("date_not_before"),
                    f"requirements[{index}].date_not_before",
                ),
                date_not_after=_optional_date(
                    raw.get("date_not_after"),
                    f"requirements[{index}].date_not_after",
                ),
                minimum_candidate_confidence=_number(
                    raw.get("minimum_candidate_confidence"),
                    f"requirements[{index}].minimum_candidate_confidence",
                    0.65,
                ),
                minimum_text_confidence=_number(
                    raw.get("minimum_text_confidence"),
                    f"requirements[{index}].minimum_text_confidence",
                    0.82,
                ),
            )
        )
    rule_ids = [item.rule_id for item in requirements]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("签署规则 rule_id 不能重复")
    return requirements


def _candidate_from_dict(raw: dict[str, Any], page_number: int, index: int) -> VisualCandidate:
    bbox = raw.get("bbox")
    if not isinstance(bbox, dict):
        raise ValueError("视觉候选 bbox 必须是对象")
    if set(bbox) != {"x", "y", "w", "h"}:
        raise ValueError("视觉候选 bbox 必须且只能包含 x/y/w/h")
    quality_flags = _tuple_strings(raw.get("quality_flags"), "quality_flags")
    return VisualCandidate(
        candidate_id=str(raw.get("candidate_id") or f"candidate-{page_number}-{index}"),
        kind=str(raw.get("kind", "")),
        page_number=page_number,
        bbox={
            key: _number(bbox[key], f"视觉候选 bbox.{key}")
            for key in ("x", "y", "w", "h")
        },
        confidence=_number(raw.get("confidence"), "视觉候选 confidence", 0.0),
        recognized_text=(
            str(raw["recognized_text"]).strip()
            if raw.get("recognized_text") not in (None, "")
            else None
        ),
        quality_flags=quality_flags,
        detector=str(raw.get("detector", "external-worker")),
    )


def _native_pages(document: DocumentIR) -> dict[int, list[str]]:
    pages: dict[int, list[str]] = {}
    for paragraph in document.paragraphs:
        page = paragraph.source_locator.page if paragraph.source_locator else None
        page_number = int(page or 1)
        pages.setdefault(page_number, []).append(paragraph.text)
    for table in document.tables:
        page = table.source_locator.page if table.source_locator else None
        page_number = int(page or 1)
        text = " ".join(cell for row in table.rows for cell in row if cell)
        if text:
            pages.setdefault(page_number, []).append(text)
    if not pages:
        page_count = int(document.page_count or 1)
        for page_number in range(1, page_count + 1):
            pages.setdefault(page_number, [])
    return pages


def page_evidence_from_document(
    document: DocumentIR,
    evidence_payload: dict[str, Any] | None = None,
) -> list[PageEvidence]:
    payload = evidence_payload or {}
    declared_document_id = payload.get("document_id")
    if declared_document_id and str(declared_document_id) != document.document_id:
        raise ValueError("视觉证据 document_id 与上传文件不一致")
    raw_pages = payload.get("pages", [])
    if not isinstance(raw_pages, list):
        raise ValueError("视觉证据 pages 必须是数组")

    external: dict[int, dict[str, Any]] = {}
    for index, raw in enumerate(raw_pages):
        if not isinstance(raw, dict):
            raise ValueError(f"pages[{index}] 必须是对象")
        page_value = raw.get("page_number")
        if isinstance(page_value, bool) or not isinstance(page_value, int):
            raise ValueError("视觉证据页码必须是唯一正整数")
        page_number = page_value
        if page_number < 1 or page_number in external:
            raise ValueError("视觉证据页码必须是唯一正整数")
        external[page_number] = raw

    native = _native_pages(document)
    page_numbers = sorted(set(native) | set(external))
    pages: list[PageEvidence] = []
    for page_number in page_numbers:
        raw = external.get(page_number, {})
        raw_ocr = raw.get("ocr_items", [])
        raw_candidates = raw.get("candidates", [])
        if not isinstance(raw_ocr, list) or not all(isinstance(item, dict) for item in raw_ocr):
            raise ValueError(f"第 {page_number} 页 ocr_items 必须是对象数组")
        if not isinstance(raw_candidates, list) or not all(
            isinstance(item, dict) for item in raw_candidates
        ):
            raise ValueError(f"第 {page_number} 页 candidates 必须是对象数组")
        pages.append(
            PageEvidence(
                page_number=page_number,
                native_text="\n".join(native.get(page_number, [])),
                ocr_items=tuple(dict(item) for item in raw_ocr),
                candidates=tuple(
                    _candidate_from_dict(item, page_number, index)
                    for index, item in enumerate(raw_candidates)
                ),
                company_names=_tuple_strings(raw.get("company_names"), "company_names"),
                person_names=_tuple_strings(raw.get("person_names"), "person_names"),
                date_values=_tuple_strings(raw.get("date_values"), "date_values"),
                ocr_status=str(raw.get("ocr_status", "not_run")),
                vision_status=str(raw.get("vision_status", "not_run")),
            )
        )
    return pages
