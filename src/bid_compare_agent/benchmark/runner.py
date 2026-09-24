from __future__ import annotations

import hashlib
import json
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from bid_compare_agent.analysis import analyze_ai_likelihood
from bid_compare_agent.check import check_document_format
from bid_compare_agent.compare import compare_document_set, compare_image_set, normalize_for_compare
from bid_compare_agent.models.document_ir import DocumentIR
from bid_compare_agent.parser import parse_document
from bid_compare_agent.scoring import score_document_set
from bid_compare_agent.utils.config import (
    load_ai_likelihood_config,
    load_image_compare_config,
    load_text_compare_config,
    load_unified_scoring_config,
)
from bid_compare_agent.utils.io import file_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_ROLES = {"tender_reference", "response_old", "response_new", "response"}


class BenchmarkInputError(ValueError):
    pass


def load_benchmark_manifest(path: str | Path) -> tuple[dict[str, Any], Path]:
    manifest_path = Path(path).resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkInputError(f"无法读取 Benchmark manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkInputError("Benchmark manifest 顶层必须是对象")
    return payload, manifest_path.parent


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise BenchmarkInputError(f"{key} 必须是非空数组")
    return value


def _resolve_documents(
    manifest: dict[str, Any],
    manifest_dir: Path,
) -> tuple[dict[str, Path], dict[str, str]]:
    paths: dict[str, Path] = {}
    roles: dict[str, str] = {}
    for item in _require_list(manifest, "documents"):
        if not isinstance(item, dict):
            raise BenchmarkInputError("documents 中的每一项必须是对象")
        document_id = str(item.get("id") or "").strip()
        role = str(item.get("role") or "").strip()
        raw_path = str(item.get("path") or "").strip()
        if not document_id or document_id in paths:
            raise BenchmarkInputError(f"文档 id 为空或重复: {document_id!r}")
        if role not in SUPPORTED_ROLES:
            raise BenchmarkInputError(f"不支持的文档角色: {role!r}")
        path = Path(raw_path)
        if not path.is_absolute():
            path = manifest_dir / path
        path = path.resolve()
        if not path.is_file():
            raise BenchmarkInputError(f"Benchmark 文件不存在: {path}")
        if path.suffix.lower() not in {".docx", ".pdf"}:
            raise BenchmarkInputError(f"Benchmark 仅支持 DOCX/PDF: {path}")
        paths[document_id] = path
        roles[document_id] = role
    return paths, roles


def _stable_json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence_diff(left: DocumentIR, right: DocumentIR) -> dict[str, Any]:
    left_text = [normalize_for_compare(item.text) for item in left.paragraphs]
    right_text = [normalize_for_compare(item.text) for item in right.paragraphs]
    left_text = [item for item in left_text if item]
    right_text = [item for item in right_text if item]
    opcodes = SequenceMatcher(None, left_text, right_text, autojunk=False).get_opcodes()
    counts = {"equal": 0, "replace_left": 0, "replace_right": 0, "delete": 0, "insert": 0}
    changed_blocks = 0
    for tag, left_start, left_end, right_start, right_end in opcodes:
        if tag == "equal":
            counts["equal"] += left_end - left_start
            continue
        changed_blocks += 1
        if tag == "replace":
            counts["replace_left"] += left_end - left_start
            counts["replace_right"] += right_end - right_start
        elif tag == "delete":
            counts["delete"] += left_end - left_start
        elif tag == "insert":
            counts["insert"] += right_end - right_start
    denominator = max(len(left_text), len(right_text), 1)
    return {
        "left_nonempty_paragraphs": len(left_text),
        "right_nonempty_paragraphs": len(right_text),
        **counts,
        "changed_blocks": changed_blocks,
        "exact_sequence_ratio": round(counts["equal"] / denominator, 6),
    }


def _table_diff(left: DocumentIR, right: DocumentIR) -> dict[str, Any]:
    left_rows = [table.rows for table in left.tables]
    right_rows = [table.rows for table in right.tables]
    return {
        "left_tables": len(left_rows),
        "right_tables": len(right_rows),
        "content_equal": left_rows == right_rows,
        "left_content_sha256": _stable_json_hash(left_rows),
        "right_content_sha256": _stable_json_hash(right_rows),
    }


def _image_order_diff(left: DocumentIR, right: DocumentIR) -> dict[str, Any]:
    pairs = list(zip(left.images, right.images))
    binary_equal = sum(1 for a, b in pairs if a.sha256 and a.sha256 == b.sha256)
    perceptual_equal = sum(1 for a, b in pairs if a.phash and a.phash == b.phash)
    dimension_equal = sum(
        1
        for a, b in pairs
        if (a.width_px, a.height_px) == (b.width_px, b.height_px)
    )
    return {
        "left_images": len(left.images),
        "right_images": len(right.images),
        "paired_by_order": len(pairs),
        "binary_equal_by_order": binary_equal,
        "perceptual_equal_by_order": perceptual_equal,
        "dimension_equal_by_order": dimension_equal,
        "binary_changed_or_unpaired": max(len(left.images), len(right.images)) - binary_equal,
        "perceptual_changed_or_unpaired": max(len(left.images), len(right.images)) - perceptual_equal,
    }


def _docx_package_diff(left_path: Path, right_path: Path) -> dict[str, Any] | None:
    if left_path.suffix.lower() != ".docx" or right_path.suffix.lower() != ".docx":
        return None
    try:
        with ZipFile(left_path) as left_zip, ZipFile(right_path) as right_zip:
            left_parts = {
                name: (hashlib.sha256(left_zip.read(name)).hexdigest(), left_zip.getinfo(name).file_size)
                for name in left_zip.namelist()
            }
            right_parts = {
                name: (hashlib.sha256(right_zip.read(name)).hexdigest(), right_zip.getinfo(name).file_size)
                for name in right_zip.namelist()
            }
    except BadZipFile as exc:
        raise BenchmarkInputError(f"无效 DOCX 包: {exc}") from exc

    common = sorted(set(left_parts) & set(right_parts))
    changed = [name for name in common if left_parts[name][0] != right_parts[name][0]]
    changed_parts = [
        {
            "part": name,
            "left_size_bytes": left_parts[name][1],
            "right_size_bytes": right_parts[name][1],
        }
        for name in changed
    ]
    return {
        "left_part_count": len(left_parts),
        "right_part_count": len(right_parts),
        "only_left_parts": sorted(set(left_parts) - set(right_parts)),
        "only_right_parts": sorted(set(right_parts) - set(left_parts)),
        "changed_common_part_count": len(changed),
        "same_common_part_count": len(common) - len(changed),
        "changed_parts": changed_parts,
    }


def _document_profile(document_id: str, role: str, path: Path, document: DocumentIR) -> dict[str, Any]:
    return {
        "id": document_id,
        "role": role,
        "filename": path.name,
        "file_type": document.file_type,
        "size_bytes": document.file_size_bytes,
        "sha256": document.sha256,
        "document_id": document.document_id,
        "page_count": document.page_count,
        "paragraph_count": len(document.paragraphs),
        "table_count": len(document.tables),
        "image_count": len(document.images),
        "warning_count": len(document.warnings),
    }


def _pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return tuple(sorted((left_id, right_id)))


def _evaluate_expectations(
    expectations: dict[str, Any],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, actual: Any, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": passed})

    if "min_text_repeated_rate" in expectations:
        expected = float(expectations["min_text_repeated_rate"])
        actual = min(
            metrics["text_similarity"]["left_repeated_rate_high"],
            metrics["text_similarity"]["right_repeated_rate_high"],
        )
        add("min_text_repeated_rate", actual, expected, actual >= expected)
    if "min_image_repeated_rate" in expectations:
        expected = float(expectations["min_image_repeated_rate"])
        actual = min(
            metrics["image_similarity"]["left_repeated_rate"],
            metrics["image_similarity"]["right_repeated_rate"],
        )
        add("min_image_repeated_rate", actual, expected, actual >= expected)
    if "min_exact_sequence_ratio" in expectations:
        expected = float(expectations["min_exact_sequence_ratio"])
        actual = metrics["logical_diff"]["paragraphs"]["exact_sequence_ratio"]
        add("min_exact_sequence_ratio", actual, expected, actual >= expected)
    if expectations.get("require_file_difference"):
        actual = metrics["left_sha256"] != metrics["right_sha256"]
        add("require_file_difference", actual, True, actual)
    return checks


def run_benchmark(
    manifest: dict[str, Any],
    *,
    manifest_dir: str | Path = ".",
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(manifest_dir).resolve()
    paths, roles = _resolve_documents(manifest, root)
    if bool((manifest.get("privacy") or {}).get("include_raw_text")):
        raise BenchmarkInputError("D11 Alpha 不允许在 Benchmark 报告中包含原文")

    original_hashes = {document_id: file_sha256(path) for document_id, path in paths.items()}
    documents: dict[str, DocumentIR] = {}
    parse_seconds: dict[str, float] = {}
    for document_id, path in paths.items():
        stage_started = time.perf_counter()
        documents[document_id] = parse_document(path)
        parse_seconds[document_id] = round(time.perf_counter() - stage_started, 6)

    thresholds_path = PROJECT_ROOT / "configs" / "thresholds.yaml"
    scoring_path = PROJECT_ROOT / "configs" / "scoring.yaml"
    text_config = load_text_compare_config(thresholds_path)
    image_config = load_image_compare_config(thresholds_path)
    ai_config = load_ai_likelihood_config(thresholds_path)
    score_config = load_unified_scoring_config(scoring_path)

    revision_results: list[dict[str, Any]] = []
    revision_findings: dict[tuple[str, str], tuple[str, str, list[Any]]] = {}
    for pair in manifest.get("revision_pairs") or []:
        left_id = str(pair.get("left") or "")
        right_id = str(pair.get("right") or "")
        if left_id not in documents or right_id not in documents or left_id == right_id:
            raise BenchmarkInputError(f"无效 revision pair: {left_id!r}, {right_id!r}")
        left = documents[left_id]
        right = documents[right_id]

        stage_started = time.perf_counter()
        text_result = compare_document_set([left, right], text_config)
        text_seconds = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        image_result = compare_image_set([left, right], image_config)
        image_seconds = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        format_results = [check_document_format(left), check_document_format(right)]
        ai_result = analyze_ai_likelihood([left, right], ai_config)
        score_result = score_document_set(
            [left, right],
            text_result=text_result,
            image_result=image_result,
            format_results=format_results,
            ai_result=ai_result,
            config=score_config,
        )
        auxiliary_seconds = time.perf_counter() - stage_started

        text_summary = text_result.pair_summaries[0]
        image_summary = image_result.pair_summaries[0]
        logical_diff = {
            "paragraphs": _sequence_diff(left, right),
            "tables": _table_diff(left, right),
            "images": _image_order_diff(left, right),
            "docx_package": _docx_package_diff(paths[left_id], paths[right_id]),
        }
        metrics = {
            "left_sha256": left.sha256,
            "right_sha256": right.sha256,
            "text_similarity": {
                "high_pairs": text_summary.high_pairs,
                "medium_pairs": text_summary.medium_pairs,
                "max_similarity": text_summary.max_similarity,
                "left_repeated_rate_high": text_summary.document_a.repeated_rate_high,
                "right_repeated_rate_high": text_summary.document_b.repeated_rate_high,
            },
            "image_similarity": {
                "exact_pairs": image_summary.exact_pairs,
                "high_similar_pairs": image_summary.high_similar_pairs,
                "max_similarity": image_summary.max_similarity,
                "left_repeated_rate": image_summary.document_a.repeated_rate,
                "right_repeated_rate": image_summary.document_b.repeated_rate,
            },
            "logical_diff": logical_diff,
            "scoring": {
                "aggregate_score": score_result.aggregate_score,
                "aggregate_score_100": score_result.aggregate_score_100,
                "aggregate_risk_level": score_result.aggregate_risk_level,
                "average_document_score": score_result.metadata["average_document_score"],
            },
        }
        checks = _evaluate_expectations(dict(pair.get("expectations") or {}), metrics)
        revision_results.append(
            {
                "id": str(pair.get("id") or f"{left_id}--{right_id}"),
                "left": left_id,
                "right": right_id,
                "metrics": metrics,
                "expectation_checks": checks,
                "status": "passed" if all(item["passed"] for item in checks) else "failed",
                "timings_seconds": {
                    "text_compare": round(text_seconds, 6),
                    "image_compare": round(image_seconds, 6),
                    "format_ai_score": round(auxiliary_seconds, 6),
                },
            }
        )
        revision_findings[_pair_key(left_id, right_id)] = (left_id, right_id, text_result.findings)

    reference_results: list[dict[str, Any]] = []
    for check in manifest.get("reference_checks") or []:
        reference_id = str(check.get("reference") or "")
        target_ids = [str(item) for item in check.get("targets") or []]
        if reference_id not in documents or not target_ids:
            raise BenchmarkInputError("reference check 必须指定有效 reference 和 targets")
        reference = documents[reference_id]
        target_overlap_ids: dict[str, set[str]] = {}
        target_metrics: list[dict[str, Any]] = []
        stage_started = time.perf_counter()
        for target_id in target_ids:
            if target_id not in documents or target_id == reference_id:
                raise BenchmarkInputError(f"无效 reference target: {target_id!r}")
            result = compare_document_set([reference, documents[target_id]], text_config)
            summary = result.pair_summaries[0]
            target_overlap_ids[target_id] = {
                str(finding.evidence.get("peer_paragraph_id"))
                for finding in result.findings
                if finding.severity == "high"
            }
            target_metrics.append(
                {
                    "target": target_id,
                    "high_pairs": summary.high_pairs,
                    "medium_pairs": summary.medium_pairs,
                    "reference_repeated_rate_high": summary.document_a.repeated_rate_high,
                    "target_repeated_rate_high": summary.document_b.repeated_rate_high,
                }
            )

        attribution: dict[str, Any] | None = None
        if len(target_ids) == 2:
            key = _pair_key(target_ids[0], target_ids[1])
            pair_record = revision_findings.get(key)
            source_target = pair_record[0] if pair_record else target_ids[0]
            peer_target = pair_record[1] if pair_record else target_ids[1]
            pair_findings = pair_record[2] if pair_record else []
            attributed = 0
            high_total = 0
            for finding in pair_findings:
                if finding.severity != "high":
                    continue
                high_total += 1
                source_id = str(finding.evidence.get("source_paragraph_id"))
                peer_id = str(finding.evidence.get("peer_paragraph_id"))
                if source_id in target_overlap_ids[source_target] and peer_id in target_overlap_ids[peer_target]:
                    attributed += 1
            attribution = {
                "revision_pair_high_pairs": high_total,
                "pairs_linked_to_reference": attributed,
                "linked_pair_ratio": round(attributed / high_total, 6) if high_total else 0.0,
            }

        reference_results.append(
            {
                "id": str(check.get("id") or f"reference-{reference_id}"),
                "reference": reference_id,
                "targets": target_metrics,
                "revision_pair_reference_attribution": attribution,
                "elapsed_seconds": round(time.perf_counter() - stage_started, 6),
            }
        )

    final_hashes = {document_id: file_sha256(path) for document_id, path in paths.items()}
    inputs_unchanged = original_hashes == final_hashes
    all_revision_passed = all(item["status"] == "passed" for item in revision_results)
    return {
        "schema_version": "1.0.0",
        "benchmark_type": "end_to_end",
        "benchmark_id": str(manifest.get("benchmark_id") or "benchmark-local"),
        "status": "passed" if inputs_unchanged and all_revision_passed else "failed",
        "privacy": {
            "raw_text_included": False,
            "source_files_embedded": False,
            "report_contains_filenames_and_hashes": True,
        },
        "documents": [
            _document_profile(document_id, roles[document_id], paths[document_id], documents[document_id])
            for document_id in paths
        ],
        "revision_pairs": revision_results,
        "reference_checks": reference_results,
        "performance": {
            "parse_seconds": parse_seconds,
            "total_seconds": round(time.perf_counter() - started, 6),
        },
        "integrity": {
            "inputs_unchanged": inputs_unchanged,
            "verified_file_count": len(paths),
        },
        "limitations": [
            "Benchmark 只验证 manifest 中声明的关系和阈值，不替代人工标注的逐条真值集。",
            "招标文件重合用于识别模板来源，不应直接作为不同投标人串标结论。",
            "AI 疑似度仍是非确定性辅助信号，必须人工复核。",
        ],
    }
