"""Splash screen with logo, progress bar, and ETA.

Shown during app startup while models/runtime download.
Auto-closes when startup is complete.
"""
import sys
import tkinter as tk
import time
import os


def _get_bundle_path(relative_path: str) -> str:
    """Get path to bundled file (works in dev and PyInstaller EXE)."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        for _ in range(3):
            base = os.path.dirname(base)
    return os.path.join(base, relative_path)


class SplashScreen:
    """Tkinter splash screen for app startup."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # no title bar
        self.root.attributes("-topmost", True)

        # Window size
        self.W = 500
        self.H = 320

        # Center on screen
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws - self.W) // 2
        y = (hs - self.H) // 2
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        # Dark background
        self.root.configure(bg="#0d0d0d")

        # ── Logo ──
        self._logo_img = None
        self._logo_label = None
        logo_paths = [
            _get_bundle_path("icons/logo/gamelens_logo.png"),
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "icons", "logo", "gamelens_logo.png"),
        ]
        for lp in logo_paths:
            if os.path.exists(lp):
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(lp)
                    # Resize to fit (max 180x180)
                    img.thumbnail((180, 180), Image.LANCZOS)
                    self._logo_img = ImageTk.PhotoImage(img)
                    self._logo_label = tk.Label(
                        self.root, image=self._logo_img,
                        bg="#0d0d0d",
                    )
                    self._logo_label.pack(pady=(30, 0))
                    break
                except Exception:
                    pass

        if self._logo_label is None:
            # Text fallback
            tk.Label(
                self.root,
                text="GameLens",
                font=("Segoe UI", 28, "bold"),
                fg="#EAEAEA",
                bg="#0d0d0d",
            ).pack(pady=(40, 0))

        # ── Status text ──
        self._status_var = tk.StringVar(value="Baslatiliyor...")
        tk.Label(
            self.root,
            textvariable=self._status_var,
            font=("Segoe UI", 11),
            fg="#AAAAAA",
            bg="#0d0d0d",
            wraplength=420,
        ).pack(pady=(20, 10))

        # ── Progress bar ──
        self._progress_var = tk.DoubleVar(value=0)
        self._progress_canvas = tk.Canvas(
            self.root, width=400, height=8,
            bg="#1a1a1a", highlightthickness=0,
        )
        self._progress_canvas.pack(pady=(0, 5))
        self._progress_bar = self._progress_canvas.create_rectangle(
            0, 0, 0, 8, fill="#6C5CE7", outline="",
        )

        # ── ETA / stats text ──
        self._eta_var = tk.StringVar(value="")
        tk.Label(
            self.root,
            textvariable=self._eta_var,
            font=("Segoe UI", 9),
            fg="#777777",
            bg="#0d0d0d",
        ).pack()

        # ── Version ──
        try:
            import json
            vp = os.path.join(os.path.dirname(__file__), "..", "..",
                              "version.json")
            with open(vp) as f:
                v = json.load(f)
            ver_str = f"v{v['version']}"
        except Exception:
            ver_str = "v0.1.0"

        tk.Label(
            self.root,
            text=ver_str,
            font=("Segoe UI", 9),
            fg="#444444",
            bg="#0d0d0d",
        ).pack(side="bottom", pady=10)

        self._start_time = time.time()
        self._total_bytes = 0
        self._downloaded = 0
        self._closed = False
        self.root.update()

    # ── Public API ──

    def set_status(self, text: str):
        """Update the status message."""
        self._status_var.set(text)
        self._update()

    def set_progress(self, pct: float, done_mb: float = 0,
                     total_mb: float = 0):
        """Update progress bar 0-100."""
        self._progress_var.set(pct)
        w = int(400 * pct / 100)
        self._progress_canvas.coords(self._progress_bar, 0, 0, w, 8)

        if total_mb > 0:
            elapsed = time.time() - self._start_time
            if done_mb > 0:
                speed = done_mb / max(elapsed, 0.1)
                remaining_mb = total_mb - done_mb
                eta_s = remaining_mb / max(speed, 0.1)
                eta_str = f"{int(eta_s // 60)}d {int(eta_s % 60)}sn"
                self._eta_var.set(
                    f"{done_mb:.0f} / {total_mb:.0f} MB  •  "
                    f"{speed:.1f} MB/s  •  Kalan: {eta_str}"
                )
            else:
                self._eta_var.set(f"0 / {total_mb:.0f} MB")
        self._update()

    def close(self):
        """Close splash screen."""
        if not self._closed:
            self._closed = True
            try:
                self.root.destroy()
            except Exception:
                pass

    def _update(self):
        """Process Tkinter events."""
        try:
            if not self._closed:
                self.root.update()
        except Exception:
            pass


# ── Global singleton ──

_splash: SplashScreen | None = None


def show_splash() -> SplashScreen:
    """Show splash screen. Returns SplashScreen instance for updates."""
    global _splash
    if _splash is None:
        _splash = SplashScreen()
    return _splash


def close_splash():
    """Close splash screen if open."""
    global _splash
    if _splash is not None:
        _splash.close()
        _splash = None


def update_splash(status: str = "",
                  pct: float = -1,
                  done_mb: float = 0,
                  total_mb: float = 0):
    """Update splash screen from anywhere."""
    if _splash is not None:
        if status:
            _splash.set_status(status)
        if pct >= 0:
            _splash.set_progress(pct, done_mb, total_mb)
