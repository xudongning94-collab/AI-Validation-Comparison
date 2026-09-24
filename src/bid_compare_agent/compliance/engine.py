from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Iterable

from bid_compare_agent.models.document_ir import SourceLocator
from bid_compare_agent.models.finding import Finding

from .models import (
    PageEvidence,
    SignatureComplianceResult,
    SignatureRequirement,
    SignatureRuleEvaluation,
    VisualCandidate,
)


DATE_PATTERN = re.compile(
    r"(?<!\d)(?P<year>20\d{2})\s*[年./-]\s*(?P<month>\d{1,2})\s*[月./-]\s*(?P<day>\d{1,2})\s*日?"
)
LIMITATIONS = [
    "本检查仅判断签字签章的存在性、一致性、位置和明显质量异常，不能鉴定签名或印章真伪。",
    "OCR 与视觉候选属于辅助证据；低置信度、遮挡、裁切或扫描质量不足时必须人工复核。",
    "规则结果必须结合招标文件原文、授权文件和投标主体信息进行最终确认。",
]


def _normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def _finding_id(document_id: str, rule_id: str, issue_code: str, token: str) -> str:
    raw = f"{document_id}|{rule_id}|{issue_code}|{token}".encode("utf-8")
    return f"finding-signature-{hashlib.sha256(raw).hexdigest()[:20]}"


def _make_finding(
    *,
    document_id: str,
    requirement: SignatureRequirement,
    issue_code: str,
    severity: str,
    summary: str,
    page_number: int,
    score: float,
    evidence: dict[str, object],
) -> Finding:
    return Finding(
        finding_id=_finding_id(document_id, requirement.rule_id, issue_code, str(page_number)),
        type="signature_compliance",
        severity=severity,
        document_id=document_id,
        source_locator=SourceLocator(kind="page", page=page_number),
        summary=summary,
        score=score,
        evidence={
            "rule_id": requirement.rule_id,
            "issue_code": issue_code,
            **evidence,
        },
        metadata={
            "deterministic": True,
            "requires_human_review": True,
            "authenticity_check": False,
        },
    )


def _page_text_sources(page: PageEvidence) -> list[tuple[str, float, str]]:
    sources: list[tuple[str, float, str]] = []
    if page.native_text.strip():
        sources.append((page.native_text, 1.0, f"page-{page.page_number}:native"))
    for index, item in enumerate(page.ocr_items):
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        evidence_id = str(item.get("evidence_id") or f"page-{page.page_number}:ocr-{index}")
        sources.append((text, max(0.0, min(1.0, confidence)), evidence_id))
    for value in page.company_names:
        sources.append((value, 1.0, f"page-{page.page_number}:company-entity"))
    for value in page.person_names:
        sources.append((value, 1.0, f"page-{page.page_number}:person-entity"))
    for value in page.date_values:
        sources.append((value, 1.0, f"page-{page.page_number}:date-entity"))
    for candidate in page.candidates:
        if candidate.recognized_text:
            sources.append(
                (
                    candidate.recognized_text,
                    candidate.confidence,
                    candidate.candidate_id,
                )
            )
    return sources


def _match_expected(
    expected: Iterable[str],
    pages: Iterable[PageEvidence],
    threshold: float,
) -> tuple[str | None, float, str | None]:
    normalized_expected = [(value, _normalized(value)) for value in expected if _normalized(value)]
    best: tuple[str | None, float, str | None] = (None, 0.0, None)
    for page in pages:
        for text, confidence, source_id in _page_text_sources(page):
            normalized_text = _normalized(text)
            for original, target in normalized_expected:
                if target in normalized_text and confidence > best[1]:
                    best = (original, confidence, source_id)
    if best[0] is None:
        return best
    return best[0], best[1], best[2]


def _parse_dates(pages: Iterable[PageEvidence]) -> list[tuple[date, float, str]]:
    values: dict[tuple[date, str], tuple[date, float, str]] = {}
    for page in pages:
        for text, confidence, source_id in _page_text_sources(page):
            for match in DATE_PATTERN.finditer(text):
                try:
                    parsed = date(
                        int(match.group("year")),
                        int(match.group("month")),
                        int(match.group("day")),
                    )
                except ValueError:
                    continue
                key = (parsed, source_id)
                existing = values.get(key)
                if existing is None or confidence > existing[1]:
                    values[key] = (parsed, confidence, source_id)
    return sorted(values.values(), key=lambda item: (item[0], -item[1], item[2]))


