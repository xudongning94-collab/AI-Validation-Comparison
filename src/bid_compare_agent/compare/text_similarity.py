from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from typing import Iterable

from bid_compare_agent.models.document_ir import DocumentIR, ParagraphIR, SourceLocator
from bid_compare_agent.models.finding import Finding
from bid_compare_agent.preprocess.interference import classify_interference
from bid_compare_agent.models.text_compare import (
    DocumentTextStats,
    TextComparisonResult,
    TextPairSummary,
)
from .reranker import SemanticReranker


_COMPARE_CHAR_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


@dataclass(frozen=True)
class TextCompareConfig:
    medium_threshold: float = 0.60
    high_threshold: float = 0.85
    min_chars: int = 20
    max_chars: int = 6000
    ngram_min: int = 2
    ngram_max: int = 4
    recall_ngram: int = 2
    max_candidates_per_paragraph: int = 30
    min_shared_recall_tokens: int = 2
    top_matches_per_paragraph: int = 3
    apply_interference: bool = True
    interference_downweight_factor: float = 0.70

    def __post_init__(self) -> None:
        if not 0 <= self.medium_threshold <= self.high_threshold <= 1:
            raise ValueError("文本相似度阈值必须满足 0 <= medium <= high <= 1")
        if self.min_chars < 1:
            raise ValueError("min_chars 必须 >= 1")
        if self.ngram_min < 1 or self.ngram_max < self.ngram_min:
            raise ValueError("n-gram 配置无效")
        if self.recall_ngram < 1:
            raise ValueError("recall_ngram 必须 >= 1")
        if self.max_candidates_per_paragraph < 1:
            raise ValueError("max_candidates_per_paragraph 必须 >= 1")
        if self.top_matches_per_paragraph < 1:
            raise ValueError("top_matches_per_paragraph 必须 >= 1")
        if not 0 < self.interference_downweight_factor <= 1:
            raise ValueError("interference_downweight_factor 必须位于 (0, 1]")


@dataclass(frozen=True)
class _PreparedParagraph:
    paragraph: ParagraphIR
    normalized: str
    section_path: str
    weight: float = 1.0
    interference_category: str | None = None
    interference_action: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.normalized)


@dataclass(frozen=True)
class _ScoredPair:
    left: _PreparedParagraph
    right: _PreparedParagraph
    score: float
    raw_score: float
    interference_factor: float
    tfidf_cosine: float
    sequence_ratio: float
    containment: float
    semantic_score: float | None = None
    reranker_name: str | None = None


def normalize_for_compare(text: str) -> str:
    """保留中文、字母和数字，统一为紧凑小写串，便于跨标点/空格比对。"""
    return "".join(_COMPARE_CHAR_RE.findall(text)).lower()


def _char_ngrams(text: str, n_min: int, n_max: int) -> list[str]:
    grams: list[str] = []
    for n in range(n_min, n_max + 1):
        if len(text) < n:
            continue
        grams.extend(text[i : i + n] for i in range(0, len(text) - n + 1))
    return grams


def _section_paths(document: DocumentIR) -> dict[str, str]:
    stack: dict[int, str] = {}
    result: dict[str, str] = {}
    for paragraph in sorted(document.paragraphs, key=lambda p: p.order):
        if paragraph.heading_level:
            level = paragraph.heading_level
            stack[level] = paragraph.text.strip()
            for stale in [k for k in stack if k > level]:
                stack.pop(stale, None)
        path = " / ".join(stack[level] for level in sorted(stack)) if stack else "正文"
        result[paragraph.id] = path
    return result


def _prepare(document: DocumentIR, config: TextCompareConfig) -> list[_PreparedParagraph]:
    paths = _section_paths(document)
    interference_by_id = {}
    if config.apply_interference:
        interference_result = classify_interference(document)
        interference_by_id = {item.paragraph_id: item for item in interference_result.items}

    prepared: list[_PreparedParagraph] = []
    for paragraph in document.paragraphs:
        normalized = normalize_for_compare(paragraph.text)
        interference = interference_by_id.get(paragraph.id)
        # 标题和明确 exclude 的干扰项不进入正文重复率；标准响应等 downweight 项保留但降权。
        if paragraph.heading_level is not None:
            continue
        if interference is not None and interference.action == "exclude":
            continue
        if len(normalized) < config.min_chars:
            continue
        if len(normalized) > config.max_chars:
            normalized = normalized[: config.max_chars]

        weight = 1.0
        category = None
        action = None
        if interference is not None:
            category = interference.category
            action = interference.action
            if action == "downweight":
                weight = config.interference_downweight_factor

        prepared.append(
            _PreparedParagraph(
                paragraph=paragraph,
                normalized=normalized,
                section_path=paths.get(paragraph.id, "正文"),
                weight=weight,
                interference_category=category,
                interference_action=action,
            )
        )
    return prepared


