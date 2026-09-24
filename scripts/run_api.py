from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 Bid Compare Agent HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="仅供本地开发使用")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("BID_COMPARE_DATA_DIR", "data"),
        help="任务数据库与产物目录，默认 data",
    )
    parser.add_argument(
        "--auth-mode",
        choices=["disabled", "api_key"],
        default=os.environ.get("BID_COMPARE_AUTH_MODE", "disabled"),
        help="非回环地址必须使用 api_key；密钥通过 BID_COMPARE_API_KEYS 提供",
    )
    args = parser.parse_args()
    if args.auth_mode == "disabled" and args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("鉴权关闭时只允许绑定回环地址")
    if args.auth_mode == "api_key" and not os.environ.get("BID_COMPARE_API_KEYS", "").strip():
        parser.error("api_key 模式需要环境变量 BID_COMPARE_API_KEYS")
    os.environ["BID_COMPARE_AUTH_MODE"] = args.auth_mode
    os.environ["BID_COMPARE_DATA_DIR"] = str(Path(args.data_dir).resolve())
    uvicorn.run(
        "bid_compare_agent.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
