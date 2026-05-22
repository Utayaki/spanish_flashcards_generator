from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox

from database import SpanishWordDatabase
from pages.editor_page import EditorPage
from pages.start_page import StartPage


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "spanish_words.db"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spanish Word DB")
        self.resize(540, 620)

        self.database = SpanishWordDatabase(DB_PATH)
        self.setStyleSheet(_style_sheet())
        self.show_start_page()

    def show_start_page(self) -> None:
        start_page = StartPage(self.database)
        start_page.open_word_requested.connect(self.show_editor_page)
        self.setCentralWidget(start_page)

    def show_editor_page(self, word_id: int) -> None:
        word = self.database.get_word_summary(word_id)
        if word is None:
            QMessageBox.warning(self, "Word not found", f"Word id {word_id} was not found.")
            return

        editor_page = EditorPage(self.database, word_id)
        editor_page.back_requested.connect(self.show_start_page)
        self.setCentralWidget(editor_page)


def _style_sheet() -> str:
    return """
        QWidget {
            font-size: 13px;
        }
        #PageTitle {
            font-size: 20px;
            font-weight: 600;
        }
        #ClassButton, #CreateButton {
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
        #AlreadyAddedEnglish, #NoneLabel {
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
    """


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
