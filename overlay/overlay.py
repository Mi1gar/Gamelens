import tkinter as tk
import threading
import time
from ctypes import windll, c_uint

class SubtitleWindow:
    """A single subtitle box window with professional styling"""
    def __init__(self, master):
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.wm_attributes("-topmost", True)
        
        # Theme Colors (Cinema Style)
        self.bg_color = "#000000" # Pure Black
        self.border_color = "#000000" 
        self.text_color = "#FFFFFF"
        self.font_style = ("Arial", 14, "bold")
        
        # Transparency Key (Pink) - used for the corners outside the rounded rect
        self.transparent_key = "#ff00ff"
        self.window.config(bg=self.transparent_key)
        self.window.wm_attributes("-transparentcolor", self.transparent_key)
        
        # Dimensions
        self.padding = 5
        self.radius = 5
        
        # Canvas for drawing
        self.canvas = tk.Canvas(
            self.window, 
            bg=self.transparent_key, 
            highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)
        
        # Element IDs
        self.rect_id = None
        self.text_id = None
        
        # Hide initially
        self.window.withdraw()
        
        # Apply Window Exclusion & Click-Through
        self._apply_exclusion()
        self._make_click_through()
    
    def _make_click_through(self):
        try:
            hwnd = windll.user32.GetParent(self.window.winfo_id())
            if not hwnd:
                hwnd = self.window.winfo_id()
            
            # WS_EX_LAYERED = 0x80000
            # WS_EX_TRANSPARENT = 0x20
            styles = windll.user32.GetWindowLongW(hwnd, -20)
            new_styles = styles | 0x80000 | 0x20
            if styles != new_styles:
                windll.user32.SetWindowLongW(hwnd, -20, new_styles)
                pass
        except Exception as e:
            print(f"[AR] Click-through Error: {e}")
    
    def _apply_exclusion(self):
        try:
            # Try to get the root window handle (Parent of the Tkinter frame)
            hwnd = windll.user32.GetParent(self.window.winfo_id())
            if not hwnd:
                hwnd = self.window.winfo_id()
                
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            
            # Apply to both just in case (Parent is usually the correct one for Toplevel)
            result = windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            
            if result == 0:
                # If 0, it failed. Try the child?
                err = windll.kernel32.GetLastError()
                print(f"[Overlay] Exclusion Failed on HWND {hwnd}: Error {err}")
            else:
                pass 
                # print(f"[Overlay] Exclusion Success on HWND {hwnd}")

        except Exception as e:
            print(f"[Overlay] Exclusion Critical Error: {e}")

    def round_rectangle(self, x1, y1, x2, y2, radius=25, **kwargs):
        points = [x1+radius, y1,
                  x1+radius, y1,
                  x2-radius, y1,
                  x2-radius, y1,
                  x2, y1,
                  x2, y1+radius,
                  x2, y1+radius,
                  x2, y2-radius,
                  x2, y2-radius,
                  x2, y2,
                  x2-radius, y2,
                  x2-radius, y2,
                  x1+radius, y2,
                  x1+radius, y2,
                  x1, y2,
                  x1, y2-radius,
                  x1, y2-radius,
                  x1, y1+radius,
                  x1, y1+radius,
                  x1, y1]
        return self.canvas.create_polygon(points, **kwargs, smooth=True)

    def show(self, text, x, y, w, h):
        self.canvas.delete("all")
        
        # Calculate size needed
        pad = self.padding
        
        # Draw Rounded Rect
        self.round_rectangle(
            0, 0, w, h, 
            radius=self.radius, 
            fill=self.bg_color, 
            outline=self.border_color,
            width=2
        )
        
        # Draw Text
        # Center text in box
        self.canvas.create_text(
            w/2, h/2,
            text=text,
            fill=self.text_color,
            font=self.font_style,
            width=w - (pad*2), # Wrap width
            justify='center'
        )
        
        # Position exactly at x,y with w,h
        self.window.geometry(f"{w}x{h}+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        
        # Re-apply click-through
        self._make_click_through()
        self._apply_exclusion()
        
    def hide(self):
        self.window.withdraw()

class SubtitleOverlay:
    def __init__(self, master=None):
        if master:
            self.root = master
            self.is_own_root = False
        else:
            self.root = tk.Tk()
            self.root.title("Game Lens AR Overlay")
            self.root.withdraw()
            self.is_own_root = True

        self.windows = [] # Pool of SubtitleWindow
        self._queue = []
        self._clear_timer = None
        
        self._check_queue() 

    def update_layout_from_event(self, event):
        """
        Adapter to handle SubtitleEvent directly.
        """
        if event.keep_alive:
            self.refresh()
            return
            
        layout_data = []
        if event.layout:
            layout_data = event.layout
        else:
            # Basic fallback - Cinema Strip
            # Lower position (Y=920), Less Height (80px) -> Tweaked to 60px height
            layout_data = [{'text': event.text, 'box': [360, 940, 1200, 60]}]
            
        self.update_layout(layout_data)

    def update_layout(self, layout_data: list):
        """
        layout_data = [{'text': '...', 'box': [x,y,w,h]}, ...]
        """
        self._queue.append(layout_data)

    def _check_queue(self):
        if self._queue:
            layout = self._queue.pop(-1) 
            self._queue.clear()
            self._draw_layout(layout)
            
            if self._clear_timer:
                self.root.after_cancel(self._clear_timer)
            self._clear_timer = self.root.after(3000, self._clear_screen)
        
        self.root.after(20, self._check_queue)

    def _clear_screen(self):
        for win in self.windows:
            win.hide()
    
    def refresh(self):
        if self._clear_timer:
            self.root.after_cancel(self._clear_timer)
        self._clear_timer = self.root.after(3000, self._clear_screen)

    def _draw_layout(self, layout):
        # Ensure enough windows
        while len(self.windows) < len(layout):
            self.windows.append(SubtitleWindow(self.root))
            
        # Update active windows
        for i, item in enumerate(layout):
            text = item['text']
            x, y, w, h = item['box']
            x, y, w, h = int(x), int(y), int(w), int(h)
            
            self.windows[i].show(text, x, y, w, h)
            
        # Hide unused windows
        for i in range(len(layout), len(self.windows)):
            self.windows[i].hide()

    def run(self):
        self.root.mainloop()

# Globals
overlay = None
