"""Mouse-only ROI setup and fast, labelled training sample collection."""
import re
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

import cv2
import mss
from PIL import Image, ImageTk

from screen import Rect, enable_dpi, grab, load_config, window_rect
from setup_support import selection_bounds, preview_scale
from config_io import save_config
from capture_ui import fresh_capture

ROI_NAMES = ['hero1', 'hero2', *[f'board{i}' for i in range(1, 6)],
             'pot', 'stack', 'call', *[f'opp{i}' for i in range(1, 9)],
             *[f'oppstack{i}' for i in range(1, 9)]]


def roi_hint(name):
    if name.startswith('hero'):
        return 'Ваша карта: выделите всю карту плотно, не захватывая соседнюю.'
    if name.startswith('board'):
        return 'Позиция карты борда: выделите слот даже если он сейчас пустой.'
    if name.startswith('oppstack'):
        return 'Необязательно: числовая строка стека соответствующего соперника.'
    if name.startswith('opp'):
        return 'Только рубашка карт соперника; аватар и имя не включайте. Неиспользуемое место пропустите.'
    return {'pot': 'Банк: только число с суффиксом, без подписи и значка фишек.',
            'stack': 'Ваш стек: только числовая строка.',
            'call': 'Сумма колла: только число, без слова Call. Check не является шаблоном цифры 0.'}.get(name, '')


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
    def __init__(self, parent, image, template_dir, rois=None, capture=None):
        super().__init__(parent)
        self.title('Шаблоны: выделите карту целиком / один символ / рубашку')
        self.image, self.template_dir = image.copy(), template_dir
        self.rois = rois or {}
        self.capture = capture
        self.kind = tk.StringVar(value='card')
        self.label = tk.StringVar()
        self.status = tk.StringVar(value='Пустые края карт обрезайте одинаково; цифры выделяйте по одному символу.')
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        kind_picker = ttk.Combobox(bar, textvariable=self.kind, values=['card', 'glyph', 'back', 'empty'], width=8, state='readonly')
        kind_picker.pack(side='left')
        kind_picker.bind('<<ComboboxSelected>>', lambda e: self.suggest_label())
        self.roi_name = tk.StringVar()
        roi_picker = ttk.Combobox(bar, textvariable=self.roi_name, values=list(self.rois), width=12, state='readonly')
        roi_picker.pack(side='left')
        roi_picker.bind('<<ComboboxSelected>>', lambda e: self.select_roi())
        self.entry = ttk.Entry(bar, textvariable=self.label, width=14)
        self.entry.pack(side='left')
        ttk.Button(bar, text='Сохранить (Enter)', command=self.save).pack(side='left')
        if capture:
            ttk.Button(bar, text='Новый кадр (3 с)', command=self.refresh).pack(side='left')
        ttk.Button(bar, text='Следующая зона', command=self.next_roi).pack(side='left')
        ttk.Label(self, textvariable=self.status, wraplength=1050).pack()
        self.scale = preview_scale(image.shape[1], image.shape[0], self.winfo_screenwidth(), self.winfo_screenheight())
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
        if self.rois:
            self.roi_name.set(next(iter(self.rois)))
            self.select_roi()

    def suggest_label(self):
        self.label.set({'empty': 'empty', 'back': 'back'}.get(self.kind.get(), ''))

    def next_roi(self):
        names = list(self.rois)
        if names:
            index = names.index(self.roi_name.get()) if self.roi_name.get() in names else -1
            self.roi_name.set(names[(index+1) % len(names)])
            self.select_roi()

    def refresh(self):
        if self.capture:
            fresh_capture(self, self.capture, self.set_image)

    def set_image(self, image):
        self.image = image.copy()
        self.scale = preview_scale(image.shape[1], image.shape[0], self.winfo_screenwidth(), self.winfo_screenheight())
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb).resize((round(image.shape[1]*self.scale), round(image.shape[0]*self.scale))))
        self.canvas.config(width=self.photo.width(), height=self.photo.height())
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.start = self.box = None
        self.select_roi()
        self.status.set('Новый кадр получен. Выберите зону и подпишите образец.')

    def select_roi(self):
        values = self.rois.get(self.roi_name.get())
        if values:
            x, y, w, h = Rect(*values).pixels(self.photo.width(), self.photo.height())
            self.canvas.delete('selection')
            self.box = self.canvas.create_rectangle(x, y, x+w, y+h, outline='#00ff88', width=2, tags='selection')
            name = self.roi_name.get()
            self.kind.set('glyph' if name in ('pot', 'stack', 'call') or name.startswith('oppstack') else ('back' if name.startswith('opp') else 'card'))
            self.suggest_label()
            self.status.set(roi_hint(name) + ' Для цифр сузьте выделение до одного символа, сохранив высоту строки.')
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
        x1, y1, x2, y2 = selection_bounds(self.canvas.coords(self.box), self.scale, self.image.shape[1], self.image.shape[0])
        try:
            path = save_template(self.template_dir, self.kind.get(), self.label.get().strip(), self.image[y1:y2, x1:x2])
            self.status.set(f'Сохранено: {path.name}. Следующий образец → выделение → метка → Enter')
            self.suggest_label()
        except ValueError as exc:
            messagebox.showerror('Шаблон', str(exc), parent=self)


