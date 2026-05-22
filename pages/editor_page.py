from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from database import NOMINAL_WORD_TYPES, SpanishWordDatabase
from editors.nominal_editor import NominalEditor


class EditorPage(QWidget):
    """Routes a loaded word to the correct editor widget.

    Phase 6 implements noun/adjective/determiner card editors. Verb and other
    editors are intentionally left as placeholders for their later phases.
    """

    back_requested = pyqtSignal()

    def __init__(
        self,
        database: SpanishWordDatabase,
        word_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.word_id = word_id
        self._build_ui()

    def _build_ui(self) -> None:
        word = self.database.load_word(self.word_id)
        word_type = str(word["word_type"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if word_type in NOMINAL_WORD_TYPES:
            editor = NominalEditor(self.database, self.word_id, self)
            editor.back_requested.connect(self.back_requested.emit)
            editor.deleted.connect(lambda _word_id: self.back_requested.emit())
            layout.addWidget(editor)
            return

        placeholder = QWidget(self)
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(24, 24, 24, 24)
        placeholder_layout.setSpacing(12)

        title = QLabel(f"{word_type.title()}: {word['lemma']}", placeholder)
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(title)

        message = QLabel(
            "This editor is planned for a later phase.",
            placeholder,
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(message)

        back_button = QPushButton("Back", placeholder)
        back_button.clicked.connect(self.back_requested.emit)
        placeholder_layout.addWidget(back_button)
        placeholder_layout.addStretch(1)
        layout.addWidget(placeholder)
