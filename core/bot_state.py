from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class BotState:
    """Zentraler Status des Bots (Entkoppelt von der UI)."""
    
    # Laufzeit-Status
    running: bool = False
    is_paused: bool = False
    
    # Fenster / Capture
    memu_hwnd: Optional[int] = None
    capture_active: bool = False
    
    # Erkennungsergebnisse
    active_matches: List[Any] = field(default_factory=list)
    ocr_values: Dict[str, str] = field(default_factory=dict)
    template_ocr_values: Dict[str, str] = field(default_factory=dict)
    
    # UI Modus
    einlern_modus: bool = False
    ocr_modus: bool = False
    
    # Mapping-Daten (Canvas <-> Screenshot)
    bild_offset_x: int = 0
    bild_offset_y: int = 0
    bild_skalierung_x: float = 1.0
    bild_skalierung_y: float = 1.0
    
    # Cache für Änderungserkennung
    last_logged_ocr: Dict[str, str] = field(default_factory=dict)
    
    # Game State (z.B. Map=True, City=False)
    game_states: Dict[str, bool] = field(default_factory=dict)
    
    # Fokusiertes Template im Editor (wird immer gescannt, ignoriert States)
    editor_template_name: Optional[str] = None

    def set_game_state(self, name: str, value: bool):
        """Setzt eine Status-Variable."""
        self.game_states[name] = value

    def get_game_state(self, name: str, default: bool = False) -> bool:
        """Gibt den Wert einer Status-Variable zurück."""
        return self.game_states.get(name, default)

    def get_all_ocr(self) -> Dict[str, str]:
        """Kombiniert feste Regionen und Template-OCR."""
        return {**self.ocr_values, **self.template_ocr_values}
