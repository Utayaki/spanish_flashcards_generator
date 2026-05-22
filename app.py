from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from database import SpanishWordDatabase
from pages.start_page import StartPage


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "spanish_words.db"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spanish Word DB")
        self.resize(420, 560)

        self.database = SpanishWordDatabase(DB_PATH)
        self.start_page = StartPage(self.database)
        self.start_page.open_word_requested.connect(self._show_editor_placeholder)

        self.setCentralWidget(self.start_page)
        self.setStyleSheet(_style_sheet())

    def _show_editor_placeholder(self, word_id: int) -> None:
        """Temporary Phase 3 handler.

        Phase 4 replaces this with the real editor page. For now, this confirms
        the start page successfully opened or created a word.
        """

        word = self.database.get_word_summary(word_id)
        if word is None:
            QMessageBox.warning(self, "Word not found", f"Word id {word_id} was not found.")
            return

        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(f"{word['word_type'].title()}: {word['lemma']}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        message = QLabel("Editor page will be implemented in the next phase.")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)

        self.setCentralWidget(placeholder)


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
        #LemmaInput {
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
    """


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
