#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bid_compare_agent.vision.review_audit import ReviewAuditError, audit_signature_review


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit full-page seal and two-stage signature human-review coverage."
    )
    parser.add_argument("review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    try:
        payload = json.loads(args.review.read_text(encoding="utf-8"))
        result = audit_signature_review(payload)
    except (OSError, json.JSONDecodeError, ReviewAuditError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "SIGNATURE_REVIEW_AUDIT "
        f"status={result['status']} "
        f"seal={result['coverage']['seal']['reviewed']}/"
        f"{result['coverage']['seal']['expected']} "
        f"signature={result['coverage']['signature']['handwriting_reviewed']}/"
        f"{result['coverage']['signature']['expected']}"
    )
    if args.require_complete and result["status"] != "ready":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
