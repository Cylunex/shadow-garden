#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import secrets
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ALLOWED_PREFIXES = (
    "/api/editor/context",
    "/api/posts",
    "/api/trips",
    "/api/food",
    "/api/moments",
    "/api/uploads",
)


def api_settings() -> tuple[str, str]:
    base_url = os.environ.get("SHADOW_GARDEN_API_URL", "").rstrip("/")
    token = os.environ.get("SHADOW_GARDEN_AGENT_TOKEN", "")
    if not base_url or not token:
        raise SystemExit(
            "Missing SHADOW_GARDEN_API_URL or SHADOW_GARDEN_AGENT_TOKEN"
        )
    return base_url, token


def validate_path(path: str, method: str) -> str:
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        raise SystemExit("API path must be relative, for example /api/posts")
    if ".." in parsed.path.split("/"):
        raise SystemExit("Invalid API path")
    if not any(
        parsed.path == prefix or parsed.path.startswith(prefix + "/")
        for prefix in ALLOWED_PREFIXES
    ):
        raise SystemExit("API path is outside the content scope")
    if parsed.path.startswith("/api/uploads") and method != "POST":
        raise SystemExit("Uploads only support POST")
    return path


def read_json_payload(path: str) -> bytes:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def multipart_image(path: Path) -> tuple[bytes, str]:
    boundary = f"----shadow-garden-{secrets.token_hex(12)}"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    content = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def send_request(method: str, path: str, body: bytes | None, content_type: str) -> int:
    base_url, token = api_settings()
    safe_path = validate_path(path, method)
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(
        base_url + safe_path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
            return 0
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        print(f"HTTP {error.code}: {detail}", file=sys.stderr)
        return 1
    except URLError as error:
        print(f"Request failed: {error.reason}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Restricted Shadow Garden API client")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("get", "post", "put", "patch"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("path")
        if command != "get":
            subparser.add_argument("--json", required=True, dest="json_path")

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("image")
    args = parser.parse_args()

    if args.command == "upload":
        image_path = Path(args.image)
        if not image_path.is_file():
            raise SystemExit(f"Image not found: {image_path}")
        body, content_type = multipart_image(image_path)
        return send_request("POST", "/api/uploads", body, content_type)

    method = args.command.upper()
    body = None
    content_type = ""
    if method in {"POST", "PUT", "PATCH"}:
        body = read_json_payload(args.json_path)
        content_type = "application/json"
    return send_request(method, args.path, body, content_type)


if __name__ == "__main__":
    raise SystemExit(main())
