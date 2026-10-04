#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit
import webbrowser


class ReviewServerError(ValueError):
    """Raised when a review package cannot be served safely."""


def _relative_image(value: object, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "://" in value:
        raise ReviewServerError(f"{field} must be a local relative path")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ReviewServerError(f"{field} must be a local relative path")
    return path


def inspect_review_package(package: Path) -> tuple[str, dict[str, Path], int]:
    package = package.resolve()
    index = package / "index.html"
    data_path = package / "review-data.json"
    if not package.is_dir() or not index.is_file() or not data_path.is_file():
        raise ReviewServerError(
            "package must contain index.html and review-data.json"
        )
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewServerError(f"cannot read review-data.json: {exc}") from exc

    url_path = "/" + quote(package.name, safe="") + "/index.html"
    allowed: dict[str, Path] = {url_path: index}
    image_count = 0
    for collection_name in ("seal_pages", "signature_fields"):
        collection = data.get(collection_name)
        if not isinstance(collection, list):
            raise ReviewServerError(f"{collection_name} must be an array")
        for index_number, item in enumerate(collection):
            if not isinstance(item, dict):
                raise ReviewServerError(
                    f"{collection_name}[{index_number}] must be an object"
                )
            relative = _relative_image(
                item.get("image"), f"{collection_name}[{index_number}].image"
            )
            resolved = (package / Path(*relative.parts)).resolve()
            try:
                resolved.relative_to(package.parent)
            except ValueError as exc:
                raise ReviewServerError(
                    "review images must stay inside the package parent directory"
                ) from exc
            if not resolved.is_file():
                raise ReviewServerError(
                    f"missing review image for {collection_name}[{index_number}]"
                )
            image_url = unquote(urlsplit(urljoin(url_path, relative.as_posix())).path)
            previous = allowed.get(image_url)
            if previous is not None and previous != resolved:
                raise ReviewServerError(f"conflicting review image URL: {image_url}")
            allowed[image_url] = resolved
            image_count += 1
    return url_path, allowed, image_count


def _handler(allowed: dict[str, Path]) -> type[BaseHTTPRequestHandler]:
    class AllowlistHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._serve(include_body=True)

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve(include_body=False)

        def _serve(self, *, include_body: bool) -> None:
            request_path = unquote(urlsplit(self.path).path)
            target = allowed.get(request_path)
            if target is None:
                self.send_error(404, "Not found")
                return
            try:
                payload = target.read_bytes()
            except OSError:
                self.send_error(404, "Not found")
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if include_body:
                self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return AllowlistHandler


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve one allowlisted review package on 127.0.0.1."
    )
    parser.add_argument("package", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        url_path, allowed, image_count = inspect_review_package(args.package)
    except ReviewServerError as exc:
        print(f"ERROR {exc}")
        return 2

    if args.check_only:
        print(
            "SIGNATURE_REVIEW_SERVER_READY "
            f"url_path={url_path} images={image_count}"
        )
        return 0

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), _handler(allowed))
    except OSError as exc:
        print(f"ERROR cannot start review server: {exc}")
        return 2
    with server:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}{url_path}"
        print(f"SIGNATURE_REVIEW_SERVER url={url} images={image_count}")
        print("Press Ctrl+C to stop the local review server.")
        if not args.no_open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("SIGNATURE_REVIEW_SERVER_STOPPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
