from __future__ import annotations

from shared.http.errors import ApiError


def require_object(body: object, name: str = "body") -> dict[str, object]:
    if not isinstance(body, dict):
        raise ApiError(f"{name} must be an object")
    return body


def require_str(obj: dict[str, object], key: str) -> str:
    value = obj.get(key)
    if value is None:
        raise ApiError(f"missing field: {key}")
    if not isinstance(value, str):
        raise ApiError(f"field must be a string: {key}")
    return value


def optional_str(obj: dict[str, object], key: str) -> str | None:
    value = obj.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(f"field must be a string: {key}")
    return value


def require_int(obj: dict[str, object], key: str) -> int:
    value = obj.get(key)
    if value is None:
        raise ApiError(f"missing field: {key}")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ApiError(f"field must be an integer: {key}") from exc


def optional_int(obj: dict[str, object], key: str) -> int | None:
    value = obj.get(key)
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ApiError(f"field must be an integer: {key}") from exc
