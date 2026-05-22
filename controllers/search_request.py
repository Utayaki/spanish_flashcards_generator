from __future__ import annotations

from dataclasses import dataclass

from controllers.start_page_presenter import normalize_lemma_input, validate_word_type


@dataclass
class SearchRequestTracker:
    """Tracks the latest start-page search request.

    The UI may start SQLite searches in worker threads. A slower older worker can
    finish after a newer worker. This tracker makes that safe: only the newest
    request for the currently selected word type and query is allowed to update
    the visible "Already added" results.
    """

    latest_request_id: int = 0
    selected_word_type: str | None = None
    normalized_query: str = ""

    def reset(self) -> None:
        self.latest_request_id += 1
        self.selected_word_type = None
        self.normalized_query = ""

    def new_input(self, word_type: str | None, query: str) -> int:
        self.latest_request_id += 1
        if word_type is not None:
            validate_word_type(word_type)
        self.selected_word_type = word_type
        self.normalized_query = normalize_lemma_input(query)
        return self.latest_request_id

    def should_apply(self, request_id: int, word_type: str, query: str) -> bool:
        validate_word_type(word_type)
        return (
            request_id == self.latest_request_id
            and word_type == self.selected_word_type
            and normalize_lemma_input(query) == self.normalized_query
        )
