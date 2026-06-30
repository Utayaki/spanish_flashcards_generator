from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from shared.http.errors import ApiError


def read_json_body(handler: BaseHTTPRequestHandler, max_bytes: int) -> dict[str, object]:
    length_text = handler.headers.get("Content-Length") or "0"
    try:
        length = int(length_text)
    except ValueError as exc:
        raise ApiError("invalid Content-Length") from exc
    if length > max_bytes:
        raise ApiError("request is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ApiError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ApiError("JSON body must be an object")
    return data


def send_json(
    handler: BaseHTTPRequestHandler,
    payload: dict[str, object],
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
