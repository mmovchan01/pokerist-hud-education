"""A scrollable, keyboard-accessible dropdown with per-item text colours.

Native ttk.Combobox does not support different foregrounds for each entry on
Windows themes. This popup uses an ordinary Tk Listbox, including selection
colours, instead of relying on unsupported combobox internals.
"""
import tkinter as tk
from tkinter import ttk

from ui_theme import PALETTE as P


class ColorChoice(ttk.Frame):
    def __init__(self, parent, textvariable, color, width=20, on_select=None):
        super().__init__(parent)
        self.variable, self.color = textvariable, color
        self.on_select = on_select
        self.values = []
        self.popup = None
        self.button = tk.Button(self, textvariable=textvariable, width=width, anchor='w',
                                background=P['field'], activebackground=P['surface_alt'],
                                relief='solid', borderwidth=1, command=self.open)
        self.button.pack(side='left', fill='x', expand=True)
        self.arrow = ttk.Button(self, text='▾', width=2, command=self.open)
        self.arrow.pack(side='right', fill='y')
        for button in (self.button, self.arrow):
            button.bind('<Down>', self.open)
            button.bind('<Alt-Down>', self.open)
            button.bind('<Return>', self.open)
        self.trace = self.variable.trace_add('write', self.update_color)
        self.bind('<Destroy>', self.cleanup)
        self.update_color()

    def config(self, **kwargs):
        if 'values' in kwargs:
            self.values = list(kwargs.pop('values'))
            self.close()
        if kwargs:
            super().configure(**kwargs)

    configure = config

    def update_color(self, *args):
        color = self.color(self.variable.get())
        self.button.config(foreground=color, activeforeground=color)

    def open(self, event=None):
        if self.popup is not None:
            self.close()
            return 'break'
        if not self.values:
            return 'break'
        popup = self.popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self.winfo_toplevel())
        popup.attributes('-topmost', True)
        box = self.box = tk.Listbox(popup, height=min(12, len(self.values)), width=24,
                                   exportselection=False, background=P['field'],
                                   foreground=P['text'], selectbackground=P['select'],
                                   activestyle='dotbox', font=('Segoe UI', 11))
        scroll = ttk.Scrollbar(popup, orient='vertical', command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        box.pack(side='left', fill='both', expand=True)
        for index, text in enumerate(self.values):
            box.insert('end', text)
            box.itemconfig(index, foreground=self.color(text), selectforeground=self.color(text))
        selected = self.values.index(self.variable.get()) if self.variable.get() in self.values else 0
        box.selection_set(selected)
        box.activate(selected)
        box.see(selected)
        box.bind('<Return>', self.choose)
        box.bind('<Escape>', self.dismiss)
        box.bind('<ButtonRelease-1>', self.choose)
        popup.bind('<Escape>', self.dismiss)
        popup.bind('<ButtonPress-1>', self.outside)
        popup.bind('<FocusOut>', lambda e: self.after_idle(self.dismiss_unfocused))
        popup.update_idletasks()
        width = max(self.winfo_width(), popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        x, y = self.winfo_rootx(), self.winfo_rooty()+self.winfo_height()
        # Windows can place the game/HUD on a secondary monitor. Virtual desktop
        # bounds preserve negative monitor coordinates rather than clipping to 0.
        try:
            if self.tk.call('tk', 'windowingsystem') == 'win32':
                import ctypes
                user = ctypes.windll.user32
                left, top = user.GetSystemMetrics(76), user.GetSystemMetrics(77)
                right = left+user.GetSystemMetrics(78)
                bottom = top+user.GetSystemMetrics(79)
            else:
                left, top = 0, 0
                right, bottom = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(left, min(x, right-width))
            if y+height > bottom:
                y = max(top, self.winfo_rooty()-height)
        except tk.TclError:
            y = self.winfo_rooty()-height
        popup.geometry(f'{width}x{height}{x:+d}{y:+d}')
        popup.deiconify()
        popup.update_idletasks()
        popup.grab_set()
        box.focus_set()
        return 'break'

    def choose(self, event=None):
        if self.popup is not None:
            selected = self.box.curselection()
            if selected:
                self.variable.set(self.values[selected[0]])
                if self.on_select:
                    self.on_select()
            self.close()
            self.focus_set()
        # Selecting with Enter must NOT also save/advance the editor.
        return 'break'

    def outside(self, event):
        if self.popup and not (self.popup.winfo_rootx() <= event.x_root < self.popup.winfo_rootx()+self.popup.winfo_width()
                               and self.popup.winfo_rooty() <= event.y_root < self.popup.winfo_rooty()+self.popup.winfo_height()):
            self.close()
            return 'break'

    def dismiss_unfocused(self):
        if self.popup is not None:
            focused = self.focus_get()
            if focused is None or focused.winfo_toplevel() is not self.popup:
                self.close()

    def dismiss(self, event=None):
        self.close()
        return 'break'

    def close(self):
        if self.popup is not None:
            popup, self.popup = self.popup, None
            popup.grab_release()
            popup.destroy()

    def cleanup(self, event):
        if event.widget is self:
            self.close()
            self.variable.trace_remove('write', self.trace)
