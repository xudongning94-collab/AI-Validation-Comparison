from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .document_ir import SourceLocator


@dataclass
class Finding:
    finding_id: str
    type: str
    severity: str
    document_id: str
    source_locator: SourceLocator
    summary: str
    peer_document_id: str | None = None
    peer_source_locator: SourceLocator | None = None
    score: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        peer_locator = data.get("peer_source_locator")
        return cls(
            finding_id=str(data["finding_id"]),
            type=str(data["type"]),
            severity=str(data["severity"]),
            document_id=str(data["document_id"]),
            source_locator=SourceLocator(**dict(data["source_locator"])),
            summary=str(data["summary"]),
            peer_document_id=(
                str(data["peer_document_id"]) if data.get("peer_document_id") is not None else None
            ),
            peer_source_locator=(SourceLocator(**dict(peer_locator)) if peer_locator is not None else None),
            score=float(data["score"]) if data.get("score") is not None else None,
            evidence=dict(data.get("evidence") or {}),
            metadata=dict(data.get("metadata") or {}),
        )
