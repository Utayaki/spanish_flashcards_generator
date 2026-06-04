from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class EditorActionBar(QWidget):
    """Bottom actions: leave without writing, or save and leave."""

    discard_requested = pyqtSignal()
    save_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EditorActionBar")
        self.discard_button = QPushButton("Go back", self)
        self.discard_button.setObjectName("DiscardBackButton")
        self.discard_button.clicked.connect(self.discard_requested.emit)
        self.save_button = QPushButton("Save and go back", self)
        self.save_button.setObjectName("SaveBackButton")
        self.save_button.clicked.connect(self.save_requested.emit)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.discard_button)
        layout.addStretch(1)
        layout.addWidget(self.save_button)

    def set_dirty(self, dirty: bool, *, is_new: bool = False) -> None:
        self.discard_button.setText("Go back without saving" if dirty or is_new else "Go back")

    def set_save_enabled(self, enabled: bool) -> None:
        self.save_button.setEnabled(enabled)
