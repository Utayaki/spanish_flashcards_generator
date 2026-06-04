from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QMessageBox,
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
    empty_participles,
    ensure_verb_word_type,
    extract_forms_from_loaded_verb,
    extract_participles_from_loaded_verb,
    group_tenses,
    ordered_persons,
    person_label_for_group,
)
from database import DatabaseError, SpanishWordDatabase, ValidationError
from widgets.editor_action_bar import EditorActionBar
from widgets.form_card import FormCard
from widgets.header_bar import HeaderBar
from widgets.nullable_line_edit import IrregularNullableLineEdit


class VerbEditor(QWidget):
    """Tabbed verb editor with participles and all seeded forms."""

    back_requested = pyqtSignal()
    saved = pyqtSignal(int)

    @classmethod
    def existing(cls, database: SpanishWordDatabase, *, word_id: int, parent: QWidget | None = None) -> "VerbEditor":
        return cls(database, word_id=word_id, parent=parent)

    @classmethod
    def new_draft(cls, database: SpanishWordDatabase, *, lemma: str, parent: QWidget | None = None) -> "VerbEditor":
        return cls(database, lemma=lemma, parent=parent)

    def __init__(
        self,
        database: SpanishWordDatabase,
        *,
        word_id: int | None = None,
        lemma: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.word_id = word_id
        self.persons = ordered_persons(self.database.list_verb_persons())
        self.tense_groups = group_tenses(self.database.list_verb_tenses())
        self.participle_cells: dict[str, IrregularNullableLineEdit] = {}
        self.form_cells: dict[tuple[str, str], IrregularNullableLineEdit] = {}
        self._loading = False
        self._dirty = DirtyState()

        if word_id is not None:
            self.word_data = self.database.load_word(word_id)
            ensure_verb_word_type(str(self.word_data["word_type"]))
        else:
            self.word_data = {
                "id": None,
                "lemma": lemma,
                "english": "",
                "word_type": "verb",
                "verb": {"participles": empty_participles(), "forms": {}},
            }

        self._build_ui()
        self._load_data(self.word_data)
        self._mark_clean()
        self._sync_availability()
        self._sync_dirty_ui()

    @property
    def is_new(self) -> bool:
        return self.word_id is None

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.header = HeaderBar(parent=self)
        root.addWidget(self.header)

        self.base_card = FormCard("Base", self)
        self.lemma_input = QLineEdit(self)
        self.lemma_input.setObjectName("EditorLineEdit")
        self.lemma_input.setReadOnly(self.is_new)
        self.lemma_input.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.lemma_input.textChanged.connect(self._update_title)
        self.lemma_input.textChanged.connect(self._on_any_field_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")
        self.english_input.setPlaceholderText("Write the English definition first")
        self.english_input.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.english_input.textChanged.connect(self._on_any_field_changed)

        self.base_card.add_row(0, "Lemma", self.lemma_input)
        self.base_card.add_row(1, "English", self.english_input)
        root.addWidget(self.base_card)

        self.helper_label = QLabel("", self)
        self.helper_label.setObjectName("HelperText")
        root.addWidget(self.helper_label)

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
            self.tabs.addTab(self._build_group_table(group_code, tenses), VERB_GROUP_LABELS[group_code])
        root.addWidget(self.tabs, 1)

        self.action_bar = EditorActionBar(self)
        self.action_bar.discard_requested.connect(self.request_back)
        self.action_bar.save_requested.connect(self.save_and_go_back)
        root.addWidget(self.action_bar)
        self._install_shortcuts()

    def _build_group_table(self, group_code: str, tenses: list[dict[str, Any]]) -> QTableWidget:
        table = QTableWidget(len(self.persons), len(tenses), self)
        table.setObjectName("VerbTable")
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setHorizontalHeaderLabels([str(tense["label"]) for tense in tenses])
        table.setVerticalHeaderLabels([person_label_for_group(person, group_code) for person in self.persons])
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
                    explicit_none=not self.is_new,
                )
            forms = extract_forms_from_loaded_verb(verb)
            for key, payload in forms.items():
                if key in self.form_cells:
                    self.form_cells[key].set_payload(
                        form=payload["form"],
                        is_irregular=bool(payload["is_irregular"]),
                        explicit_none=not self.is_new,
                    )
            self._update_title()
        finally:
            self._loading = False

    def _has_english_definition(self) -> bool:
        return bool(self.english_input.text().strip())

    def _cells_complete(self) -> bool:
        return all(cell.is_complete() for cell in self.participle_cells.values()) and all(
            cell.is_complete() for cell in self.form_cells.values()
        )

    def _is_valid_for_save(self) -> bool:
        return bool(self.lemma_input.text().strip()) and self._has_english_definition() and self._cells_complete()

    def _sync_availability(self) -> None:
        unlocked = self._has_english_definition()
        self.participles_card.setVisible(unlocked)
        self.participles_card.setEnabled(unlocked)
        self.tabs.setVisible(unlocked)
        self.tabs.setEnabled(unlocked)
        if not unlocked:
            self.helper_label.setText("Enter the English definition to unlock participles and conjugations.")
            self.helper_label.setVisible(True)
        elif not self._cells_complete():
            self.helper_label.setText("Every visible verb cell must be filled or explicitly marked None.")
            self.helper_label.setVisible(True)
        else:
            self.helper_label.setVisible(False)

    def _current_snapshot(self) -> tuple[object, ...]:
        participles = {participle_type: cell.payload() for participle_type, cell in self.participle_cells.items()}
        forms = {key: cell.payload() for key, cell in self.form_cells.items()}
        return (
            self.lemma_input.text().strip(),
            self.english_input.text().strip(),
            freeze_payload_mapping(participles),
            freeze_payload_mapping(forms),
            self._cells_complete(),
        )

    def _mark_clean(self) -> None:
        self._dirty.mark_clean(self._current_snapshot())
        self._sync_dirty_ui()

    def _on_any_field_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._sync_availability()
        self._dirty.update(self._current_snapshot())
        self._sync_dirty_ui()

    def is_dirty(self) -> bool:
        return self._dirty.is_dirty

    def _sync_dirty_ui(self) -> None:
        can_save = self._is_valid_for_save() and (self.is_dirty() or self.is_new)
        self.action_bar.set_dirty(self.is_dirty(), is_new=self.is_new)
        self.action_bar.set_save_enabled(can_save)
        self._update_title()

    def _update_title(self) -> None:
        title = editor_title(self.lemma_input.text())
        if self.is_dirty():
            title = f"{title} *"
        self.header.set_title(title)

    def _install_shortcuts(self) -> None:
        # Do not install Ctrl-based shortcuts. On some non-English layouts,
        # AltGr is reported as Ctrl+Alt and shortcut handlers can steal normal
        # text input from QLineEdit. Escape is safe because it does not produce
        # text.
        self.back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.back_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.back_shortcut.activated.connect(self.request_back)

    def request_back(self) -> None:
        if self.is_dirty():
            reply = QMessageBox.question(
                self,
                "Discard unsaved changes",
                "Go back without saving these changes?",
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
            participles={participle_type: cell.payload() for participle_type, cell in self.participle_cells.items()},
            forms={key: cell.payload() for key, cell in self.form_cells.items()},
        )

    def save(self) -> bool:
        if not self._is_valid_for_save():
            QMessageBox.warning(
                self,
                "Cannot save",
                "Complete the English definition and every visible verb cell first.",
            )
            return False
        if not self.is_new and not self.is_dirty():
            return True
        try:
            payload = self.collect_payload()
            if self.is_new:
                self.word_id = self.database.create_verb_word(
                    lemma=payload.lemma,
                    english=payload.english,
                    participles=payload.participles,
                    forms=payload.forms,
                )
                self.lemma_input.setReadOnly(False)
            else:
                assert self.word_id is not None
                self.database.save_word_base(self.word_id, lemma=payload.lemma, english=payload.english)
                self.database.save_verb_participles(self.word_id, payload.participles)
                self.database.save_verb_forms(self.word_id, payload.forms)
        except (VerbEditorStateError, ValidationError, DatabaseError) as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return False
        self._mark_clean()
        assert self.word_id is not None
        self.saved.emit(self.word_id)
        return True

    def save_and_go_back(self) -> None:
        if self.save():
            self.back_requested.emit()
