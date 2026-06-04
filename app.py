from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox

from controllers.editor_mode import NewWordDraft
from database import SpanishWordDatabase
from pages.editor_page import EditorPage
from pages.start_page import StartPage


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "spanish_words.db"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spanish Word DB")
        self.resize(720, 680)

        self.database = SpanishWordDatabase(DB_PATH)
        self.setStyleSheet(_style_sheet())
        self.show_start_page()

    def show_start_page(self) -> None:
        start_page = StartPage(self.database)
        start_page.open_word_requested.connect(self.show_existing_editor_page)
        start_page.create_word_requested.connect(self.show_new_editor_page)
        self.setCentralWidget(start_page)

    def show_existing_editor_page(self, word_id: int) -> None:
        word = self.database.get_word_summary(word_id)
        if word is None:
            QMessageBox.warning(self, "Word not found", f"Word id {word_id} was not found.")
            return

        editor_page = EditorPage(self.database, word_id=word_id)
        editor_page.back_requested.connect(self.show_start_page)
        self.setCentralWidget(editor_page)

    def show_new_editor_page(self, word_type: str, lemma: str) -> None:
        try:
            draft = NewWordDraft(word_type=word_type, lemma=lemma)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot create word", str(exc))
            return

        editor_page = EditorPage(self.database, draft=draft)
        editor_page.back_requested.connect(self.show_start_page)
        self.setCentralWidget(editor_page)


# Backwards-compatible alias for old signal hookups or local scripts.
MainWindow.show_editor_page = MainWindow.show_existing_editor_page  # type: ignore[attr-defined]


def _style_sheet() -> str:
    return """
        QWidget {
            font-size: 13px;
        }
        #PageTitle {
            font-size: 20px;
            font-weight: 600;
        }
        #ClassButton, #CreateButton, #SaveBackButton, #DiscardBackButton {
            min-height: 34px;
            padding: 4px 10px;
        }
        #SelectedClassLabel {
            font-size: 16px;
            font-weight: 600;
        }
        #FieldLabel, #AlreadyAddedTitle {
            font-weight: 600;
        }
        #LemmaInput, #EditorLineEdit {
            min-height: 30px;
            padding: 2px 6px;
        }
        #AlreadyAddedRow {
            border: 1px solid palette(mid);
            border-radius: 6px;
        }
        #AlreadyAddedEnglish, #NoneLabel, #HelperText {
            color: palette(mid);
        }
        #HeaderTitle {
            font-size: 18px;
            font-weight: 600;
        }
        #FormCard {
            border: 1px solid palette(mid);
            border-radius: 8px;
        }
        #FormCardTitle {
            font-weight: 600;
        }
        #FormCardFieldLabel, #GridHeaderLabel {
            font-weight: 600;
        }
        #DeleteButton {
            color: #b00020;
        }
        #SaveBackButton {
            font-weight: 600;
        }
        #VerbTabs::pane {
            border: 1px solid palette(mid);
            border-radius: 6px;
        }
        #VerbTable {
            gridline-color: palette(mid);
        }
    """


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
