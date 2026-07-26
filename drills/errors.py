from __future__ import annotations


class DatabaseError(RuntimeError):
    """Raised when the drills database layer cannot complete a valid operation."""
