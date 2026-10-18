"""F8 → native game-window PNG inbox. Labelling is deferred until later."""
import tkinter as tk
from tkinter import ttk

from global_hotkey import ScreenshotHotkey
from screen import enable_dpi
from screenshot_album import Album
from capture_worker import CaptureWorker


class BatchCapture:
    def __init__(self, args):
        enable_dpi()
        self.args = args
        self.album = Album(args.album, args.templates)
        self.root = tk.Tk()
        self.root.title('Сбор снимков • F8')  # Deliberately does not match Texas Poker.
        self.root.geometry('590x380')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.worker = self.hotkey = None
        self.title = tk.StringVar(value=args.window_title or 'Texas Poker')
        self.key = tk.StringVar(value='F8')
        self.pin = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Откройте Texas Poker, нажмите «Включить сбор», затем играйте и нажимайте F8.')
        self.root.attributes('-topmost', True)
        ttk.Label(self.root, text='Сейчас — снимки. Подписи карт — после игры.', font=('Arial', 14, 'bold')).pack(pady=12)
        ttk.Label(self.root, text='Заголовок приложения Windows:').pack(anchor='w', padx=15)
        self.entry = ttk.Entry(self.root, textvariable=self.title)
        self.entry.pack(fill='x', padx=15)
        self.key_picker = ttk.Combobox(self.root, textvariable=self.key, values=['F8', 'F9', 'F10'], state='readonly', width=8)
        self.key_picker.pack(anchor='w', padx=15, pady=8)
        self.toggle = ttk.Button(self.root, text='Включить сбор', command=self.start)
        self.toggle.pack(fill='x', padx=15)
        ttk.Button(self.root, text='Сделать снимок сейчас', command=self.snapshot).pack(fill='x', padx=15, pady=6)
        ttk.Checkbutton(self.root, text='Поверх всех окон', variable=self.pin,
                        command=lambda: self.root.attributes('-topmost', self.pin.get())).pack(anchor='w', padx=15)
        ttk.Label(self.root, textvariable=self.status, wraplength=550).pack(fill='x', padx=15, pady=10)
        ttk.Label(self.root, text='Можно свернуть это окно: горячая клавиша продолжает работать.\nЗакройте сборщик после сессии и откройте «Редактор накопленных снимков» в панели.', wraplength=550).pack(fill='x', padx=15)
        self.root.after(100, self.poll)

    def start(self):
        if self.worker:
            self.stop()
            return
        title = self.title.get().strip()
        if not title:
            self.status.set('Введите заголовок окна игры.')
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
                self.status.set(f'{self.key.get()} готова. Снимки: {self.args.album}. Окно можно свернуть.')
            while not self.hotkey.errors.empty():
                self.status.set(self.hotkey.errors.get_nowait())
        if self.worker:
            while not self.worker.events.empty():
                kind, value = self.worker.events.get_nowait()
                self.status.set(f'Сохранён PNG: {value[:12]}…' if kind == 'saved' else value)
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
