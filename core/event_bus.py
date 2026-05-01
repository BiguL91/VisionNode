import threading
import logging
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass

# Setup Logging für den Bus
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
    Ein zentraler, thread-sicherer Event Bus für die Entkopplung der Engines.
    Ermöglicht Pub/Sub Kommunikation.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, topic: str, callback: Callable):
        """Abonniert ein Thema mit einer Callback-Funktion."""
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            if callback not in self._subscribers[topic]:
                self._subscribers[topic].append(callback)
                # logger.debug(f"Abonnement: {callback.__name__} für Thema '{topic}'")

    def unsubscribe(self, topic: str, callback: Callable):
        """Beendet ein Abonnement."""
        with self._lock:
            if topic in self._subscribers and callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)

    def publish(self, topic: str, data: Any = None, sender: str = None):
        """
        Publiziert Daten unter einem bestimmten Thema.
        Die Callbacks werden aktuell synchron im Thread des Publishers ausgeführt.
        """
        import time
        event = Event(topic=topic, data=data, sender=sender, timestamp=time.time())
        
        with self._lock:
            # Wir kopieren die Liste, falls sich während der Iteration Abonnements ändern
            subscribers = self._subscribers.get(topic, []).copy()
            # Unterstützung für Wildcards (z.B. "ocr.*") könnte man hier später einbauen
        
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Fehler im EventBus Callback ({topic}) von {sender}: {e}")

# Globale Instanz für einfachen Zugriff innerhalb des Prozesses
bus = EventBus()
