from __future__ import annotations

import argparse
import json
from pathlib import Path

from bid_compare_agent.api.app import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "hiagent" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 HiAgent 可导入的 OpenAPI 快照")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"输出路径，默认 {DEFAULT_OUTPUT}",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
