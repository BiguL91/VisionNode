import os
import json
from PyQt6.QtWidgets import QWidget, QDialog
from PyQt6.QtCore import QByteArray, QObject, QEvent

APP_CONFIG_DATEI = os.path.join("templates", "settings", "app_config.json")

class GeometryFilter(QObject):
    """Event-Filter, der beim Verstecken (Hide) des Widgets die Geometrie speichert."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Hide:
            try:
                GeometryManager.save_geometry(obj)
            except RuntimeError:
                pass # Objekt bereits weg
        return super().eventFilter(obj, event)

class GeometryManager:
    """Verwaltet das Speichern und Laden von Fenstergeometrien."""
    
    _filter = None

    @classmethod
    def get_filter(cls):
        if cls._filter is None:
            cls._filter = GeometryFilter()
        return cls._filter

    @staticmethod
    def _load_config():
        if os.path.exists(APP_CONFIG_DATEI):
            try:
                with open(APP_CONFIG_DATEI, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def _save_config(config):
        try:
            os.makedirs(os.path.dirname(APP_CONFIG_DATEI), exist_ok=True)
            with open(APP_CONFIG_DATEI, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    @classmethod
    def restore_geometry(cls, widget: QWidget, key: str = None):
        """Stellt die Geometrie eines Widgets wieder her."""
        if key is None:
            key = widget.objectName() or widget.__class__.__name__
            if isinstance(widget, QDialog) and not key.startswith("dialog_"):
                key = f"dialog_{key}"
        
        config = cls._load_config()
        # Unterscheidung zwischen Hauptfenster (direkt in config) und Dialogen
        if isinstance(widget, QDialog):
            geo = config.get("dialog_geometrien", {}).get(key)
        else:
            geo = config.get(f"geom_{key}")
            
        if geo:
            widget.restoreGeometry(QByteArray.fromHex(geo.encode()))

    @classmethod
    def save_geometry(cls, widget: QWidget, key: str = None):
        """Speichert die Geometrie eines Widgets."""
        if key is None:
            key = widget.objectName() or widget.__class__.__name__
            if isinstance(widget, QDialog) and not key.startswith("dialog_"):
                key = f"dialog_{key}"
            
        config = cls._load_config()
        geo_hex = widget.saveGeometry().toHex().data().decode()
        
        if isinstance(widget, QDialog):
            if "dialog_geometrien" not in config:
                config["dialog_geometrien"] = {}
            config["dialog_geometrien"][key] = geo_hex
        else:
            config[f"geom_{key}"] = geo_hex
            
        cls._save_config(config)

    @classmethod
    def restore_window_state(cls, window, key: str = "main_window"):
        """Stellt den State (Docks/Toolbars) des Hauptfensters wieder her."""
        config = cls._load_config()
        state = config.get(f"state_{key}")
        if state:
            window.restoreState(QByteArray.fromHex(state.encode()))

    @classmethod
    def save_window_state(cls, window, key: str = "main_window"):
        """Speichert den State (Docks/Toolbars) des Hauptfensters."""
        config = cls._load_config()
        config[f"state_{key}"] = window.saveState().toHex().data().decode()
        cls._save_config(config)
