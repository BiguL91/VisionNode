import tkinter as tk
import time

class LogPanel:
    def __init__(self, parent):
        self.parent = parent
        self._setup_ui()

    def _setup_ui(self):
        self.log_text = tk.Text(self.parent, bg="#1a1a1a", fg="#888888", 
                                font=("Consolas", 8), relief=tk.FLAT, 
                                state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        tk.Scrollbar(self.parent, command=self.log_text.yview, bg="#2d2d2d").pack(side=tk.RIGHT, fill=tk.Y)

    def log(self, message):
        ts = time.strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{ts}  {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
