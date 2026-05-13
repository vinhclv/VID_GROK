# main.py
import tkinter as tk
from ui.app_window import BatchApp

if __name__ == "__main__":
    root = tk.Tk()
    app = BatchApp(root)
    root.mainloop()