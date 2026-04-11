import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot
from PyQt6.QtGui import QTextCursor, QFont


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 8))
        self.log_text.setStyleSheet(
            "QPlainTextEdit { background-color: #1a1a1a; color: #888888; border: none; }"
        )
        self.log_text.setMaximumBlockCount(500)  # Max 500 Zeilen, älteste fliegen raus
        layout.addWidget(self.log_text)

    @pyqtSlot(str)
    def log(self, message: str):
        """Thread-sicher: kann aus beliebigem Thread aufgerufen werden."""
        if self.thread() != __import__("threading").current_thread().__class__:
            # Aus anderem Thread → ins Qt-MainThread weiterleiten
            QMetaObject.invokeMethod(
                self, "_log_main_thread",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, message)
            )
        else:
            self._log_main_thread(message)

    @pyqtSlot(str)
    def _log_main_thread(self, message: str):
        ts = time.strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"{ts}  {message}")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
