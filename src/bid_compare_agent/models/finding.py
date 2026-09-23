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