class CalibrationApp:
    def __init__(self, config_path, template_dir, collect=False, window_title=''):
        enable_dpi()
        self.path, self.template_dir = Path(config_path), template_dir
        self.root = tk.Tk()
        self.root.title('Калибровка Pokerist')
        self.root.withdraw()
        self.window_title = window_title
        self.base_config = {}
        if collect:
            try:
                config = load_config(self.path)
                with mss.mss() as sct:
                    image = grab(sct, config)
                dialog = Collector(self.root, image, template_dir, config['rois'], capture=lambda: self.capture_config(config))
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
        self.image = self.desktop
        self.capture = None
        self.rois = {}
        self.stage = 'client'
        try:
            if self.path.exists():
                self.base_config = load_config(self.path)
                self.rois = self.base_config['rois'].copy()
                self.capture = self.base_config['capture'].copy()
                self.window_title = window_title or self.base_config.get('window_title', '')
            actual = window_rect(self.window_title)
            if actual:
                self.capture = actual
            if self.capture:
                config = dict(capture=self.capture, window_title=self.window_title)
                self.image = self.capture_config(config)
                self.stage = 'rois'
        except Exception as exc:
            messagebox.showerror('Окно / конфигурация', str(exc), parent=self.root)
            self.root.destroy()
            raise
        self.status = tk.StringVar(value='1. Выделите клиентскую область игры (без рамок и HUD).')
        ttk.Label(self.root, textvariable=self.status, wraplength=1100).pack()
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill='x')
        self.name = tk.StringVar(value='hero1')
        ttk.Combobox(toolbar, textvariable=self.name, values=ROI_NAMES, state='readonly').pack(side='left')
        self.name.trace_add('write', lambda *args: self.update_hint())
        ttk.Button(toolbar, text='Новый кадр (3 с)', command=self.refresh).pack(side='left')
        ttk.Button(toolbar, text='Выбрать область заново', command=self.reselect_client).pack(side='left')
        ttk.Button(toolbar, text='Сохранить config', command=self.save).pack(side='left')
        ttk.Button(toolbar, text='Собрать шаблоны', command=self.collect_templates).pack(side='left')
        ttk.Label(self.root, text='Карты: вся карта; opp: только рубашка; oppstack: необязательно', wraplength=1100).pack()
        self.canvas = tk.Canvas(self.root)
        self.canvas.pack()
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.up)
        self.start = self.box = None
        self.render()
        self.update_hint()
        self.root.deiconify()

    def update_hint(self):
        if self.stage == 'client':
            self.status.set('1. Выделите клиентскую область игры. Для точного выбора окна в Windows задайте его заголовок в панели запуска.')
        else:
            missing = set(ROI_NAMES[:10])-self.rois.keys()
            self.status.set(f'Зон: {len(self.rois)}, обязательных осталось: {len(missing)}. Сейчас {self.name.get()}: {roi_hint(self.name.get())}')

    @staticmethod
    def capture_config(config):
        with mss.mss() as sct:
            return grab(sct, config)

    def capture_current(self):
        return self.capture_config(dict(capture=self.capture, window_title=self.window_title))

    def collect_templates(self):
        if self.capture is None:
            messagebox.showinfo('Сначала область игры', 'Выделите клиентскую область игры.', parent=self.root)
            return
        fresh_capture(self.root, self.capture_current, lambda image: Collector(self.root, image, self.template_dir, self.rois, capture=self.capture_current))

    def reselect_client(self):
        if self.rois and not messagebox.askyesno('Новая область', 'Текущие выделения будут убраны из редактора. Файл на диске не изменится до сохранения. Продолжить?', parent=self.root):
            return
        def capture():
            import numpy as np
            with mss.mss() as sct:
                self.monitor = dict(sct.monitors[0])
                return np.asarray(sct.grab(self.monitor))[:, :, :3].copy()
        def accept(image):
            self.desktop = self.image = image
            self.capture = None
            self.rois = {}
            self.window_title = ''
            self.stage = 'client'
            self.name.set('hero1')
            self.start = self.box = None
            self.render()
            self.update_hint()
        fresh_capture(self.root, capture, accept)

    def refresh(self):
        def capture():
            if self.stage == 'rois':
                actual = window_rect(self.window_title)
                if actual:
                    self.capture = actual
                return self.capture_current()
            import numpy as np
            with mss.mss() as sct:
                self.monitor = dict(sct.monitors[0])
                return np.asarray(sct.grab(self.monitor))[:, :, :3].copy()

        def accept(image):
            self.image = image
            if self.stage == 'client':
                self.desktop = image
            self.start = self.box = None
            self.render()
            self.update_hint()
        fresh_capture(self.root, capture, accept)

    def render(self):
        self.scale = preview_scale(self.image.shape[1], self.image.shape[0], self.root.winfo_screenwidth(), self.root.winfo_screenheight())
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
        self.update_hint()
        self.render()

    def save(self):
        required = ROI_NAMES[:10]
        missing = set(required)-self.rois.keys()
        if missing or self.capture is None:
            messagebox.showerror('Не все зоны', ', '.join(sorted(missing)))
            return
        title = simpledialog.askstring('Привязка окна', 'Windows: уникальная часть заголовка игры для слежения.\nLinux/macOS: оставьте пустым (фиксированная область).', parent=self.root, initialvalue=self.window_title)
        if title is None:
            return
        if title:
            try:
                actual = window_rect(title)
                if actual and any(abs(actual[k]-self.capture[k]) > 8 for k in actual):
                    messagebox.showerror('Границы не совпадают', 'Выделенная область должна совпадать с клиентской областью указанного окна. Повторите калибровку.')
                    return
            except RuntimeError as exc:
                messagebox.showerror('Окно', str(exc))
                return
        data = dict(self.base_config)
        data.update(version=1, capture=self.capture, window_title=title, rois=self.rois)
        data.setdefault('confidence', .84)
        data.setdefault('margin', .04)
        data.setdefault('interval', .275)
        try:
            save_config(self.path, data)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Не удалось сохранить', str(exc), parent=self.root)
            return
        self.window_title = title
        self.base_config = data
        self.status.set(f'Сохранено {self.path}. Теперь соберите шаблоны: карты, цифры, рубашка.')

    def run(self):
        self.root.mainloop()
