"""F8 → native game-window PNG inbox. Labelling is deferred until later."""
import tkinter as tk
from tkinter import ttk

from capture_worker import CaptureWorker
from global_hotkey import ScreenshotHotkey
from screen import enable_dpi
from screenshot_album import Album
from ui_theme import PALETTE as P, apply_theme, card, font


class BatchCapture:
    def __init__(self, args):
        enable_dpi()
        self.args = args
        self.album = Album(args.album, args.templates)
        self.root = tk.Tk()
        apply_theme(self.root)
        self.root.title('Сбор снимков • F8')  # Deliberately does not match Texas Poker.
        self.root.geometry('620x520')
        self.root.minsize(560, 480)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.worker = self.hotkey = None
        self.title = tk.StringVar(value=args.window_title or 'Texas Poker')
        self.key = tk.StringVar(value='F8')
        self.pin = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Откройте Texas Poker, нажмите «Включить сбор», затем играйте и нажимайте F8.')
        self.root.attributes('-topmost', True)

        tk.Label(self.root, text='Сбор снимков F8', bg=P['bg'], fg=P['accent'], font=font(18, 'bold')).pack(anchor='w', padx=22, pady=(20, 0))
        tk.Label(self.root, text='Снимки окна игры копятся в альбом. Подписи карт делаются позже, в редакторе.',
                 bg=P['bg'], fg=P['muted'], font=font(10), wraplength=560, justify='left').pack(anchor='w', padx=22, pady=(2, 12))

        panel = card(self.root, padding=(18, 14))
        panel.pack(fill='x', padx=22)
        tk.Label(panel, text='Заголовок окна игры (Windows)', bg=P['surface'], fg=P['text'], font=font(10, 'bold')).pack(anchor='w')
        self.entry = ttk.Entry(panel, textvariable=self.title)
        self.entry.pack(fill='x', pady=(6, 12))
        row = tk.Frame(panel, bg=P['surface'])
        row.pack(fill='x')
        tk.Label(row, text='Горячая клавиша:', bg=P['surface'], fg=P['text'], font=font(10, 'bold')).pack(side='left')
        self.key_picker = ttk.Combobox(row, textvariable=self.key, values=['F8', 'F9', 'F10'], state='readonly', width=6)
        self.key_picker.pack(side='left', padx=10)
        ttk.Checkbutton(row, text='Поверх всех окон', variable=self.pin, style='Card.TCheckbutton',
                        command=lambda: self.root.attributes('-topmost', self.pin.get())).pack(side='right')

        buttons = tk.Frame(self.root, bg=P['bg'])
        buttons.pack(fill='x', padx=22, pady=14)
        self.toggle = ttk.Button(buttons, text='Включить сбор', style='Accent.TButton', command=self.start)
        self.toggle.pack(fill='x')
        ttk.Button(buttons, text='Сделать снимок сейчас', command=self.snapshot).pack(fill='x', pady=(8, 0))

        status = tk.Frame(self.root, bg=P['surface_alt'])
        status.pack(fill='x', padx=22)
        tk.Label(status, textvariable=self.status, bg=P['surface_alt'], fg=P['text'], font=font(10),
                 wraplength=540, justify='left', anchor='w', padx=12, pady=10).pack(fill='x')
        tk.Label(self.root, text='Окно можно свернуть: горячая клавиша продолжает работать.\n'
                                 'После сессии закройте сборщик и откройте «Редактор накопленных снимков» в панели.',
                 bg=P['bg'], fg=P['muted'], font=font(9), wraplength=560, justify='left').pack(anchor='w', padx=22, pady=12)
        self.root.after(100, self.poll)

    def start(self):
        if self.worker:
            self.stop()
            return
        title = self.title.get().strip()
        if not title:
            self.status.set('Введите заголовок окна игры — например, Texas Poker.')
            return
        self.worker = CaptureWorker(self.album, self.args.config, title)
        self.hotkey = ScreenshotHotkey(self.worker.request, self.key.get())
        self.hotkey.start()
        self.entry.config(state='disabled')
        self.key_picker.config(state='disabled')
        self.toggle.config(text='Остановить сбор')
        self.status.set(f'Регистрация {self.key.get()}… Кнопка снимка также доступна.')

    def snapshot(self):
        if not self.worker:
            self.start()
        if self.worker:
            self.worker.request()

    def poll(self):
        if self.hotkey:
            if self.hotkey.ready.is_set() and not getattr(self.hotkey, 'announced', False):
                self.hotkey.announced = True
                self.status.set(f'{self.key.get()} готова. Снимки сохраняются в: {self.args.album}. Окно можно свернуть.')
            while not self.hotkey.errors.empty():
                self.status.set(self.hotkey.errors.get_nowait())
        if self.worker:
            while not self.worker.events.empty():
                kind, value = self.worker.events.get_nowait()
                self.status.set(f'✓ Снимок сохранён ({value[:8]}…). Продолжайте играть.' if kind == 'saved' else value)
        self.root.after(100, self.poll)

    def stop(self):
        if self.hotkey:
            self.hotkey.close()
        if self.worker:
            self.worker.close()
        self.hotkey = self.worker = None
        self.entry.config(state='normal')
        self.key_picker.config(state='readonly')
        self.toggle.config(text='Включить сбор')
        self.status.set('Сбор остановлен, глобальная клавиша освобождена.')

    def close(self):
        self.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
