from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class HeaderBar(QWidget):
    """Reusable editor header: title on the left, Save button on the right."""

    save_requested = pyqtSignal()

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("HeaderTitle")

        self.save_button = QPushButton("Save", self)
        self.save_button.setObjectName("HeaderSaveButton")
        self.save_button.clicked.connect(self.save_requested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.save_button)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_save_enabled(self, enabled: bool) -> None:
        self.save_button.setEnabled(enabled)
