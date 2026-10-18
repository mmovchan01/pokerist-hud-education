"""Take a fresh screenshot without capturing our own Tk windows.

Uses Tk timers rather than sleep so the user can cancel during the countdown.
No global hotkeys, injected overlays or game input are used.
"""
import tkinter as tk
from tkinter import messagebox


def fresh_capture(owner, capture, accept):
    root = owner._root()
    if getattr(root, '_capture_busy', False):
        return
    root._capture_busy = True
    windows = [root]+[w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    states = [(w, w.state()) for w in windows if w.winfo_exists()]
    countdown = tk.Toplevel(root)
    countdown.title('Новый снимок')
    countdown.attributes('-topmost', True)
    text = tk.StringVar()
    tk.Label(countdown, textvariable=text, padx=25, pady=20).pack()

    def restore():
        for window, state in states:
            if window.winfo_exists():
                if state == 'normal':
                    window.deiconify()
                elif state == 'iconic':
                    window.iconify()
        root._capture_busy = False

    def cancel():
        if getattr(countdown, 'timer', None):
            root.after_cancel(countdown.timer)
        countdown.destroy()
        restore()

    def take():
        try:
            image = capture()
        except Exception as exc:
            restore()
            messagebox.showerror('Не удалось снять экран', str(exc), parent=owner)
            return
        restore()
        accept(image)

    def tick(seconds):
        if seconds:
            text.set(f'Переключитесь в игру. Снимок через {seconds} с.\nОкна помощника скроются перед захватом.')
            countdown.timer = root.after(1000, lambda: tick(seconds-1))
        else:
            countdown.destroy()
            for window, _ in states:
                if window.winfo_exists():
                    window.withdraw()
            # Allow the compositor to remove windows before MSS reads pixels.
            root.after(350, take)

    tk.Button(countdown, text='Отмена', command=cancel).pack(pady=8)
    countdown.protocol('WM_DELETE_WINDOW', cancel)
    countdown.transient(owner)
    countdown.grab_set()
    tick(3)
