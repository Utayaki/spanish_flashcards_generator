from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable


Snapshot = Hashable


class DirtyStateError(ValueError):
    """Raised when an editor dirty-state operation receives invalid data."""


@dataclass
class DirtyState:
    """Small pure helper for editor dirty tracking.

    Editors call ``mark_clean(snapshot)`` after loading or saving. They call
    ``update(snapshot)`` whenever fields change. The helper only compares
    immutable snapshots; it does not know about PyQt widgets.
    """

    clean_snapshot: Snapshot | None = None
    current_snapshot: Snapshot | None = None

    def mark_clean(self, snapshot: Snapshot) -> None:
        self.clean_snapshot = snapshot
        self.current_snapshot = snapshot

    def update(self, snapshot: Snapshot) -> bool:
        if self.clean_snapshot is None:
            self.mark_clean(snapshot)
            return False
        self.current_snapshot = snapshot
        return self.is_dirty

    @property
    def is_dirty(self) -> bool:
        return self.clean_snapshot is not None and self.current_snapshot != self.clean_snapshot

    @property
    def can_save(self) -> bool:
        return self.is_dirty


def freeze_mapping(mapping: dict[Any, Any]) -> tuple[tuple[Any, Any], ...]:
    """Convert a mapping to a stable tuple for equality comparisons."""

    return tuple(sorted(mapping.items(), key=lambda item: repr(item[0])))


def freeze_payload_mapping(mapping: dict[Any, dict[str, Any]]) -> tuple[tuple[Any, str | None, bool], ...]:
    """Stable snapshot helper for verb participles and form payloads."""

    frozen: list[tuple[Any, str | None, bool]] = []
    for key, payload in mapping.items():
        form = payload.get("form")
        frozen.append((key, str(form) if form is not None else None, bool(payload.get("is_irregular", False))))
    return tuple(sorted(frozen, key=lambda item: repr(item[0])))
