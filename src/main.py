import tkinter as tk
import sys
import os

# Fix for running as "python src/main.py"
sys.path.append(os.getcwd())

from src.ui.launcher import LauncherApp
from src.adapters import mock_adapter, firewatch_adapter, metro_adapter, rdr2_adapter

def main():
    print("=== Game Lens - Launcher Mode ===")
    
    root = tk.Tk()
    app = LauncherApp(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)

if __name__ == "__main__":
    main()