def _build_recall_index(
    paragraphs: list[_PreparedParagraph], n: int
) -> tuple[dict[str, set[int]], list[set[str]]]:
    index: dict[str, set[int]] = defaultdict(set)
    token_sets: list[set[str]] = []
    for idx, item in enumerate(paragraphs):
        tokens = set(_char_ngrams(item.normalized, n, n))
        token_sets.append(tokens)
        for token in tokens:
            index[token].add(idx)
    return index, token_sets


def _candidate_indices(
    source: _PreparedParagraph,
    target_index: dict[str, set[int]],
    target_token_sets: list[set[str]],
    config: TextCompareConfig,
) -> list[int]:
    source_tokens = set(_char_ngrams(source.normalized, config.recall_ngram, config.recall_ngram))
    shared_counts: Counter[int] = Counter()
    for token in source_tokens:
        for idx in target_index.get(token, ()):
            shared_counts[idx] += 1

    ranked: list[tuple[float, int]] = []
    for idx, shared in shared_counts.items():
        if shared < config.min_shared_recall_tokens:
            continue
        target_tokens = target_token_sets[idx]
        union = len(source_tokens | target_tokens)
        jaccard = shared / union if union else 0.0
        ranked.append((jaccard, idx))

    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [idx for _, idx in ranked[: config.max_candidates_per_paragraph]]


def _idf_from_paragraphs(
    paragraphs: Iterable[_PreparedParagraph], config: TextCompareConfig
) -> dict[str, float]:
    token_sets: list[set[str]] = []
    for item in paragraphs:
        token_sets.append(set(_char_ngrams(item.normalized, config.ngram_min, config.ngram_max)))
    total = len(token_sets)
    df: Counter[str] = Counter()
    for tokens in token_sets:
        df.update(tokens)
    return {token: math.log((1 + total) / (1 + freq)) + 1.0 for token, freq in df.items()}


def _tfidf_vector(text: str, idf: dict[str, float], config: TextCompareConfig) -> dict[str, float]:
    counts = Counter(_char_ngrams(text, config.ngram_min, config.ngram_max))
    if not counts:
        return {}
    total = sum(counts.values())
    vector = {token: (count / total) * idf.get(token, 1.0) for token, count in counts.items()}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm == 0:
        return {}
    return {token: value / norm for token, value in vector.items()}


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())


def _containment(left: str, right: str, n: int = 3) -> float:
    left_tokens = set(_char_ngrams(left, n, n))
    right_tokens = set(_char_ngrams(right, n, n))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _score_pair(
    left: _PreparedParagraph,
    right: _PreparedParagraph,
    left_vec: dict[str, float],
    right_vec: dict[str, float],
    reranker: SemanticReranker | None = None,
) -> _ScoredPair:
    tfidf_cosine = max(0.0, min(1.0, _cosine(left_vec, right_vec)))
    containment = _containment(left.normalized, right.normalized)

    # SequenceMatcher 对超长文本成本较高；只有词法召回已具备一定相似度时才执行。
    if max(tfidf_cosine, containment) >= 0.35:
        sequence_ratio = SequenceMatcher(None, left.normalized, right.normalized, autojunk=False).ratio()
    else:
        sequence_ratio = 0.0

    semantic_score = None
    reranker_name = None
    if reranker is not None:
        semantic_score = max(0.0, min(1.0, float(reranker.score(left.paragraph.text, right.paragraph.text))))
        reranker_name = getattr(reranker, "name", reranker.__class__.__name__)

    lexical_score = max(tfidf_cosine, sequence_ratio, containment)
    raw_score = max(lexical_score, semantic_score or 0.0)
    interference_factor = min(left.weight, right.weight)
    score = raw_score * interference_factor
    return _ScoredPair(
        left=left,
        right=right,
        score=round(max(0.0, min(1.0, score)), 6),
        raw_score=round(max(0.0, min(1.0, raw_score)), 6),
        interference_factor=round(interference_factor, 6),
        tfidf_cosine=round(tfidf_cosine, 6),
        sequence_ratio=round(sequence_ratio, 6),
        containment=round(containment, 6),
        semantic_score=round(semantic_score, 6) if semantic_score is not None else None,
        reranker_name=reranker_name,
    )


