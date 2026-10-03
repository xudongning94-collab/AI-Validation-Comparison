#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bid_compare_agent.vision.signature_fields import (
    SignatureFieldLocatorConfig,
    locate_signature_fields,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Locate semantic signature fields from OCR text geometry."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "signature_field_locator.yaml",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        config_payload = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        if not isinstance(config_payload, dict):
            raise ValueError("config must be an object")
        config = SignatureFieldLocatorConfig.from_mapping(
            config_payload.get("signature_field_locator")
        )
        result = locate_signature_fields(
            payload.get("items"),
            page_number=int(payload.get("page_number")),
            canvas=payload.get("canvas"),
            config=config,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SIGNATURE_FIELDS status=ok page={result['page_number']} count={result['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
