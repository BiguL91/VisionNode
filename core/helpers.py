import win32gui
import numpy as np
from PIL import Image

# Name des MEMUPlayer-Fensters (Teilstring genügt)
MEMU_FENSTERTITEL = "MEmu"

# Farben für Match-Rahmen (pro Template-Name gleichbleibend)
_RAHMEN_FARBEN = [
    "#ef5350", "#ab47bc", "#42a5f5", "#26c6da",
    "#66bb6a", "#ffca28", "#ff7043", "#8d6e63",
]

def _template_farbe(name):
    """Gibt eine konsistente Farbe für einen Template-Namen zurück."""
    return _RAHMEN_FARBEN[hash(name) % len(_RAHMEN_FARBEN)]

# ---------------------------------------------------------------------------
# Windows Graphics Capture (WGC) – primäre Capture-Methode
# ---------------------------------------------------------------------------


def memu_fenster_finden():
    """Sucht das MEMUPlayer-Fenster und gibt das Handle zurück."""
    gefunden = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            titel = win32gui.GetWindowText(hwnd)
            if MEMU_FENSTERTITEL.lower() in titel.lower():
                gefunden.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return gefunden[0] if gefunden else None


# ---------------------------------------------------------------------------
# Windows Graphics Capture (WGC) – primäre Capture-Methode
# ---------------------------------------------------------------------------

class _WGCKamera:
    """Wraps Windows.Graphics.Capture für synchrones frame.grab()."""

    def __init__(self, fenster_titel):
        from windows_capture import WindowsCapture

        self._letzter_frame = None  # BGR numpy array
        self._fehler = None

        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            window_name=fenster_titel,
        )

        kamera = self

        @capture.event
        def on_frame_arrived(frame, capture_control):
            buf = frame.frame_buffer          # numpy BGRA uint8
            if buf.ndim == 3 and buf.shape[2] >= 3:
                kamera._letzter_frame = buf[:, :, :3].copy()  # BGRA → BGR

        @capture.event
        def on_closed():
            kamera._letzter_frame = None

        capture.start_free_threaded()
        self._capture = capture

    def grab(self):
        return self._letzter_frame

    def stoppen(self):
        try:
            self._capture.stop()
        except Exception:
            pass


_wgc_kamera: _WGCKamera | None = None


def wgc_starten(fenster_titel):
    """Erstellt und startet eine WGC-Kamera-Instanz. Wirft Exception bei Fehler."""
    global _wgc_kamera
    _wgc_kamera = _WGCKamera(fenster_titel)


def fenster_screenshot_wgc():
    """Liefert den letzten WGC-Frame als BGR numpy array oder None."""
    if _wgc_kamera is None:
        return None
    return _wgc_kamera.grab()


def wgc_stoppen():
    global _wgc_kamera
    if _wgc_kamera is not None:
        _wgc_kamera.stoppen()
        _wgc_kamera = None


# ---------------------------------------------------------------------------
# mss – Fallback
# ---------------------------------------------------------------------------

def fenster_screenshot_mss(hwnd, sct):
    """mss-basierter Screenshot als numpy BGR-Array. Fallback wenn WGC nicht verfügbar."""
    try:
        client_rect = win32gui.GetClientRect(hwnd)
        breite = client_rect[2]
        hoehe = client_rect[3]
        if breite <= 0 or hoehe <= 0:
            return None, 0, 0
        x, y = win32gui.ClientToScreen(hwnd, (0, 0))
        monitor = {"top": y, "left": x, "width": breite, "height": hoehe}
        screenshot = sct.grab(monitor)
        import cv2
        frame = cv2.cvtColor(
            np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape(hoehe, breite, 4),
            cv2.COLOR_BGRA2BGR
        )
        return frame, breite, hoehe
    except Exception:
        return None, 0, 0


def fenster_screenshot(hwnd, sct):
    """Kompatibilitäts-Wrapper – gibt PIL Image zurück (für OCR-Engine)."""
    try:
        client_rect = win32gui.GetClientRect(hwnd)
        breite = client_rect[2]
        hoehe = client_rect[3]
        if breite <= 0 or hoehe <= 0:
            return None
        x, y = win32gui.ClientToScreen(hwnd, (0, 0))
        monitor = {"top": y, "left": x, "width": breite, "height": hoehe}
        screenshot = sct.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    except Exception:
        return None

class SharedFrameBuffer:
    """Verwaltet einen Shared Memory Block für Screenshots (Zero-Copy)."""
    def __init__(self, name: str, size_mb: int = 40, create: bool = False):
        from multiprocessing import shared_memory
        self.name = name
        self.size = size_mb * 1024 * 1024
        self.shm = None
        
        try:
            if create:
                # Alten Puffer gleichen Namens aufräumen falls nötig
                try:
                    temp_shm = shared_memory.SharedMemory(name=name)
                    temp_shm.close()
                    temp_shm.unlink()
                except: pass
                self.shm = shared_memory.SharedMemory(name=name, create=True, size=self.size)
            else:
                self.shm = shared_memory.SharedMemory(name=name)
        except Exception as e:
            print(f"[SharedMemory] Fehler: {e}")

    def write_frame(self, frame_np: np.ndarray):
        """Kopiert den Frame in den Shared Memory Bereich."""
        if self.shm is None or frame_np is None:
            return
        # Wir nutzen einen View auf den SHM-Puffer
        target = np.ndarray(frame_np.shape, dtype=frame_np.dtype, buffer=self.shm.buf)
        target[:] = frame_np[:]

    def get_frame(self, shape, dtype) -> np.ndarray:
        """Gibt einen Numpy-View auf den Shared Memory Bereich zurück (Zero-Copy)."""
        if self.shm is None:
            return None
        return np.ndarray(shape, dtype=dtype, buffer=self.shm.buf)

    def close(self):
        if self.shm:
            self.shm.close()

    def unlink(self):
        if self.shm:
            try: self.shm.unlink()
            except: pass
