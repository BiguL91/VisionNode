from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QScrollArea, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.daten_manager import (
    zeilen_der_liste, zeile_hinzufuegen, zeile_umbenennen, zeile_loeschen,
    liste_umbenennen, liste_loeschen
)

class TimerEditorDialogQt(QDialog):
    """
    Spezialisierter Editor für Timer-Listen.
    Erlaubt das Anlegen und Löschen von globalen Timern.
    """
    gespeichert = pyqtSignal()
    geloescht = pyqtSignal()

    def __init__(self, liste: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Timer verwalten: {liste['name']}")
        self.setModal(False)
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._liste = liste
        self._zeilen = zeilen_der_liste(liste["id"])
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header: Name der Liste
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("Listen-Name:"))
        self._name_edit = QLineEdit(self._liste["name"])
        self._name_edit.editingFinished.connect(self._name_speichern)
        kopf.addWidget(self._name_edit)
        root.addLayout(kopf)

        info = QLabel("Definiere hier deine globalen Timer.\nDiese können im Workflow gesetzt und im FUP abgefragt werden.")
        info.setProperty("class", "lbl_info")
        info.setWordWrap(True)
        root.addWidget(info)

        # Liste der Timer
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(4)
        self.container_layout.addStretch()
        scroll.setWidget(self.container)
        root.addWidget(scroll)

        # Buttons unten
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Timer hinzufügen")
        btn_add.setObjectName("btn_new_sm")
        btn_add.clicked.connect(self._timer_hinzufuegen)
        btn_row.addWidget(btn_add)
        
        btn_del_liste = QPushButton("✕ Liste löschen")
        btn_del_liste.setObjectName("btn_del_sm")
        btn_del_liste.clicked.connect(self._liste_loeschen)
        btn_row.addWidget(btn_del_liste)
        
        root.addLayout(btn_row)

        btn_save = QPushButton("✔ Schließen")
        btn_save.setObjectName("btn_new")
        btn_save.clicked.connect(self.accept)
        root.addWidget(btn_save)

        self._liste_aktualisieren()

    def _liste_aktualisieren(self):
        while self.container_layout.count() > 1:
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._zeilen = zeilen_der_liste(self._liste["id"])
        for i, z in enumerate(self._zeilen):
            row = self._timer_widget_erstellen(z)
            self.container_layout.insertWidget(i, row)

    def _timer_widget_erstellen(self, z: dict):
        f = QFrame()
        f.setObjectName("structure_row")
        l = QHBoxLayout(f)
        l.setContentsMargins(6, 4, 6, 4)

        lbl = QLabel("⏳")
        l.addWidget(lbl)

        edit = QLineEdit(z["name"])
        edit.setPlaceholderText("Timer Name (z.B. Cooldown_X)")
        edit.editingFinished.connect(lambda zid=z["id"], e=edit: self._timer_umbenennen(zid, e.text()))
        l.addWidget(edit)

        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_del_sm")
        btn_del.setFixedWidth(30)
        btn_del.clicked.connect(lambda _, zid=z["id"]: self._timer_loeschen(zid))
        l.addWidget(btn_del)
        return f

    def _timer_hinzufuegen(self):
        zeile_hinzufuegen(self._liste["id"], f"Timer_{len(self._zeilen)+1}")
        self._liste_aktualisieren()

    def _timer_umbenennen(self, zid, neuer_name):
        neuer_name = neuer_name.strip()
        if neuer_name:
            zeile_umbenennen(zid, neuer_name)

    def _timer_loeschen(self, zid):
        zeile_loeschen(zid)
        self._liste_aktualisieren()

    def _name_speichern(self):
        neuer = self._name_edit.text().strip()
        if neuer and neuer != self._liste["name"]:
            liste_umbenennen(self._liste["id"], neuer)
            self._liste["name"] = neuer
            self.gespeichert.emit()

    def _liste_loeschen(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Timer-Liste löschen")
        msg.setText(f"Möchtest du die Timer-Liste '{self._liste['name']}' wirklich löschen?")
        msg.setIcon(QMessageBox.Icon.Question)
        btn_ja = msg.addButton("Ja", QMessageBox.ButtonRole.YesRole)
        btn_nein = msg.addButton("Nein", QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() == btn_ja:
            liste_loeschen(self._liste["id"])
            self.geloescht.emit()
            self.accept()
