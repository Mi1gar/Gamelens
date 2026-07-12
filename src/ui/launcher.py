import tkinter as tk
from tkinter import ttk, messagebox
import threading
import mss
from ..core.registry import GameRegistry
from ..core.engine import engine


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Game Lens - Game Selector")
        self.root.geometry("520x480")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.theme_use('clam')

        # Header
        ttk.Label(root, text="Game Lens", font=("Segoe UI", 18, "bold")).pack(side='top', pady=(15, 0))
        ttk.Label(root, text="Real-time Game Subtitle Translator",
                  font=("Segoe UI", 9), foreground="gray").pack(side='top')

        # Monitor selection
        monitor_frame = ttk.LabelFrame(root, text="Monitor Selection", padding=5)
        monitor_frame.pack(side='top', fill='x', padx=20, pady=(10, 5))

        self.monitors = self._detect_monitors()
        self.monitor_var = tk.StringVar()

        ttk.Label(monitor_frame, text="Capture from:").pack(side='left', padx=5)
        self.monitor_combo = ttk.Combobox(monitor_frame, textvariable=self.monitor_var,
                                          state="readonly", width=35)
        self.monitor_combo.pack(side='left', padx=5, fill='x', expand=True)

        monitor_names = [m["name"] for m in self.monitors]
        self.monitor_combo['values'] = monitor_names
        if monitor_names:
            self.monitor_combo.current(0)

        # Game list
        ttk.Label(root, text="Select Game Profile",
                  font=("Segoe UI", 11, "bold")).pack(side='top', pady=(10, 0))

        self.tree = ttk.Treeview(root, columns=("name",), show='headings',
                                 selectmode='browse', height=6)
        self.tree.heading("name", text="Game")
        self.tree.column("name", width=480)
        self.tree.pack(fill='both', padx=20, pady=5)
        self.tree.bind('<<TreeviewSelect>>', self.on_game_select)

        # Status bar
        self.lbl_status = ttk.Label(root, text="Ready — Select a game and click START",
                                    foreground="gray")
        self.lbl_status.pack(side='bottom', fill='x', pady=5, padx=20)

        # Buttons
        self.btn_frame = ttk.Frame(root)
        self.btn_frame.pack(side='bottom', fill='x', pady=10, padx=20)

        self.btn_start = ttk.Button(self.btn_frame, text="START ENGINE",
                                    command=self.start_engine)
        self.btn_start.pack(side='left', expand=True, fill='x', padx=5)

        self.btn_stop = ttk.Button(self.btn_frame, text="STOP",
                                   command=self.stop_engine, state='disabled')
        self.btn_stop.pack(side='left', expand=True, fill='x', padx=5)

        self.selected_game_id = None
        self.refresh_games()

        engine.on_status_change_callback = self.update_status_ui

    def _detect_monitors(self):
        monitors = []
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors):
                if i == 0:
                    continue  # skip "all monitors" virtual
                monitors.append({
                    "index": i,
                    "name": f"Monitor {i}: {m['width']}x{m['height']} "
                            f"at ({m['left']},{m['top']})",
                    "region": (m['left'], m['top'], m['width'], m['height'])
                })
        return monitors

    def get_selected_monitor(self):
        idx = self.monitor_combo.current()
        if idx >= 0 and idx < len(self.monitors):
            return self.monitors[idx]["region"]
        return (0, 0, 1920, 1080)

    def refresh_games(self):
        self.tree.delete(*self.tree.get_children())
        games = GameRegistry.get_all_games()
        for g in games:
            self.tree.insert('', 'end', values=(g['name'],), tags=(g['id'],))

    def on_game_select(self, event):
        item = self.tree.selection()
        if not item:
            return
        tags = self.tree.item(item)['tags']
        if tags:
            self.selected_game_id = tags[0]
            self.lbl_status.config(text=f"Selected: {self.tree.item(item)['values'][0]}")

    def start_engine(self):
        if not self.selected_game_id:
            messagebox.showwarning("No Game", "Please select a game first.")
            return

        monitor = self.get_selected_monitor()
        print(f"[Launcher] Monitor: {monitor}")
        print(f"[Launcher] Game: {self.selected_game_id}")

        engine.select_game(self.selected_game_id)

        # Apply monitor region to adapter
        engine.hook_manager.set_active_adapter(engine.hook_manager.active_adapter)

        engine.start()
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.lbl_status.config(text="Running... Press STOP to finish.")

    def stop_engine(self):
        engine.stop()
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.lbl_status.config(text="Stopped. Dataset saved to ./dataset/")

    def update_status_ui(self, status):
        if status == "running":
            self.btn_start.config(state='disabled')
            self.btn_stop.config(state='normal')
        else:
            self.btn_start.config(state='normal')
            self.btn_stop.config(state='disabled')


def main():
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
