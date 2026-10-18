"""Mouse-only ROI setup and fast, labelled training sample collection."""
import json
import re
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

import cv2
import mss
from PIL import Image, ImageTk

from screen import Rect, enable_dpi, grab, load_config, window_rect

ROI_NAMES = ['hero1', 'hero2', *[f'board{i}' for i in range(1, 6)],
             'pot', 'stack', 'call', *[f'opp{i}' for i in range(1, 9)],
             *[f'oppstack{i}' for i in range(1, 9)]]


def save_template(root, kind, label, image):
    valid = ((kind == 'card' and re.fullmatch(r'[2-9TJQKA][cdhs]', label)) or
             (kind == 'glyph' and label in '0123456789.,KMB' and len(label) == 1) or
             (kind == 'back' and label == 'back') or
             (kind == 'empty' and label == 'empty'))
    if not valid:
        raise ValueError('Карта: Ah, Td; цифра/символ: 0–9 . , K M B; рубашка: back; пустой слот: empty')
    folder = Path(root) / kind / label
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{time.time_ns()}.png'
    if not image.size or not cv2.imwrite(str(path), image):
        raise ValueError('Не удалось сохранить изображение')
    return path


class Collector(tk.Toplevel):
    """Select any crop, type a label, press Enter. No filesystem editing."""
    def __init__(self, parent, image, template_dir, rois=None):
        super().__init__(parent)
        self.title('Шаблоны: выделите карту целиком / один символ / рубашку')
        self.image, self.template_dir = image.copy(), template_dir
        self.rois = rois or {}
        self.kind = tk.StringVar(value='card')
        self.label = tk.StringVar()
        self.status = tk.StringVar(value='Пустые края карт обрезайте одинаково; цифры выделяйте по одному символу.')
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        ttk.Combobox(bar, textvariable=self.kind, values=['card', 'glyph', 'back', 'empty'], width=8, state='readonly').pack(side='left')
        self.roi_name = tk.StringVar()
        roi_picker = ttk.Combobox(bar, textvariable=self.roi_name, values=list(self.rois), width=12, state='readonly')
        roi_picker.pack(side='left')
        roi_picker.bind('<<ComboboxSelected>>', lambda e: self.select_roi())
        self.entry = ttk.Entry(bar, textvariable=self.label, width=14)
        self.entry.pack(side='left')
        ttk.Button(bar, text='Сохранить (Enter)', command=self.save).pack(side='left')
        ttk.Label(self, textvariable=self.status).pack()
        self.scale = min(1, 1200/image.shape[1], 720/image.shape[0])
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb).resize((round(image.shape[1]*self.scale), round(image.shape[0]*self.scale))))
        self.canvas = tk.Canvas(self, width=self.photo.width(), height=self.photo.height())
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', lambda e: self.entry.focus_set())
        self.bind('<Return>', lambda e: self.save())
        self.start = self.box = None

    def select_roi(self):
        values = self.rois.get(self.roi_name.get())
        if values:
            x, y, w, h = Rect(*values).pixels(self.photo.width(), self.photo.height())
            self.canvas.delete('selection')
            self.box = self.canvas.create_rectangle(x, y, x+w, y+h, outline='#00ff88', width=2, tags='selection')
            self.entry.focus_set()

    def down(self, event):
        self.start = (event.x, event.y)
        self.canvas.delete('selection')
        self.box = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='#00ff88', width=2, tags='selection')

    def drag(self, event):
        if self.start:
            self.canvas.coords(self.box, *self.start, event.x, event.y)

    def save(self):
        if self.box is None:
            return
        x1, y1, x2, y2 = self.canvas.coords(self.box)
        x1, x2 = sorted((max(0, round(x1/self.scale)), min(self.image.shape[1], round(x2/self.scale))))
        y1, y2 = sorted((max(0, round(y1/self.scale)), min(self.image.shape[0], round(y2/self.scale))))
        try:
            path = save_template(self.template_dir, self.kind.get(), self.label.get().strip(), self.image[y1:y2, x1:x2])
            self.status.set(f'Сохранено: {path.name}. Следующий образец → выделение → метка → Enter')
            self.label.set('')
        except ValueError as exc:
            messagebox.showerror('Шаблон', str(exc), parent=self)


