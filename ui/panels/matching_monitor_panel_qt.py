"""
Matching-Monitor Panel (Qt). 
Zeigt live an, welche Templates in wie vielen ROIs gescannt werden.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
from PyQt6.QtCore import Qt, pyqtSlot
from core.event_bus import bus

class MatchingMonitorPanel(QWidget):
    def __init__(self, bot_win=None, parent=None):
        super().__init__(parent)
        self.bot_win = bot_win
        self._setup_ui()
        self._connect_bus()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.lbl_info = QLabel("Aktive Suche (Templates & ROIs):")
        self.lbl_info.setProperty("class", "lbl_dim_sm")
        layout.addWidget(self.lbl_info)

        self.liste = QListWidget()
        self.liste.setObjectName("matching_monitor_list")
        self.liste.setStyleSheet("""
            QListWidget#matching_monitor_list {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                color: #aaaaaa;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.liste)

    def _connect_bus(self):
        # Wir lauschen auf das Event aus main_app
        bus.subscribe("matching.stats", self._on_stats_received)

    def _on_stats_received(self, event):
        stats = event.data
        self.liste.clear()
        if not stats or not isinstance(stats, dict):
            return

        # Sortieren nach ROI-Anzahl (Fullscreen oben)
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=False)
        
        for name, count in sorted_stats:
            if count == 0:
                roi_str = "Fullscreen"
            elif count == 1:
                roi_str = "1 ROI"
            else:
                roi_str = f"{count} ROIs"
            
            # Name kürzen für bessere Lesbarkeit im schmalen Dock
            display_name = name
            if len(display_name) > 30:
                display_name = "..." + display_name[-27:]

            item = QListWidgetItem(f"{display_name:<30} {roi_str:>12}")
            
            if count == 0 and not name.startswith("state/"):
                item.setForeground(Qt.GlobalColor.yellow)
            
            self.liste.addItem(item)
