import win32gui
import numpy as np
import multiprocessing as mp
from PIL import Image

MEMU_FENSTERTITEL = "MEmu"

_RAHMEN_FARBEN = [
    "#ef5350", "#ab47bc", "#42a5f5", "#26c6da",
    "#66bb6a", "#ffca28", "#ff7043", "#8d6e63",
]

def _template_farbe(name):
    return _RAHMEN_FARBEN[hash(name) % len(_RAHMEN_FARBEN)]


def memu_fenster_finden():
    gefunden = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            titel = win32gui.GetWindowText(hwnd)
            if MEMU_FENSTERTITEL.lower() in titel.lower():
                gefunden.append(hwnd)
    win32gui.EnumWindows(callback, None)
    return gefunden[0] if gefunden else None


# ---------------------------------------------------------------------------
# WGC-Subprocess – isoliert den instabilen windows_capture-Buffer-Zugriff.
# Der Rust-Thread gibt D3D11-Staging-Buffer ohne GIL frei → egal welche
# Python-Kopiermethode wir nutzen, der Hauptprozess kann abstürzen.
# Lösung: WGC läuft in einem eigenen Subprocess. Crash dort → kein Crash
# im Hauptprozess, _capture_loop fällt auf mss zurück.
# ---------------------------------------------------------------------------

# Shared-Memory-Layout: [h(i32), w(i32), frame_id(i32), pad(i32)] = 16 Bytes Header
# ab Byte 16: BGR-Framedaten
_WGC_SHM_NAME  = "bot_wgc_frame"
_WGC_SHM_BYTES = 30 * 1024 * 1024   # 30 MB → reicht für 4K BGR

_wgc_proc: mp.Process | None = None
_wgc_shm  = None   # multiprocessing.shared_memory.SharedMemory


def _wgc_subprocess(shm_name: str, shm_size: int, hwnd):
    """Läuft isoliert. Schreibt WGC-Frames in Shared Memory."""
    import faulthandler, ctypes, numpy as np, threading, time, warnings
    faulthandler.enable(file=open("crash_subprocess.log", "a"))
    warnings.filterwarnings("ignore")

    from multiprocessing import shared_memory as shm_mod

    try:
        shm = shm_mod.SharedMemory(name=shm_name)
    except Exception:
        return

    header = np.ndarray(4, dtype=np.int32, buffer=shm.buf)

    try:
        from windows_capture import WindowsCapture

        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            window_hwnd=hwnd if hwnd else None,
            window_name=None,
            minimum_update_interval=33,
        )

        @capture.event
        def on_frame_arrived(frame, capture_control):
            try:
                buf = frame.frame_buffer
                if buf.ndim != 3 or buf.shape[2] < 3:
                    return
                h, w      = buf.shape[:2]
                row_stride = buf.strides[0]
                row_bytes  = w * 4

                # Kopie aus Rust-Buffer (kann hier crashen – isoliert im Subprocess)
                total = h * row_stride
                tmp = np.empty(total, dtype=np.uint8)
                ctypes.memmove(tmp.ctypes.data, buf.ctypes.data, total)

                # BGR extrahieren (alles Python-Speicher ab hier)
                if row_stride == row_bytes:
                    bgr = np.ascontiguousarray(tmp.reshape(h, w, 4)[:, :, :3])
                else:
                    bgr = np.ascontiguousarray(
                        tmp.reshape(h, row_stride)[:, :row_bytes].reshape(h, w, 4)[:, :, :3]
                    )

                nbytes = bgr.nbytes
                if nbytes + 16 > shm_size:
                    return

                header[0] = h
                header[1] = w
                np.ndarray(nbytes, dtype=np.uint8, buffer=shm.buf, offset=16)[:] = bgr.ravel()
                header[2] += 1          # frame-counter für Reader

            except Exception:
                pass

        @capture.event
        def on_closed():
            header[0] = 0
            header[1] = 0

        threading.Thread(target=capture.start, daemon=True).start()

        while True:
            time.sleep(0.5)

    except Exception:
        pass
    finally:
        try:
            shm.close()
        except Exception:
            pass


