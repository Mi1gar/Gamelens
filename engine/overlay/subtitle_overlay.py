"""Optimized subtitle overlay — black strip below original, no feedback loop."""
import tkinter as tk
import ctypes


class SubtitleOverlay:
    """Thin black strip + small white text positioned BELOW the original subtitle.

    Matches the proven overlay from live_test_optimized.py exactly.
    """

    def __init__(self, monitor: dict):
        self.mx = monitor["left"]
        self.my = monitor["top"]

        self.root = tk.Tk()
        self.root.withdraw()

        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.config(bg="#0a0a0a")
        self.win.attributes("-alpha", 0.90)

        self.win.update_idletasks()
        try:
            hwnd = (
                ctypes.windll.user32.GetParent(self.win.winfo_id())
                or self.win.winfo_id()
            )
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            ctypes.windll.user32.SetWindowDisplayAffinity(
                hwnd, WDA_EXCLUDEFROMCAPTURE,
            )
            print("  [Overlay] WDA_EXCLUDEFROMCAPTURE OK")
        except Exception as e:
            print(f"  [Overlay] WDA exclude failed: {e}")

        self.win.withdraw()

        self.lbl = tk.Label(
            self.win, text="",
            fg="#EAEAEA", bg="#0a0a0a",
            font=("Corbel", 14),
            justify="center", anchor="center",
        )
        self.lbl.pack(expand=True, fill="both", padx=10, pady=3)

        self._current: str = ""
        self._current_geo: str = ""
        self._hide_timer: str | None = None
        self._next: dict | None = None
        self._update()

    def queue_show(self, text: str, x: int, y: int, w: int, h: int):
        """Show black box below the original subtitle — no feedback loop."""
        clean = text.strip().lower()

        if clean == self._current:
            try:
                cur_x = int(self._current_geo.split("+")[1])
                cur_y = int(self._current_geo.split("+")[2])
                new_x = self.mx + int(x) - 8
                new_y = self.my + int(y) + int(h) + 2
                if abs(cur_x - new_x) < 15 and abs(cur_y - new_y) < 15:
                    self._reset_timer()
                    return
            except (IndexError, ValueError):
                pass

        font_sz = max(11, min(18, int(h * 0.40)))
        font = ("Corbel", font_sz)

        dummy = tk.Label(self.root, text=text, font=font)
        text_w = dummy.winfo_reqwidth()
        dummy.destroy()

        box_w = max(int(w) + 16, text_w + 24)
        box_h = font_sz + 12

        sx = self.mx + int(x) - 8
        sy = self.my + int(y) + int(h) + 2
        geo = f"{box_w}x{box_h}+{sx}+{sy}"

        if clean == self._current and geo == self._current_geo:
            return

        self._next = {"text": text, "geo": geo, "font": font}

    def _update(self):
        if self._next:
            self._current = self._next["text"].strip().lower()
            self._current_geo = self._next["geo"]
            self.lbl.config(text=self._next["text"], font=self._next["font"])
            self.win.geometry(self._next["geo"])
            self.win.deiconify()
            self.win.lift()
            # Force immediate redraw for instant subtitle updates
            self.win.update_idletasks()
            self._next = None
            self._reset_timer()
        self.root.after(16, self._update)

    @property
    def is_visible(self) -> bool:
        return self._current != ""

    def refresh(self):
        self._reset_timer()

    def _reset_timer(self):
        if self._hide_timer:
            self.root.after_cancel(self._hide_timer)
        self._hide_timer = self.root.after(4000, self._hide)

    def _hide(self):
        self.win.withdraw()
        self._current = ""
        self._current_geo = ""

    def run(self):
        self.root.mainloop()

    def stop(self):
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
