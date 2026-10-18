"""A small, observable collection panel: shortcut health and latest-frame preview."""
import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk

from global_hotkey import ScreenshotHotkey
from screen import enable_dpi
from screenshot_album import Album
from capture_worker import CaptureWorker
from ui_theme import install_theme, header, open_folder


class BatchCapture:
    def __init__(self, args):
        enable_dpi()
        self.args = args
        self.album = Album(args.album, args.templates)
        self.root = tk.Tk()
        self.root.title('Poker Lab · Сбор снимков')
        self.root.geometry(f'620x{min(690, self.root.winfo_screenheight()-70)}')
        install_theme(self.root)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.worker = self.hotkey = None
        self.title = tk.StringVar(value=args.window_title or 'Texas Poker')
        self.key = tk.StringVar(value='F8')
        self.pin = tk.BooleanVar(value=True)
        self.key_status = tk.StringVar(value='Сбор выключен')
        self.counter = tk.StringVar(value='Сохранено за сессию: 0')
        self.count = 0
        self.status = tk.StringVar(value='Нажмите «Включить сбор». Затем переключитесь в игру и нажимайте F8.')
        self.root.attributes('-topmost', True)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        header(self.root, 'Сбор снимков', 'Играйте сейчас. Подпишете карты после сессии.').grid(row=0, column=0, sticky='ew')
        controls = ttk.Frame(self.root, padding=(20, 12))
        controls.grid(row=1, column=0, sticky='ew')
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, text='Окно приложения Windows', style='Heading.TLabel').grid(row=0, column=0, columnspan=3, sticky='w')
        self.entry = ttk.Entry(controls, textvariable=self.title)
        self.entry.grid(row=1, column=0, sticky='ew', pady=8)
        self.key_picker = ttk.Combobox(controls, textvariable=self.key, values=['F8', 'F9', 'F10'], state='readonly', width=6)
        self.key_picker.grid(row=1, column=1, padx=8)
        self.toggle = ttk.Button(controls, text='Включить сбор', command=self.start, style='Primary.TButton')
        self.toggle.grid(row=1, column=2)
        ttk.Label(controls, textvariable=self.key_status, foreground='#087f68').grid(row=2, column=0, columnspan=3, sticky='w')
        ttk.Button(controls, text='Сделать один снимок сейчас', command=self.snapshot).grid(row=3, column=0, columnspan=3, sticky='ew', pady=10)
        ttk.Checkbutton(controls, text='Закрепить поверх окон', variable=self.pin, command=lambda: self.root.attributes('-topmost', self.pin.get())).grid(row=4, column=0, sticky='w')
        preview = ttk.Frame(self.root, style='Card.TFrame', padding=14)
        preview.grid(row=2, column=0, sticky='nsew', padx=20)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)
        ttk.Label(preview, text='Последний сохранённый кадр', style='Card.TLabel', font=('Segoe UI', 11, 'bold')).grid(row=0, column=0, sticky='w')
        self.preview = ttk.Label(preview, text='Пока нет снимков\n\nПервый кадр появится здесь — проверьте,\nчто видна игра, а не чёрный экран.', anchor='center', style='Card.TLabel')
        self.preview.grid(row=1, column=0, sticky='nsew', pady=8)
        foot = ttk.Frame(self.root, padding=(20, 10))
        foot.grid(row=3, column=0, sticky='ew')
        ttk.Label(foot, textvariable=self.counter, style='Heading.TLabel').pack(anchor='w')
        ttk.Label(foot, textvariable=self.status, wraplength=570).pack(anchor='w', pady=8)
        ttk.Button(foot, text='Открыть папку сохранённых снимков', command=self.folder).pack(fill='x')
        ttk.Label(foot, text='Можно свернуть это окно. После сессии закройте его\nи откройте «Разобрать и подписать карты» в главной панели.', style='Muted.TLabel').pack(anchor='w', pady=6)
        self.root.after(100, self.poll)

    def start(self):
        if self.worker:
            self.stop()
            return
        title = self.title.get().strip()
        if not title:
            self.status.set('Укажите заголовок окна игры, например Texas Poker.')
            return
        self.worker = CaptureWorker(self.album, self.args.config, title)
        self.hotkey = ScreenshotHotkey(self.worker.request, self.key.get())
        self.hotkey.start()
        self.entry.configure(state='disabled')
        self.key_picker.configure(state='disabled')
        self.toggle.configure(text='Остановить')
        self.key_status.set(f'Регистрирую {self.key.get()}…')
        self.status.set('Кнопка снимка работает независимо от регистрации горячей клавиши.')

    def snapshot(self):
        if not self.worker:
            self.start()
        if self.worker:
            self.worker.request()

    def poll(self):
        if self.hotkey:
            if self.hotkey.ready.is_set():
                self.key_status.set(f'{self.key.get()} работает · окно можно свернуть' if self.hotkey.registered else f'{self.key.get()} не активна · используйте кнопку или выберите другую клавишу')
            while not self.hotkey.errors.empty():
                self.status.set(self.hotkey.errors.get_nowait())
        if self.worker:
            while not self.worker.events.empty():
                kind, value = self.worker.events.get_nowait()
                if kind == 'saved':
                    self.count += 1
                    self.counter.set(f'Сохранено за сессию: {self.count}')
                    self.status.set('PNG сохранён. Если кадр правильный, продолжайте игру и нажимайте '+self.key.get()+'.')
                    try:
                        image = self.album.image(self.album.load(value))
                        h, w = image.shape[:2]
                        scale = min(540/w, 150/h)
                        self.preview.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).resize((max(1, round(w*scale)), max(1, round(h*scale)))))
                        self.preview.configure(image=self.preview.photo, text='')
                    except (OSError, ValueError) as exc:
                        self.status.set('Файл сохранён, но предпросмотр недоступен: '+str(exc))
                else:
                    self.status.set(value)
        self.root.after(100, self.poll)

    def stop(self):
        if self.hotkey:
            self.hotkey.close()
        if self.worker:
            self.worker.close()
        self.hotkey = self.worker = None
        self.entry.configure(state='normal')
        self.key_picker.configure(state='readonly')
        self.toggle.configure(text='Включить сбор')
        self.key_status.set('Сбор выключен · клавиша освобождена')

    def folder(self):
        try:
            open_folder(self.album.folder)
        except OSError as exc:
            self.status.set(str(exc))

    def close(self):
        self.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