def wgc_starten(fenster_titel):
    """Startet den WGC-Subprocess. Wirft Exception wenn nicht möglich."""
    global _wgc_proc, _wgc_shm
    from multiprocessing import shared_memory as shm_mod

    hwnd = memu_fenster_finden()

    try:
        _wgc_shm = shm_mod.SharedMemory(name=_WGC_SHM_NAME, create=True, size=_WGC_SHM_BYTES)
    except FileExistsError:
        _wgc_shm = shm_mod.SharedMemory(name=_WGC_SHM_NAME)

    # Header nullen
    np.ndarray(4, dtype=np.int32, buffer=_wgc_shm.buf)[:] = 0

    _wgc_proc = mp.Process(
        target=_wgc_subprocess,
        args=(_WGC_SHM_NAME, _WGC_SHM_BYTES, hwnd),
        daemon=True,
    )
    _wgc_proc.start()


def fenster_screenshot_wgc() -> np.ndarray | None:
    """Liest den letzten WGC-Frame aus Shared Memory. None wenn kein Frame da."""
    if _wgc_shm is None:
        return None
    header = np.ndarray(4, dtype=np.int32, buffer=_wgc_shm.buf)
    h, w = int(header[0]), int(header[1])
    if h <= 0 or w <= 0:
        return None
    nbytes = h * w * 3
    if nbytes + 16 > _WGC_SHM_BYTES:
        return None
    return np.ndarray((h, w, 3), dtype=np.uint8, buffer=_wgc_shm.buf, offset=16).copy()


def wgc_subprocess_alive() -> bool:
    return _wgc_proc is not None and _wgc_proc.is_alive()


def wgc_stoppen():
    global _wgc_proc, _wgc_shm
    if _wgc_proc and _wgc_proc.is_alive():
        try:
            _wgc_proc.terminate()
            _wgc_proc.join(timeout=1.0)
        except Exception:
            pass
    _wgc_proc = None
    if _wgc_shm:
        try:
            _wgc_shm.close()
            _wgc_shm.unlink()
        except Exception:
            pass
    _wgc_shm = None


# ---------------------------------------------------------------------------
# mss – Fallback
# ---------------------------------------------------------------------------

def fenster_screenshot_mss(hwnd, sct):
    try:
        client_rect = win32gui.GetClientRect(hwnd)
        breite = client_rect[2]
        hoehe  = client_rect[3]
        if breite <= 0 or hoehe <= 0:
            return None, 0, 0
        x, y = win32gui.ClientToScreen(hwnd, (0, 0))
        monitor = {"top": y, "left": x, "width": breite, "height": hoehe}
        screenshot = sct.grab(monitor)
        import cv2
        frame = cv2.cvtColor(
            np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape(hoehe, breite, 4),
            cv2.COLOR_BGRA2BGR,
        )
        return frame, breite, hoehe
    except Exception:
        return None, 0, 0


def fenster_screenshot(hwnd, sct):
    try:
        client_rect = win32gui.GetClientRect(hwnd)
        breite = client_rect[2]
        hoehe  = client_rect[3]
        if breite <= 0 or hoehe <= 0:
            return None
        x, y = win32gui.ClientToScreen(hwnd, (0, 0))
        monitor = {"top": y, "left": x, "width": breite, "height": hoehe}
        screenshot = sct.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    except Exception:
        return None


class SharedFrameBuffer:
    """Verwaltet einen Shared Memory Block für Screenshots."""
    def __init__(self, name: str, size_mb: int = 40, create: bool = False):
        from multiprocessing import shared_memory
        import threading
        self.name = name
        self.size = size_mb * 1024 * 1024
        self.shm  = None
        self._lock = threading.Lock()
        try:
            if create:
                try:
                    self.shm = shared_memory.SharedMemory(name=name, create=True, size=self.size)
                except FileExistsError:
                    self.shm = shared_memory.SharedMemory(name=name)
            else:
                self.shm = shared_memory.SharedMemory(name=name)
        except Exception as e:
            print(f"[SharedMemory] Fehler: {e}")

    def write_frame(self, frame_np: np.ndarray):
        if self.shm is None or frame_np is None:
            return
        if frame_np.nbytes > self.size:
            print(f"[SharedMemory] Frame zu groß: {frame_np.nbytes} > {self.size}")
            return
        with self._lock:
            target = np.ndarray(frame_np.shape, dtype=frame_np.dtype, buffer=self.shm.buf)
            target[:] = frame_np[:]

    def get_frame(self, shape, dtype) -> np.ndarray:
        if self.shm is None:
            return None
        nbytes = int(np.dtype(dtype).itemsize * np.prod(shape))
        if nbytes > self.size:
            return None
        with self._lock:
            view = np.ndarray(shape, dtype=dtype, buffer=self.shm.buf)
            return view.copy()

    def close(self):
        if self.shm:
            self.shm.close()

    def unlink(self):
        if self.shm:
            try: self.shm.unlink()
            except: pass
