from __future__ import annotations

from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from controllers.nominal_editor_state import (
    GENDER_CHOICES,
    NominalEditorStateError,
    NominalSavePayload,
    editor_title,
    ensure_nominal_word_type,
    gender_field_label,
    nested_inflections_to_tuple_map,
)
from database import DatabaseError, SpanishWordDatabase, ValidationError
from widgets.form_card import FormCard
from widgets.header_bar import HeaderBar
from widgets.inflection_grid import NominalInflectionGrid


class NominalEditor(QWidget):
    """Card editor for nouns, adjectives, and determiners."""

    back_requested = pyqtSignal()
    deleted = pyqtSignal(int)
    saved = pyqtSignal(int)

    def __init__(
        self,
        database: SpanishWordDatabase,
        word_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.word_id = word_id
        self.word_data = self.database.load_word(word_id)
        self.word_type = ensure_nominal_word_type(str(self.word_data["word_type"]))
        self._loading = False

        self._build_ui()
        self._load_data(self.word_data)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.header = HeaderBar(parent=self)
        self.header.save_requested.connect(self.save)
        root.addWidget(self.header)

        self.base_card = FormCard("Base", self)
        self.lemma_input = QLineEdit(self)
        self.lemma_input.setObjectName("EditorLineEdit")
        self.lemma_input.textChanged.connect(self._on_title_source_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")

        self.gender_combo = QComboBox(self)
        self.gender_combo.setObjectName("GenderAvailabilityCombo")
        for value, label in GENDER_CHOICES:
            self.gender_combo.addItem(label, value)
        self.gender_combo.currentIndexChanged.connect(self._on_gender_changed)

        self.base_card.add_row(0, "Lemma", self.lemma_input)
        self.base_card.add_row(1, "English", self.english_input)
        self.base_card.add_row(2, gender_field_label(self.word_type), self.gender_combo)
        root.addWidget(self.base_card)

        self.inflections_card = FormCard("Inflections", self)
        self.inflection_grid = NominalInflectionGrid(self)
        self.inflections_card.content_layout.addWidget(self.inflection_grid, 0, 0, 1, 2)
        root.addWidget(self.inflections_card)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self.back_button = QPushButton("Back", self)
        self.back_button.clicked.connect(self.back_requested.emit)

        self.delete_button = QPushButton("Delete", self)
        self.delete_button.setObjectName("DeleteButton")
        self.delete_button.clicked.connect(self.delete)

        self.save_button = QPushButton("Save", self)
        self.save_button.setObjectName("BottomSaveButton")
        self.save_button.clicked.connect(self.save)

        button_row.addWidget(self.back_button)
        button_row.addStretch(1)
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.save_button)
        root.addLayout(button_row)
        root.addStretch(1)

    def _load_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self.lemma_input.setText(str(data.get("lemma", "")))
            self.english_input.setText(str(data.get("english", "")))

            nominal = data.get("nominal", {})
            gender_availability = str(nominal.get("gender_availability", "both"))
            self._set_combo_value(gender_availability)
            self.inflection_grid.set_gender_availability(gender_availability)
            self.inflection_grid.set_forms(
                nested_inflections_to_tuple_map(nominal.get("inflections"))
            )
            self._update_title()
        finally:
            self._loading = False

    def _set_combo_value(self, value: str) -> None:
        index = self.gender_combo.findData(value)
        if index < 0:
            index = self.gender_combo.findData("both")
        self.gender_combo.setCurrentIndex(index)

    def _current_gender_availability(self) -> str:
        return str(self.gender_combo.currentData())

    def _on_gender_changed(self) -> None:
        if self._loading:
            return
        self.inflection_grid.set_gender_availability(self._current_gender_availability())

    def _on_title_source_changed(self) -> None:
        self._update_title()

    def _update_title(self) -> None:
        self.header.set_title(editor_title(self.word_type, self.lemma_input.text()))

    def collect_payload(self) -> NominalSavePayload:
        return NominalSavePayload.from_inputs(
            lemma=self.lemma_input.text(),
            english=self.english_input.text(),
            gender_availability=self._current_gender_availability(),
            forms=self.inflection_grid.forms(),
        )

    def save(self) -> bool:
        try:
            payload = self.collect_payload()
            self.database.save_word_base(
                self.word_id,
                lemma=payload.lemma,
                english=payload.english,
            )
            self.database.save_nominal_details(
                self.word_id,
                payload.gender_availability,
            )
            self.database.save_nominal_inflections(self.word_id, payload.forms)
        except (NominalEditorStateError, ValidationError, DatabaseError) as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return False

        self._update_title()
        self.saved.emit(self.word_id)
        return True

    def delete(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete word",
            f"Delete {self.lemma_input.text().strip() or 'this word'}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.database.delete_word(self.word_id):
            self.deleted.emit(self.word_id)
        else:
            QMessageBox.warning(self, "Delete failed", "This word was not found in the database.")
