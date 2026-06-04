from __future__ import annotations

from dataclasses import dataclass

from controllers.start_page_presenter import validate_word_type


@dataclass(frozen=True)
class NewWordDraft:
    """Unsaved word selected on the start page.

    A draft has enough information to open the correct editor, but it does not
    have a database id yet. The database row is created only after the user
    clicks "Save and go back".
    """

    word_type: str
    lemma: str

    def __post_init__(self) -> None:
        validate_word_type(self.word_type)
        if not self.lemma.strip():
            raise ValueError("draft lemma cannot be empty")
