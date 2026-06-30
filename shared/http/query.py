from __future__ import annotations

from shared.http.errors import ApiError


def one(query: dict[str, list[str]], key: str, *, default: str | None = None) -> str:
    values = query.get(key)
    if not values:
        if default is not None:
            return default
        raise ApiError(f"missing query parameter: {key}")
    return values[0]