class CalibrationApp:
    def __init__(self, config_path, template_dir, collect=False):
        enable_dpi()
        self.path, self.template_dir = Path(config_path), template_dir
        self.root = tk.Tk()
        self.root.title('Калибровка Pokerist')
        self.root.withdraw()
        if collect:
            try:
                config = load_config(self.path)
                with mss.mss() as sct:
                    image = grab(sct, config)
                dialog = Collector(self.root, image, template_dir, config['rois'])
                dialog.protocol('WM_DELETE_WINDOW', self.root.destroy)
            except Exception:
                self.root.destroy()
                raise
            return
        # Hide the app before taking the frozen desktop screenshot.
        with mss.mss() as sct:
            self.monitor = dict(sct.monitors[0])
            import numpy as np
            self.desktop = np.asarray(sct.grab(self.monitor))[:, :, :3].copy()
        self.root.deiconify()
        self.image = self.desktop
        self.capture = None
        self.rois = {}
        self.stage = 'client'
        self.status = tk.StringVar(value='1. Выделите клиентскую область игры (без рамок и HUD).')
        ttk.Label(self.root, textvariable=self.status, wraplength=1100).pack()
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill='x')
        self.name = tk.StringVar(value='hero1')
        ttk.Combobox(toolbar, textvariable=self.name, values=ROI_NAMES, state='readonly').pack(side='left')
        ttk.Button(toolbar, text='Сохранить config', command=self.save).pack(side='left')
        ttk.Button(toolbar, text='Собрать шаблоны', command=lambda: Collector(self.root, self.image, self.template_dir, self.rois)).pack(side='left')
        ttk.Label(toolbar, text='Карты: вся карта; opp: только рубашка; oppstack: необязательно').pack(side='left')
        self.canvas = tk.Canvas(self.root)
        self.canvas.pack()
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.up)
        self.start = self.box = None
        self.render()

    def render(self):
        self.scale = min(1, 1200/self.image.shape[1], 720/self.image.shape[0])
        self.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)).resize((round(self.image.shape[1]*self.scale), round(self.image.shape[0]*self.scale))))
        self.canvas.config(width=self.photo.width(), height=self.photo.height())
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        for name, values in self.rois.items():
            x, y, w, h = Rect(*values).pixels(self.photo.width(), self.photo.height())
            self.canvas.create_rectangle(x, y, x+w, y+h, outline='#00ee88')
            self.canvas.create_text(x, y, text=name, anchor='nw', fill='#ff5500')

    def down(self, e):
        self.start = e.x, e.y
        self.box = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline='red', width=2)

    def drag(self, e):
        if self.start:
            self.canvas.coords(self.box, *self.start, e.x, e.y)

    def up(self, e):
        if not self.start:
            return
        a, b = self.start
        x, y = max(0, min(a, e.x)), max(0, min(b, e.y))
        w, h = min(self.photo.width(), max(a, e.x))-x, min(self.photo.height(), max(b, e.y))-y
        if min(w, h) < 4:
            return
        values = [x/self.photo.width(), y/self.photo.height(), w/self.photo.width(), h/self.photo.height()]
        if self.stage == 'client':
            px, py, pw, ph = Rect(*values).pixels(self.desktop.shape[1], self.desktop.shape[0])
            self.capture = dict(left=self.monitor['left']+px, top=self.monitor['top']+py, width=pw, height=ph)
            self.image = self.desktop[py:py+ph, px:px+pw].copy()
            self.stage = 'rois'
        else:
            self.rois[self.name.get()] = values
            index = ROI_NAMES.index(self.name.get())
            self.name.set(ROI_NAMES[min(index+1, len(ROI_NAMES)-1)])
        self.start = None
        self.status.set(f'Зон: {len(self.rois)}. Выделите {self.name.get()}; необязательные места можно пропустить.')
        self.render()

    def save(self):
        required = ROI_NAMES[:10]
        missing = set(required)-self.rois.keys()
        if missing or self.capture is None:
            messagebox.showerror('Не все зоны', ', '.join(sorted(missing)))
            return
        title = simpledialog.askstring('Привязка окна', 'Windows: уникальная часть заголовка игры для слежения.\nLinux/macOS: оставьте пустым (фиксированная область).', parent=self.root) or ''
        if title:
            try:
                actual = window_rect(title)
                if actual and any(abs(actual[k]-self.capture[k]) > 8 for k in actual):
                    messagebox.showerror('Границы не совпадают', 'Выделенная область должна совпадать с клиентской областью указанного окна. Повторите калибровку.')
                    return
            except RuntimeError as exc:
                messagebox.showerror('Окно', str(exc))
                return
        data = dict(version=1, capture=self.capture, window_title=title, rois=self.rois,
                    confidence=0.84, margin=0.04, interval=0.275)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        self.status.set(f'Сохранено {self.path}. Теперь соберите шаблоны: карты, цифры, рубашка.')

    def run(self):
        self.root.mainloop()