def _candidates(
    pages: Iterable[PageEvidence],
    kind: str,
) -> list[VisualCandidate]:
    return sorted(
        [
            candidate
            for page in pages
            for candidate in page.candidates
            if candidate.kind == kind
        ],
        key=lambda item: (-item.confidence, item.candidate_id),
    )


def _rule_pages(
    requirement: SignatureRequirement,
    pages: list[PageEvidence],
) -> tuple[list[PageEvidence], bool]:
    allowed = [
        page
        for page in pages
        if not requirement.allowed_pages or page.page_number in requirement.allowed_pages
    ]
    if not requirement.anchor_terms:
        return allowed, bool(allowed)

    matches: list[PageEvidence] = []
    targets = [_normalized(term) for term in requirement.anchor_terms if _normalized(term)]
    for page in allowed:
        page_text = _normalized(" ".join(text for text, _confidence, _source in _page_text_sources(page)))
        if any(target in page_text for target in targets):
            matches.append(page)
    return (matches or allowed), bool(matches)


def _append_presence_findings(
    *,
    document_id: str,
    requirement: SignatureRequirement,
    pages: list[PageEvidence],
    kind: str,
    required: bool,
    findings: list[Finding],
) -> list[str]:
    candidates = _candidates(pages, kind)
    if not required:
        return [candidate.candidate_id for candidate in candidates]

    label = "签字" if kind == "signature" else "印章"
    confident = [
        candidate
        for candidate in candidates
        if candidate.confidence >= requirement.minimum_candidate_confidence
    ]
    page_number = pages[0].page_number if pages else 1
    if not candidates and pages and any(page.vision_status != "ok" for page in pages):
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code=f"{kind}_evidence_unavailable",
                severity="medium",
                summary=f"{requirement.title}缺少可用的{label}视觉检测结果，不能判定为已签或漏签。",
                page_number=page_number,
                score=0.6,
                evidence={"vision_statuses": sorted({page.vision_status for page in pages})},
            )
        )
        return []

    if not confident and candidates:
        best = candidates[0]
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code=f"{kind}_low_confidence",
                severity="medium",
                summary=f"{requirement.title}检测到疑似{label}，但置信度不足，需人工复核。",
                page_number=best.page_number,
                score=round(1.0 - best.confidence, 4),
                evidence={
                    "candidate_ids": [item.candidate_id for item in candidates[:5]],
                    "best_confidence": best.confidence,
                    "minimum_confidence": requirement.minimum_candidate_confidence,
                },
            )
        )
    elif not confident:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code=f"missing_{kind}",
                severity="high",
                summary=f"{requirement.title}未发现必需的{label}证据。",
                page_number=page_number,
                score=0.9,
                evidence={"candidate_count": 0},
            )
        )

    quality_candidates = [
        candidate
        for candidate in candidates
        if candidate.quality_flags
    ]
    if quality_candidates:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code=f"{kind}_quality_issue",
                severity="medium",
                summary=f"{requirement.title}的{label}候选存在裁切、遮挡或清晰度问题。",
                page_number=quality_candidates[0].page_number,
                score=0.65,
                evidence={
                    "candidates": [
                        {
                            "candidate_id": item.candidate_id,
                            "quality_flags": list(item.quality_flags),
                        }
                        for item in quality_candidates[:5]
                    ]
                },
            )
        )
    return [candidate.candidate_id for candidate in candidates]


