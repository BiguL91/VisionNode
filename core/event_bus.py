import threading
import logging
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EventBus")

@dataclass
class Event:
    """Basis-Klasse für alle Events im System."""
    topic: str
    data: Any = None
    sender: Optional[str] = None
    timestamp: float = 0.0


class EventBus:
    """
    Zentraler, thread-sicherer Event Bus.
    Callbacks aus Background-Threads werden automatisch via Qt-Signal (QueuedConnection)
    in den GUI-Thread gereicht. Der Dispatcher wird beim ersten publish() aus dem
    Haupt-Thread lazy initialisiert.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._main_thread_id = threading.get_ident()
        self._qt_dispatcher = None

    def _init_dispatcher(self):
        """Wird einmalig aus dem GUI-Thread heraus aufgerufen."""
        try:
            from PyQt6.QtCore import QObject, pyqtSignal
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is None:
                return

            bus_ref = self

            class _Dispatcher(QObject):
                # object-Typen erlauben beliebige Python-Objekte inkl. None
                _ev = pyqtSignal(object, object, object, object)

                def __init__(self):
                    super().__init__()
                    # AutoConnection → bei Emit aus fremdem Thread automatisch Queued
                    self._ev.connect(self._run)

                def _run(self, callback, event, topic, sender):
                    bus_ref._safe_call(callback, event, topic, sender)

                def post(self, callback, event, topic, sender):
                    self._ev.emit(callback, event, topic, sender)

            self._qt_dispatcher = _Dispatcher()
        except Exception:
            pass

    def subscribe(self, topic: str, callback: Callable):
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            if callback not in self._subscribers[topic]:
                self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable):
        with self._lock:
            if topic in self._subscribers and callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)

    def _safe_call(self, callback, event, topic, sender):
        try:
            callback(event)
        except Exception as e:
            logger.error(f"Fehler im EventBus Callback ({topic}) von {sender}: {e}")

    def publish(self, topic: str, data: Any = None, sender: str = None):
        import time
        event = Event(topic=topic, data=data, sender=sender, timestamp=time.time())

        with self._lock:
            subscribers = self._subscribers.get(topic, []).copy()

        if not subscribers:
            return

        is_main = threading.get_ident() == self._main_thread_id

        if is_main:
            # Lazy-Init des Dispatchers beim ersten Aufruf aus dem Haupt-Thread
            if self._qt_dispatcher is None:
                self._init_dispatcher()
            for callback in subscribers:
                self._safe_call(callback, event, topic, sender)
        else:
            if self._qt_dispatcher is not None:
                # GUI-Thread via Qt AutoConnection erreichen
                for callback in subscribers:
                    self._qt_dispatcher.post(callback, event, topic, sender)
            else:
                # Fallback (kein Qt / Subprocess): direkt aufrufen
                for callback in subscribers:
                    self._safe_call(callback, event, topic, sender)


# Globale Instanz für einfachen Zugriff innerhalb des Prozesses
bus = EventBus()
