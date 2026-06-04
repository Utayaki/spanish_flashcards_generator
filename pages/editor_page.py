from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from controllers.editor_mode import NewWordDraft
from database import NOMINAL_WORD_TYPES, SpanishWordDatabase
from editors.nominal_editor import NominalEditor
from editors.other_editor import OtherEditor
from editors.verb_editor import VerbEditor


class EditorPage(QWidget):
    """Routes an existing word or an unsaved draft to the correct editor."""

    back_requested = pyqtSignal()

    def __init__(
        self,
        database: SpanishWordDatabase,
        *,
        word_id: int | None = None,
        draft: NewWordDraft | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if (word_id is None) == (draft is None):
            raise ValueError("EditorPage requires exactly one of word_id or draft")

        self.database = database
        self.word_id = word_id
        self.draft = draft
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self.draft is not None:
            self._add_draft_editor(layout, self.draft)
            return

        assert self.word_id is not None
        word = self.database.load_word(self.word_id)
        word_type = str(word["word_type"])
        self._add_existing_editor(layout, self.word_id, word_type)

    def _add_draft_editor(self, layout: QVBoxLayout, draft: NewWordDraft) -> None:
        word_type = draft.word_type
        if word_type in NOMINAL_WORD_TYPES:
            editor = NominalEditor.new_draft(self.database, word_type=word_type, lemma=draft.lemma, parent=self)
        elif word_type == "other":
            editor = OtherEditor.new_draft(self.database, lemma=draft.lemma, parent=self)
        elif word_type == "verb":
            editor = VerbEditor.new_draft(self.database, lemma=draft.lemma, parent=self)
        else:
            self._add_unknown_word_type(layout, word_type, draft.lemma)
            return

        editor.back_requested.connect(self.back_requested.emit)
        layout.addWidget(editor)

    def _add_existing_editor(self, layout: QVBoxLayout, word_id: int, word_type: str) -> None:
        if word_type in NOMINAL_WORD_TYPES:
            editor = NominalEditor.existing(self.database, word_id=word_id, parent=self)
        elif word_type == "other":
            editor = OtherEditor.existing(self.database, word_id=word_id, parent=self)
        elif word_type == "verb":
            editor = VerbEditor.existing(self.database, word_id=word_id, parent=self)
        else:
            word = self.database.get_word_summary(word_id) or {"lemma": "Unknown"}
            self._add_unknown_word_type(layout, word_type, str(word.get("lemma", "Unknown")))
            return

        editor.back_requested.connect(self.back_requested.emit)
        layout.addWidget(editor)

    def _add_unknown_word_type(self, layout: QVBoxLayout, word_type: str, lemma: str) -> None:
        placeholder = QWidget(self)
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(24, 24, 24, 24)
        placeholder_layout.setSpacing(12)

        title = QLabel(f"{word_type.title()}: {lemma}", placeholder)
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(title)

        message = QLabel("Unknown word type.", placeholder)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(message)

        back_button = QPushButton("Go back", placeholder)
        back_button.clicked.connect(self.back_requested.emit)
        placeholder_layout.addWidget(back_button)
        placeholder_layout.addStretch(1)
        layout.addWidget(placeholder)