def _evaluate_identity(
    *,
    document_id: str,
    requirement: SignatureRequirement,
    pages: list[PageEvidence],
    expected: tuple[str, ...],
    entity_kind: str,
    findings: list[Finding],
) -> str | None:
    if not expected:
        return None
    match, confidence, source_id = _match_expected(
        expected,
        pages,
        requirement.minimum_text_confidence,
    )
    page_number = pages[0].page_number if pages else 1
    label = "投标主体名称" if entity_kind == "company" else "签署人姓名"
    text_evidence_available = any(
        page.native_text.strip()
        or page.company_names
        or page.person_names
        or page.date_values
        or page.ocr_status == "ok"
        for page in pages
    )
    if not text_evidence_available:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code=f"{entity_kind}_name_evidence_unavailable",
                severity="medium",
                summary=f"{requirement.title}缺少可用文本或 OCR 证据，无法核对{label}。",
                page_number=page_number,
                score=0.6,
                evidence={"ocr_statuses": sorted({page.ocr_status for page in pages})},
            )
        )
        return None
    observed = sorted(
        {
            value
            for page in pages
            for value in (page.company_names if entity_kind == "company" else page.person_names)
            if value.strip()
        }
    )
    if match is None:
        issue_code = f"{entity_kind}_name_mismatch" if observed else f"missing_{entity_kind}_name"
        summary = (
            f"{requirement.title}检测到的{label}与规则不一致。"
            if observed
            else f"{requirement.title}未发现要求的{label}。"
        )
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code=issue_code,
                severity="high",
                summary=summary,
                page_number=page_number,
                score=0.88,
                evidence={
                    "expected_values": list(expected),
                    "observed_values": observed[:10],
                },
            )
        )
        return None
    if confidence < requirement.minimum_text_confidence:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code=f"{entity_kind}_name_low_confidence",
                severity="medium",
                summary=f"{requirement.title}疑似包含正确{label}，但 OCR 置信度不足。",
                page_number=page_number,
                score=round(1.0 - confidence, 4),
                evidence={
                    "matched_value": match,
                    "confidence": confidence,
                    "source_id": source_id,
                },
            )
        )
    return match


def _evaluate_dates(
    *,
    document_id: str,
    requirement: SignatureRequirement,
    pages: list[PageEvidence],
    findings: list[Finding],
) -> str | None:
    if not requirement.require_date:
        return None
    page_number = pages[0].page_number if pages else 1

    text_evidence_available = any(
        page.native_text.strip()
        or page.date_values
        or page.ocr_status == "ok"
        for page in pages
    )
    if not text_evidence_available:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code="date_evidence_unavailable",
                severity="medium",
                summary=f"{requirement.title}缺少可用文本或 OCR 证据，无法核对签署日期。",
                page_number=page_number,
                score=0.6,
                evidence={"ocr_statuses": sorted({page.ocr_status for page in pages})},
            )
        )
        return None
    dates = _parse_dates(pages)
    confident = [
        item for item in dates if item[1] >= requirement.minimum_text_confidence
    ]
    if not confident and dates:
        best = max(dates, key=lambda item: item[1])
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code="date_low_confidence",
                severity="medium",
                summary=f"{requirement.title}疑似存在签署日期，但 OCR 置信度不足。",
                page_number=page_number,
                score=round(1.0 - best[1], 4),
                evidence={"date": best[0].isoformat(), "confidence": best[1], "source_id": best[2]},
            )
        )
        return best[0].isoformat()
    if not confident:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code="missing_date",
                severity="high",
                summary=f"{requirement.title}未发现有效签署日期。",
                page_number=page_number,
                score=0.85,
                evidence={},
            )
        )
        return None

    unique_dates = sorted({item[0] for item in confident})
    if len(unique_dates) > 1:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code="conflicting_dates",
                severity="medium",
                summary=f"{requirement.title}检测到多个不同日期，需确认是否存在跨页或版本矛盾。",
                page_number=page_number,
                score=0.65,
                evidence={"dates": [value.isoformat() for value in unique_dates[:10]]},
            )
        )

    in_range = [
        value
        for value in unique_dates
        if (requirement.date_not_before is None or value >= requirement.date_not_before)
        and (requirement.date_not_after is None or value <= requirement.date_not_after)
    ]
    if not in_range:
        findings.append(
            _make_finding(
                document_id=document_id,
                requirement=requirement,
                issue_code="date_out_of_range",
                severity="high",
                summary=f"{requirement.title}的签署日期不在允许范围内。",
                page_number=page_number,
                score=0.9,
                evidence={
                    "dates": [value.isoformat() for value in unique_dates],
                    "date_not_before": (
                        requirement.date_not_before.isoformat()
                        if requirement.date_not_before
                        else None
                    ),
                    "date_not_after": (
                        requirement.date_not_after.isoformat()
                        if requirement.date_not_after
                        else None
                    ),
                },
            )
        )
    selected = in_range[0] if in_range else unique_dates[0]
    return selected.isoformat()


