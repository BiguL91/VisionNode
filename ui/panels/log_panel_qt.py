import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot
from PyQt6.QtGui import QTextCursor, QFont


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("panel_header_lite")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(8, 4, 8, 4)

        lbl = QLabel("LOG")
        lbl.setProperty("class", "lbl_dim")
        h_lay.addWidget(lbl)
        root.addWidget(header)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("log_text")
        self.log_text.setMaximumBlockCount(500)
        root.addWidget(self.log_text, stretch=1)


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
