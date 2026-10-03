from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.vision.page_rendering import render_document_pages


def _load_config(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("page_rendering"), dict):
        raise ValueError("config must contain a page_rendering object")
    return payload["page_rendering"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render PDF/DOCX pages to privacy-safe, hash-named PNG files."
    )
    parser.add_argument("document", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "page_rendering.yaml",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--canonical-pdf",
        type=Path,
        help="Verified same-source PDF whose pagination overrides DOCX conversion.",
    )
    args = parser.parse_args()

    try:
        config = _load_config(args.config)
        renderer_environment = str(
            config.get("docx_renderer_environment_variable")
            or "BID_COMPARE_DOCX_RENDERER"
        )
        docx_renderer = os.environ.get(renderer_environment) or config.get(
            "docx_renderer"
        )
        result = render_document_pages(
            args.document,
            args.output_dir,
            dpi=int(config.get("dpi", 150)),
            docx_renderer=docx_renderer,
            timeout_seconds=int(config.get("docx_conversion_timeout_seconds", 120)),
            canonical_pdf=args.canonical_pdf,
            canonical_pdf_minimum_text_match=float(
                config.get("canonical_pdf_minimum_text_match", 0.7)
            ),
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    manifest = args.manifest or args.output_dir / "page-render.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"PAGE_RENDER status={result['status']} type={result['source_type']} "
        f"pages={result['page_count']}"
    )
    print(f"MANIFEST {manifest}")
    if result["status"] == "ok":
        return 0
    if result["status"] == "unavailable":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