def check_signature_compliance(
    document_id: str,
    pages: Iterable[PageEvidence],
    requirements: Iterable[SignatureRequirement],
) -> SignatureComplianceResult:
    ordered_pages = sorted(pages, key=lambda item: item.page_number)
    if not document_id.strip():
        raise ValueError("document_id 不能为空")
    if len({page.page_number for page in ordered_pages}) != len(ordered_pages):
        raise ValueError("PageEvidence 页码不能重复")

    all_findings: list[Finding] = []
    evaluations: list[SignatureRuleEvaluation] = []
    for requirement in requirements:
        rule_findings: list[Finding] = []
        relevant_pages, location_ok = _rule_pages(requirement, ordered_pages)
        page_number = relevant_pages[0].page_number if relevant_pages else 1
        if not location_ok:
            rule_findings.append(
                _make_finding(
                    document_id=document_id,
                    requirement=requirement,
                    issue_code="required_location_missing",
                    severity="high",
                    summary=f"{requirement.title}未在要求页码或签署位置锚点发现证据。",
                    page_number=page_number,
                    score=0.9,
                    evidence={
                        "allowed_pages": list(requirement.allowed_pages),
                        "anchor_terms": list(requirement.anchor_terms),
                    },
                )
            )

        signature_ids = _append_presence_findings(
            document_id=document_id,
            requirement=requirement,
            pages=relevant_pages,
            kind="signature",
            required=requirement.require_signature,
            findings=rule_findings,
        )
        seal_ids = _append_presence_findings(
            document_id=document_id,
            requirement=requirement,
            pages=relevant_pages,
            kind="seal",
            required=requirement.require_seal,
            findings=rule_findings,
        )
        company_name = _evaluate_identity(
            document_id=document_id,
            requirement=requirement,
            pages=relevant_pages,
            expected=requirement.expected_company_names,
            entity_kind="company",
            findings=rule_findings,
        )
        signer_name = _evaluate_identity(
            document_id=document_id,
            requirement=requirement,
            pages=relevant_pages,
            expected=requirement.expected_signer_names,
            entity_kind="signer",
            findings=rule_findings,
        )
        matched_date = _evaluate_dates(
            document_id=document_id,
            requirement=requirement,
            pages=relevant_pages,
            findings=rule_findings,
        )

        severities = {finding.severity for finding in rule_findings}
        status = "failed" if severities & {"critical", "high"} else "review" if severities else "passed"
        evaluations.append(
            SignatureRuleEvaluation(
                rule_id=requirement.rule_id,
                title=requirement.title,
                status=status,
                relevant_pages=[page.page_number for page in relevant_pages],
                matched_company_name=company_name,
                matched_signer_name=signer_name,
                matched_date=matched_date,
                signature_candidate_ids=signature_ids,
                seal_candidate_ids=seal_ids,
                finding_ids=[finding.finding_id for finding in rule_findings],
            )
        )
        all_findings.extend(rule_findings)

    all_findings.sort(key=lambda item: (item.finding_id, item.severity))
    return SignatureComplianceResult(
        schema_version="1.0.0",
        check_type="signature_compliance",
        document_id=document_id,
        rules=evaluations,
        findings=all_findings,
        summary={
            "rule_count": len(evaluations),
            "passed_rule_count": sum(item.status == "passed" for item in evaluations),
            "review_rule_count": sum(item.status == "review" for item in evaluations),
            "failed_rule_count": sum(item.status == "failed" for item in evaluations),
            "finding_count": len(all_findings),
        },
        limitations=list(LIMITATIONS),
        metadata={
            "method": "signature-compliance-rules-v1",
            "deterministic": True,
            "authenticity_check": False,
        },
    )