def _severity(score: float, config: TextCompareConfig) -> str:
    return "high" if score >= config.high_threshold else "medium"


def _make_finding(
    doc_a: DocumentIR,
    doc_b: DocumentIR,
    pair: _ScoredPair,
    config: TextCompareConfig,
) -> Finding:
    left_locator = pair.left.paragraph.source_locator or SourceLocator(kind="unknown")
    right_locator = pair.right.paragraph.source_locator or SourceLocator(kind="unknown")
    level = _severity(pair.score, config)
    label = "高度重复" if level == "high" else "中度相似"
    finding_key = "|".join(
        [doc_a.sha256, pair.left.paragraph.id, doc_b.sha256, pair.right.paragraph.id]
    ).encode("utf-8")
    finding_id = f"txt-{hashlib.sha256(finding_key).hexdigest()[:24]}"
    return Finding(
        finding_id=finding_id,
        type="text_similarity",
        severity=level,
        document_id=doc_a.document_id,
        peer_document_id=doc_b.document_id,
        source_locator=left_locator,
        peer_source_locator=right_locator,
        score=pair.score,
        summary=(
            f"{doc_a.filename} 与 {doc_b.filename} 检测到{label}段落，"
            f"相似度 {pair.score * 100:.1f}%"
        ),
        evidence={
            "source_paragraph_id": pair.left.paragraph.id,
            "peer_paragraph_id": pair.right.paragraph.id,
            "source_section": pair.left.section_path,
            "peer_section": pair.right.section_path,
            "source_text": pair.left.paragraph.text,
            "peer_text": pair.right.paragraph.text,
            "source_char_count": pair.left.char_count,
            "peer_char_count": pair.right.char_count,
        },
        metadata={
            "algorithm": "lexical-alpha-v1",
            "tfidf_cosine": pair.tfidf_cosine,
            "sequence_ratio": pair.sequence_ratio,
            "containment": pair.containment,
            "semantic_score": pair.semantic_score,
            "semantic_reranker": pair.reranker_name,
            "raw_similarity": pair.raw_score,
            "interference_factor": pair.interference_factor,
            "source_interference_category": pair.left.interference_category,
            "source_interference_action": pair.left.interference_action,
            "peer_interference_category": pair.right.interference_category,
            "peer_interference_action": pair.right.interference_action,
            "high_threshold": config.high_threshold,
            "medium_threshold": config.medium_threshold,
        },
    )


def _aggregate_top_sections(findings: list[Finding], limit: int = 10) -> list[dict[str, object]]:
    stats: dict[tuple[str, str], dict[str, object]] = {}
    for finding in findings:
        source_section = str(finding.evidence.get("source_section") or "正文")
        peer_section = str(finding.evidence.get("peer_section") or "正文")
        key = (source_section, peer_section)
        item = stats.setdefault(
            key,
            {
                "source_section": source_section,
                "peer_section": peer_section,
                "pair_count": 0,
                "high_pair_count": 0,
                "max_similarity": 0.0,
            },
        )
        item["pair_count"] = int(item["pair_count"]) + 1
        if finding.severity == "high":
            item["high_pair_count"] = int(item["high_pair_count"]) + 1
        item["max_similarity"] = max(float(item["max_similarity"]), float(finding.score or 0.0))

    result = list(stats.values())
    result.sort(
        key=lambda x: (
            -int(x["high_pair_count"]),
            -float(x["max_similarity"]),
            -int(x["pair_count"]),
            str(x["source_section"]),
        )
    )
    return result[:limit]


