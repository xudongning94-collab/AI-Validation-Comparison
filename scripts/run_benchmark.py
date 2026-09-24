from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bid_compare_agent.benchmark import load_benchmark_manifest, run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="执行隐私保护的本地端到端 Benchmark")
    parser.add_argument("manifest", help="Benchmark manifest JSON")
    parser.add_argument("-o", "--output", default="output/benchmark/report.json")
    args = parser.parse_args()

    manifest, manifest_dir = load_benchmark_manifest(args.manifest)
    result = run_benchmark(manifest, manifest_dir=manifest_dir)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"OK benchmark={result['benchmark_id']} status={result['status']} "
        f"documents={len(result['documents'])} seconds={result['performance']['total_seconds']:.3f}"
    )
    print(f"OUTPUT {target}")
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
