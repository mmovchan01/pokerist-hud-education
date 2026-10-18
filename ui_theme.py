"""Shared light desktop theme; no external fonts, images or network resources."""
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

BG = '#f2f5f9'
SURFACE = '#ffffff'
INK = '#182b3a'
MUTED = '#627586'
GREEN = '#087f68'


def install_theme(root):
    root.configure(background=BG)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10), foreground=INK)
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG)
    style.configure('TCheckbutton', background=BG, padding=3)
    style.configure('TButton', padding=(12, 8), background='#e7edf2', borderwidth=0)
    style.map('TButton', background=[('active', '#d9e5ed')])
    style.configure('Primary.TButton', background=GREEN, foreground='white', font=('Segoe UI', 10, 'bold'))
    style.map('Primary.TButton', background=[('active', '#066b58'), ('disabled', '#a6c5bd')], foreground=[('disabled', '#ffffff')])
    style.configure('Card.TFrame', background=SURFACE)
    style.configure('Card.TLabel', background=SURFACE)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'))
    style.configure('Heading.TLabel', font=('Segoe UI', 12, 'bold'))
    style.configure('TNotebook', background=BG, borderwidth=0)
    style.configure('TNotebook.Tab', padding=(18, 9), background='#e6edf3')
    style.map('TNotebook.Tab', background=[('selected', SURFACE)])
    style.configure('Treeview', rowheight=30, fieldbackground=SURFACE, background=SURFACE, borderwidth=0)
    style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), background='#e6edf3', padding=7)
    style.map('Treeview', background=[('selected', '#d6eee7')], foreground=[('selected', INK)])
    style.configure('TCombobox', padding=5)
    style.configure('Horizontal.TProgressbar', background=GREEN, troughcolor='#e2eaf0')
    return style


def header(parent, title, subtitle):
    frame = tk.Frame(parent, background='#142c39', padx=22, pady=15)
    tk.Label(frame, text='POKER LAB  /  '+title, background='#142c39', foreground='white',
             font=('Segoe UI', 17, 'bold'), anchor='w').pack(fill='x')
    tk.Label(frame, text=subtitle, background='#142c39', foreground='#a9c8cb',
             font=('Segoe UI', 10), anchor='w').pack(fill='x', pady=(5, 0))
    return frame


def open_folder(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'win32':
        os.startfile(str(path))
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])


class ScrollFrame(ttk.Frame):
    """A panel that stays usable when the desktop is only 720 pixels high."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background=BG, highlightthickness=0, width=290, height=120)
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.inner = ttk.Frame(self.canvas, padding=9)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))

    def enable_wheel(self):
        def scroll(event):
            if event.num == 4:
                delta = -1
            elif event.num == 5:
                delta = 1
            else:
                delta = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(delta*2, 'units')
            return 'break'
        def bind(widget):
            widget.bind('<MouseWheel>', scroll, add='+')
            widget.bind('<Button-4>', scroll, add='+')
            widget.bind('<Button-5>', scroll, add='+')
            for child in widget.winfo_children():
                bind(child)
        bind(self.canvas)
