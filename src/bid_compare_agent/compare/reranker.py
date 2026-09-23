from __future__ import annotations

from typing import Protocol


class SemanticReranker(Protocol):
    """可插拔语义精排接口。

    D3 Alpha 默认不依赖外部 Embedding 服务。后续可通过 HTTP/SDK 实现本协议，
    HiAgent 无需感知底层模型差异。
    """

    name: str

    def score(self, source_text: str, peer_text: str) -> float:
        """返回 0~1 的语义相似度。"""
        ...
