from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


class HeaderBar(QWidget):
    """Reusable editor header with a title only.

    Save actions live in the bottom action bar so each editor has one clear
    save path: Save and go back.
    """

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("HeaderTitle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.title_label, 1)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
