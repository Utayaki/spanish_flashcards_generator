from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget


class FormCard(QFrame):
    """Small bordered card with a title and a form layout area."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FormCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("FormCardTitle")

        self.content_layout = QGridLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setHorizontalSpacing(8)
        self.content_layout.setVerticalSpacing(6)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)
        outer.addWidget(self.title_label)
        outer.addLayout(self.content_layout)

    def add_row(self, row: int, label: str, widget: QWidget) -> None:
        label_widget = QLabel(label, self)
        label_widget.setObjectName("FormCardFieldLabel")
        self.content_layout.addWidget(label_widget, row, 0)
        self.content_layout.addWidget(widget, row, 1)