def compare_document_pair(
    doc_a: DocumentIR,
    doc_b: DocumentIR,
    config: TextCompareConfig | None = None,
    reranker: SemanticReranker | None = None,
) -> tuple[list[Finding], TextPairSummary]:
    config = config or TextCompareConfig()
    left = _prepare(doc_a, config)
    right = _prepare(doc_b, config)

    target_index, target_token_sets = _build_recall_index(right, config.recall_ngram)
    idf = _idf_from_paragraphs([*left, *right], config)
    left_vectors = {item.paragraph.id: _tfidf_vector(item.normalized, idf, config) for item in left}
    right_vectors = {item.paragraph.id: _tfidf_vector(item.normalized, idf, config) for item in right}

    scored: list[_ScoredPair] = []
    for source in left:
        source_pairs: list[_ScoredPair] = []
        for target_idx in _candidate_indices(source, target_index, target_token_sets, config):
            target = right[target_idx]
            pair = _score_pair(
                source,
                target,
                left_vectors[source.paragraph.id],
                right_vectors[target.paragraph.id],
                reranker=reranker,
            )
            if pair.score >= config.medium_threshold:
                source_pairs.append(pair)
        source_pairs.sort(key=lambda p: (-p.score, p.right.paragraph.order))
        scored.extend(source_pairs[: config.top_matches_per_paragraph])

    # 同一段落对只保留一次，并按确定性顺序输出。
    unique: dict[tuple[str, str], _ScoredPair] = {}
    for pair in scored:
        key = (pair.left.paragraph.id, pair.right.paragraph.id)
        previous = unique.get(key)
        if previous is None or pair.score > previous.score:
            unique[key] = pair
    pairs = sorted(
        unique.values(),
        key=lambda p: (-p.score, p.left.paragraph.order, p.right.paragraph.order),
    )
    findings = [_make_finding(doc_a, doc_b, pair, config) for pair in pairs]

    high_source_ids = {
        str(f.evidence["source_paragraph_id"]) for f in findings if f.severity == "high"
    }
    high_peer_ids = {
        str(f.evidence["peer_paragraph_id"]) for f in findings if f.severity == "high"
    }
    left_by_id = {item.paragraph.id: item for item in left}
    right_by_id = {item.paragraph.id: item for item in right}
    left_total_chars = sum(item.char_count for item in left)
    right_total_chars = sum(item.char_count for item in right)
    left_repeated_chars = sum(left_by_id[item_id].char_count for item_id in high_source_ids if item_id in left_by_id)
    right_repeated_chars = sum(right_by_id[item_id].char_count for item_id in high_peer_ids if item_id in right_by_id)

    left_stats = DocumentTextStats(
        document_id=doc_a.document_id,
        filename=doc_a.filename,
        eligible_paragraphs=len(left),
        total_chars=left_total_chars,
        repeated_paragraphs_high=len(high_source_ids),
        repeated_chars_high=left_repeated_chars,
        repeated_rate_high=round(left_repeated_chars / left_total_chars, 6) if left_total_chars else 0.0,
    )
    right_stats = DocumentTextStats(
        document_id=doc_b.document_id,
        filename=doc_b.filename,
        eligible_paragraphs=len(right),
        total_chars=right_total_chars,
        repeated_paragraphs_high=len(high_peer_ids),
        repeated_chars_high=right_repeated_chars,
        repeated_rate_high=round(right_repeated_chars / right_total_chars, 6) if right_total_chars else 0.0,
    )

    summary = TextPairSummary(
        document_a_id=doc_a.document_id,
        document_b_id=doc_b.document_id,
        document_a_filename=doc_a.filename,
        document_b_filename=doc_b.filename,
        high_pairs=sum(1 for f in findings if f.severity == "high"),
        medium_pairs=sum(1 for f in findings if f.severity == "medium"),
        max_similarity=max((float(f.score or 0.0) for f in findings), default=0.0),
        document_a=left_stats,
        document_b=right_stats,
        top_sections=_aggregate_top_sections(findings),
    )
    return findings, summary


def compare_document_set(
    documents: list[DocumentIR],
    config: TextCompareConfig | None = None,
    reranker: SemanticReranker | None = None,
) -> TextComparisonResult:
    if len(documents) < 2:
        raise ValueError("文本比对至少需要 2 份文档")
    if len(documents) > 5:
        raise ValueError("当前单批最多支持 5 份文档")

    config = config or TextCompareConfig()
    all_findings: list[Finding] = []
    summaries: list[TextPairSummary] = []
    for doc_a, doc_b in combinations(documents, 2):
        findings, summary = compare_document_pair(
            doc_a, doc_b, config=config, reranker=reranker
        )
        all_findings.extend(findings)
        summaries.append(summary)

    return TextComparisonResult(
        schema_version="1.0.0",
        compare_type="text_similarity",
        documents=[
            {"document_id": doc.document_id, "filename": doc.filename, "sha256": doc.sha256}
            for doc in documents
        ],
        pair_summaries=summaries,
        findings=all_findings,
        metadata={
            "algorithm": "lexical-alpha-v1",
            "medium_threshold": config.medium_threshold,
            "high_threshold": config.high_threshold,
            "candidate_recall": f"char-{config.recall_ngram}-gram inverted index",
            "ranker": f"char-{config.ngram_min}-{config.ngram_max}-gram TF-IDF + sequence + containment",
            "embedding_rerank": getattr(reranker, "name", "not-enabled-alpha") if reranker else "not-enabled-alpha",
            "interference_filter": "rule-alpha-v1" if config.apply_interference else "disabled",
            "interference_downweight_factor": config.interference_downweight_factor,
        },
    )
