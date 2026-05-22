from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from controllers.editor_dirty_state import DirtyState, freeze_payload_mapping
from controllers.verb_editor_state import (
    PARTICIPLE_LABELS,
    PARTICIPLE_TYPES,
    VERB_GROUP_LABELS,
    VerbEditorStateError,
    VerbSavePayload,
    editor_title,
    ensure_verb_word_type,
    extract_forms_from_loaded_verb,
    extract_participles_from_loaded_verb,
    group_tenses,
    ordered_persons,
    person_label_for_group,
)
from database import DatabaseError, SpanishWordDatabase, ValidationError
from widgets.form_card import FormCard
from widgets.header_bar import HeaderBar
from widgets.nullable_line_edit import IrregularNullableLineEdit


class VerbEditor(QWidget):
    """Tabbed verb editor with participles and all seeded Spanish verb forms."""

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
        ensure_verb_word_type(str(self.word_data["word_type"]))
        self.persons = ordered_persons(self.database.list_verb_persons())
        self.tense_groups = group_tenses(self.database.list_verb_tenses())
        self.participle_cells: dict[str, IrregularNullableLineEdit] = {}
        self.form_cells: dict[tuple[str, str], IrregularNullableLineEdit] = {}
        self._loading = False
        self._dirty = DirtyState()

        self._build_ui()
        self._load_data(self.word_data)
        self._mark_clean()

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
        self.lemma_input.textChanged.connect(self._update_title)
        self.lemma_input.textChanged.connect(self._on_any_field_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")
        self.english_input.textChanged.connect(self._on_any_field_changed)

        self.base_card.add_row(0, "Lemma", self.lemma_input)
        self.base_card.add_row(1, "English", self.english_input)
        root.addWidget(self.base_card)

        self.participles_card = FormCard("Participles", self)
        for row, participle_type in enumerate(PARTICIPLE_TYPES):
            cell = IrregularNullableLineEdit(self)
            cell.payload_changed.connect(self._on_any_field_changed)
            self.participle_cells[participle_type] = cell
            self.participles_card.add_row(row, PARTICIPLE_LABELS[participle_type], cell)
        root.addWidget(self.participles_card)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("VerbTabs")
        for group_code, tenses in self.tense_groups.items():
            self.tabs.addTab(
                self._build_group_table(group_code, tenses),
                VERB_GROUP_LABELS[group_code],
            )
        root.addWidget(self.tabs, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self.back_button = QPushButton("Back", self)
        self.back_button.clicked.connect(self.request_back)

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

        self._install_shortcuts()

    def _build_group_table(self, group_code: str, tenses: list[dict[str, Any]]) -> QTableWidget:
        table = QTableWidget(len(self.persons), len(tenses), self)
        table.setObjectName("VerbTable")
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setHorizontalHeaderLabels([str(tense["label"]) for tense in tenses])
        table.setVerticalHeaderLabels([
            person_label_for_group(person, group_code)
            for person in self.persons
        ])

        for column, tense in enumerate(tenses):
            tense_code = str(tense["code"])
            for row, person in enumerate(self.persons):
                person_code = str(person["code"])
                cell = IrregularNullableLineEdit(table)
                cell.payload_changed.connect(self._on_any_field_changed)
                self.form_cells[(tense_code, person_code)] = cell
                table.setCellWidget(row, column, cell)
                table.setItem(row, column, QTableWidgetItem(""))

        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        table.setMinimumHeight(260)
        return table

    def _load_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self.lemma_input.setText(str(data.get("lemma", "")))
            self.english_input.setText(str(data.get("english", "")))

            verb = data.get("verb", {})
            participles = extract_participles_from_loaded_verb(verb)
            for participle_type, payload in participles.items():
                self.participle_cells[participle_type].set_payload(
                    form=payload["form"],
                    is_irregular=bool(payload["is_irregular"]),
                )

            forms = extract_forms_from_loaded_verb(verb)
            for key, payload in forms.items():
                if key in self.form_cells:
                    self.form_cells[key].set_payload(
                        form=payload["form"],
                        is_irregular=bool(payload["is_irregular"]),
                    )
            self._update_title()
        finally:
            self._loading = False

    def _current_snapshot(self) -> tuple[object, ...]:
        participles = {
            participle_type: cell.payload()
            for participle_type, cell in self.participle_cells.items()
        }
        forms = {key: cell.payload() for key, cell in self.form_cells.items()}
        return (
            self.lemma_input.text().strip(),
            self.english_input.text().strip(),
            freeze_payload_mapping(participles),
            freeze_payload_mapping(forms),
        )

    def _mark_clean(self) -> None:
        self._dirty.mark_clean(self._current_snapshot())
        self._sync_dirty_ui()

    def _on_any_field_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._dirty.update(self._current_snapshot())
        self._sync_dirty_ui()

    def is_dirty(self) -> bool:
        return self._dirty.is_dirty

    def _sync_dirty_ui(self) -> None:
        can_save = self._dirty.can_save
        self.header.set_save_enabled(can_save)
        self.save_button.setEnabled(can_save)
        self._update_title()

    def _update_title(self) -> None:
        title = editor_title(self.lemma_input.text())
        if self.is_dirty():
            title = f"{title} *"
        self.header.set_title(title)

    def _install_shortcuts(self) -> None:
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save)

        self.back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.back_shortcut.activated.connect(self.request_back)

    def request_back(self) -> None:
        if self.is_dirty():
            reply = QMessageBox.question(
                self,
                "Discard unsaved changes",
                "Discard unsaved changes and go back?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.back_requested.emit()

    def collect_payload(self) -> VerbSavePayload:
        return VerbSavePayload.from_inputs(
            lemma=self.lemma_input.text(),
            english=self.english_input.text(),
            participles={
                participle_type: cell.payload()
                for participle_type, cell in self.participle_cells.items()
            },
            forms={
                key: cell.payload()
                for key, cell in self.form_cells.items()
            },
        )

    def save(self) -> bool:
        if not self.is_dirty():
            return True

        try:
            payload = self.collect_payload()
            self.database.save_word_base(
                self.word_id,
                lemma=payload.lemma,
                english=payload.english,
            )
            self.database.save_verb_participles(self.word_id, payload.participles)
            self.database.save_verb_forms(self.word_id, payload.forms)
        except (VerbEditorStateError, ValidationError, DatabaseError) as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return False

        self._mark_clean()
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
