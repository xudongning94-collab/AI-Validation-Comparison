from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


_ROLE = r"(?:法定代表人|授权代表人?|委托代理人|供应商代表|投标人代表|申请人代表|负责人)"
_SIGNATURE = r"(?:(?:手书)?(?:签字|签名)|签章)"
_ANCHOR_PATTERNS = (
    re.compile(_ROLE + r".{0,12}" + _SIGNATURE),
    re.compile(_SIGNATURE + r".{0,12}" + _ROLE),
)
_COMPANY_SEAL_PATTERNS = (
    re.compile(r"(?:供应商|投标人|申请人|单位|公司)(?:名称)?.{0,10}(?:公章|盖章)"),
    re.compile(r"(?:公章|盖章).{0,10}(?:供应商|投标人|申请人|单位|公司)"),
)
_DATE_PATTERN = re.compile(r"(?:日期|年\s*月\s*日|\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)")


@dataclass(frozen=True)
class SignatureFieldLocatorConfig:
    minimum_confidence: float = 0.80
    maximum_same_line_gap_ratio: float = 0.04
    maximum_context_vertical_distance_ratio: float = 0.09
    maximum_context_horizontal_offset_ratio: float = 0.18
    roi_right_margin_ratio: float = 0.05
    roi_minimum_height_ratio: float = 0.035
    roi_maximum_height_ratio: float = 0.08

    def __post_init__(self) -> None:
        for name in (
            "minimum_confidence",
            "maximum_same_line_gap_ratio",
            "maximum_context_vertical_distance_ratio",
            "maximum_context_horizontal_offset_ratio",
            "roi_right_margin_ratio",
            "roi_minimum_height_ratio",
            "roi_maximum_height_ratio",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be a number")
            if not math.isfinite(float(value)) or not 0 < float(value) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.roi_minimum_height_ratio > self.roi_maximum_height_ratio:
            raise ValueError("roi_minimum_height_ratio must not exceed roi_maximum_height_ratio")

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> SignatureFieldLocatorConfig:
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("signature field locator config must be an object")
        allowed = set(cls.__dataclass_fields__)
        unexpected = set(value) - allowed
        if unexpected:
            raise ValueError(f"unsupported signature field locator config keys: {sorted(unexpected)}")
        return cls(**{key: float(item) for key, item in value.items()})


@dataclass(frozen=True)
class _Item:
    item_id: str
    text: str
    confidence: float
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2


def _number(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field} must be a {qualifier} finite number")
    return number


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("(", "（").replace(")", "）")


def _items(raw_items: list[dict[str, Any]]) -> list[_Item]:
    if not isinstance(raw_items, list):
        raise ValueError("items must be an array")
    items: list[_Item] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ValueError(f"items[{index}] must be an object")
        item_id = str(raw.get("id") or raw.get("evidence_id") or f"text-{index:04d}")
        text = _normalize_text(str(raw.get("text") or ""))
        if not text:
            continue
        bbox = raw.get("bbox")
        if not isinstance(bbox, dict):
            raise ValueError(f"{item_id}.bbox must be an object")
        confidence = _number(raw.get("confidence", 1.0), f"{item_id}.confidence")
        if confidence > 1:
            raise ValueError(f"{item_id}.confidence must be <= 1")
        items.append(
            _Item(
                item_id=item_id,
                text=text,
                confidence=confidence,
                x=_number(bbox.get("x"), f"{item_id}.bbox.x"),
                y=_number(bbox.get("y"), f"{item_id}.bbox.y"),
                w=_number(bbox.get("w"), f"{item_id}.bbox.w", positive=True),
                h=_number(bbox.get("h"), f"{item_id}.bbox.h", positive=True),
            )
        )
    return items


def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _same_line(left: _Item, right: _Item, *, width: float, config: SignatureFieldLocatorConfig) -> bool:
    first, second = sorted((left, right), key=lambda item: item.x)
    vertical_offset = abs(first.center_y - second.center_y)
    horizontal_gap = max(0.0, second.x - first.right)
    return (
        vertical_offset <= max(first.h, second.h) * 0.65
        and horizontal_gap <= width * config.maximum_same_line_gap_ratio
    )


def _anchor_groups(
    items: list[_Item], *, width: float, config: SignatureFieldLocatorConfig
) -> list[tuple[list[_Item], str, dict[str, float]]]:
    groups: list[tuple[list[_Item], str, dict[str, float]]] = []
    for item in items:
        if _matches(_ANCHOR_PATTERNS, item.text):
            groups.append(([item], item.text, {"x": item.x, "y": item.y, "w": item.w, "h": item.h}))
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if not _same_line(left, right, width=width, config=config):
                continue
            ordered = sorted((left, right), key=lambda item: item.x)
            text = "".join(item.text for item in ordered)
            if not _matches(_ANCHOR_PATTERNS, text):
                continue
            x = min(item.x for item in ordered)
            y = min(item.y for item in ordered)
            right_edge = max(item.right for item in ordered)
            bottom = max(item.bottom for item in ordered)
            groups.append((ordered, text, {"x": x, "y": y, "w": right_edge - x, "h": bottom - y}))
    return groups


def _is_local_context(
    anchor: dict[str, float],
    item: _Item,
    *,
    width: float,
    height: float,
    config: SignatureFieldLocatorConfig,
) -> bool:
    anchor_center_y = anchor["y"] + anchor["h"] / 2
    vertical_distance = abs(item.center_y - anchor_center_y)
    horizontal_offset = abs(item.x - anchor["x"])
    horizontal_overlap = min(anchor["x"] + anchor["w"], item.right) - max(anchor["x"], item.x)
    return (
        vertical_distance <= height * config.maximum_context_vertical_distance_ratio
        and (
            horizontal_offset <= width * config.maximum_context_horizontal_offset_ratio
            or horizontal_overlap > 0
        )
    )


def _signature_roi(
    anchor: dict[str, float],
    context: list[_Item],
    *,
    width: float,
    height: float,
    config: SignatureFieldLocatorConfig,
) -> dict[str, float]:
    x = max(0.0, anchor["x"] + anchor["w"] - width * 0.015)
    right = width * (1 - config.roi_right_margin_ratio)
    if right - x < width * 0.18:
        x = max(anchor["x"], right - width * 0.18)
    y = max(0.0, anchor["y"] - anchor["h"] * 0.5)
    minimum_bottom = y + height * config.roi_minimum_height_ratio
    maximum_bottom = min(height, y + height * config.roi_maximum_height_ratio)
    following = [item.y for item in context if item.y > anchor["y"] + anchor["h"] * 0.5]
    context_bottom = min(following) - anchor["h"] * 0.2 if following else maximum_bottom
    bottom = min(maximum_bottom, max(minimum_bottom, context_bottom))
    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "w": round(max(1.0, right - x), 2),
        "h": round(max(1.0, bottom - y), 2),
    }


