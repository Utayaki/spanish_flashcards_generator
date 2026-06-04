from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from controllers.start_page_presenter import highlight_match_html


class AlreadyAddedRow(QFrame):
    """Search result row with open-on-row and delete-on-button behavior."""

    open_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, result: dict[str, Any], query: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.word_id = int(result["id"])
        self.lemma = str(result.get("lemma", "")).strip()
        self.english = str(result.get("english", "")).strip()
        self.setObjectName("AlreadyAddedRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lemma_label = QLabel(highlight_match_html(self.lemma, query), self)
        lemma_label.setTextFormat(Qt.TextFormat.RichText)
        lemma_label.setObjectName("AlreadyAddedLemma")
        lemma_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(lemma_label)
        if self.english:
            english_label = QLabel(self.english, self)
            english_label.setObjectName("AlreadyAddedEnglish")
            english_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            text_layout.addWidget(english_label)

        self.delete_button = QPushButton("Delete", self)
        self.delete_button.setObjectName("DeleteButton")
        self.delete_button.setCursor(Qt.CursorShape.ArrowCursor)
        self.delete_button.clicked.connect(lambda _checked=False: self.delete_requested.emit(self.word_id))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.word_id)
            event.accept()
            return
        super().mousePressEvent(event)