def locate_signature_fields(
    raw_items: list[dict[str, Any]],
    *,
    page_number: int,
    canvas: dict[str, Any],
    config: SignatureFieldLocatorConfig | None = None,
) -> dict[str, Any]:
    """Locate semantic signature fields without claiming handwriting is present."""

    if page_number < 1:
        raise ValueError("page_number must be >= 1")
    if not isinstance(canvas, dict):
        raise ValueError("canvas must be an object")
    width = _number(canvas.get("width"), "canvas.width", positive=True)
    height = _number(canvas.get("height"), "canvas.height", positive=True)
    settings = config or SignatureFieldLocatorConfig()
    items = _items(raw_items)
    fields: list[dict[str, Any]] = []
    seen_evidence: set[tuple[str, ...]] = set()
    for anchor_items, anchor_text, anchor_bbox in _anchor_groups(
        items, width=width, config=settings
    ):
        anchor_ids = tuple(item.item_id for item in anchor_items)
        if anchor_ids in seen_evidence:
            continue
        seen_evidence.add(anchor_ids)
        local_items = [
            item
            for item in items
            if item not in anchor_items
            and _is_local_context(
                anchor_bbox,
                item,
                width=width,
                height=height,
                config=settings,
            )
        ]
        seal_items = [item for item in local_items if _matches(_COMPANY_SEAL_PATTERNS, item.text)]
        date_items = [item for item in local_items if _DATE_PATTERN.search(item.text)]
        has_field_marker = any(marker in anchor_text for marker in (":", "：", "签字处", "签名处"))
        raw_score = 0.55 + 0.15 * has_field_marker + 0.15 * bool(seal_items) + 0.15 * bool(date_items)
        evidence: list[_Item] = []
        for item in [*anchor_items, *seal_items[:1], *date_items[:1]]:
            if all(existing.item_id != item.item_id for existing in evidence):
                evidence.append(item)
        score = round(min(1.0, raw_score) * min(item.confidence for item in evidence), 4)
        if score < settings.minimum_confidence:
            continue
        cues = ["role_signature_anchor"]
        if seal_items:
            cues.append("company_seal")
        if date_items:
            cues.append("date")
        fields.append(
            {
                "field_id": f"signature-field-{page_number}-{len(fields):04d}",
                "kind": "signature_field",
                "page_number": page_number,
                "anchor_bbox": {key: round(value, 2) for key, value in anchor_bbox.items()},
                "signature_roi": _signature_roi(
                    anchor_bbox,
                    [*seal_items, *date_items],
                    width=width,
                    height=height,
                    config=settings,
                ),
                "confidence": score,
                "cues": cues,
                "evidence_ids": [item.item_id for item in evidence],
                "field_status": "candidate",
                "handwritten_status": "not_evaluated",
            }
        )
    return {
        "schema_version": "1.0.0",
        "status": "ok",
        "page_number": page_number,
        "canvas": {"width": width, "height": height},
        "fields": fields,
        "count": len(fields),
        "requires_human_review": bool(fields),
        "error": None,
        "metadata": {
            "method": "signature-field-semantic-layout-v1",
            "minimum_confidence": settings.minimum_confidence,
            "handwritten_presence_evaluated": False,
        },
    }
