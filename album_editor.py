"""Offline screenshot labelling. Choose cards from a list, save and continue."""
import queue
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
from PIL import Image, ImageTk

from screen import Rect, enable_dpi
from screenshot_album import Album, read_image
from setup_support import selection_bounds, preview_scale
from profile_support import load_profile

from card_choices import MISSING_ONLY_DEFAULT, choice_color, display_choice, resolve_choice, filtered_choices
from color_choice import ColorChoice
from editor_assistant import EditorAssistant, identical_sample_exists
from ui_theme import PALETTE as P, apply_theme, font


class AlbumEditor:
    def __init__(self, args):
        enable_dpi()
        self.album = Album(args.album, args.templates)
        self.root = tk.Tk()
        apply_theme(self.root)
        self.root.title('Редактор накопленных снимков — подпись шаблонов')
        self.root.geometry(f'{min(1180, self.root.winfo_screenwidth()-40)}x{min(850, self.root.winfo_screenheight()-80)}')
        self.record = self.image = self.item_id = self.pending_rect = None
        self.start = self.box = None
        self.records = []
        self.known_cards = set()
        self.analysis_token = 0
        self.last_auto = None
        self.closed = False
        self.assistant = EditorAssistant(args.templates)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='label-assistant')
        self.analysis_future = None
        self.analysis_results = queue.Queue()
        self.status = tk.StringVar(value='Шаг 1: выберите снимок слева. Шаг 2: выделите область мышью или выберите её в списке. Шаг 3: укажите карту и нажмите Enter.')
        self.kind = tk.StringVar(value='card')
        self.label = tk.StringVar()
        self.only_pending = tk.BooleanVar(value=False)
        self.cards_only = tk.BooleanVar(value=True)
        self.pin = tk.BooleanVar(value=False)
        self.auto_known = tk.BooleanVar(value=True)
        self.missing_only = tk.BooleanVar(value=MISSING_ONLY_DEFAULT)
        self.add_variants = tk.BooleanVar(value=False)
        self.coverage = tk.StringVar(value='База карт: проверка…')
        bar = ttk.Frame(self.root)
        bar.pack(fill='x', padx=8, pady=5)
        ttk.Button(bar, text='Обновить список', command=self.refresh).pack(side='left')
        ttk.Button(bar, text='Импорт PNG/JPEG…', command=self.import_files).pack(side='left', padx=5)
        ttk.Checkbutton(bar, text='Только карты', variable=self.cards_only, command=self.refresh).pack(side='left')
        ttk.Checkbutton(bar, text='Только незавершённые снимки', variable=self.only_pending, command=self.refresh).pack(side='left')
        ttk.Checkbutton(bar, text='Поверх всех окон', variable=self.pin,
                        command=lambda: self.root.attributes('-topmost', self.pin.get())).pack(side='right')
        assist = ttk.Frame(self.root)
        assist.pack(fill='x', padx=8, pady=3)
        ttk.Checkbutton(assist, text='Распознавать и пропускать известные', variable=self.auto_known, command=self.toggle_assistant).pack(side='left')
        ttk.Checkbutton(assist, text='Скрыть уже известные карты', variable=self.missing_only, command=self.refresh_choices).pack(side='left')
        ttk.Button(assist, text='Проверить последнюю авто', command=self.review_last).pack(side='left', padx=5)
        ttk.Label(assist, textvariable=self.coverage).pack(side='right')
        panes = ttk.Panedwindow(self.root, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=8)
        left = ttk.Frame(panes, width=230)
        right = ttk.Frame(panes)
        panes.add(left, weight=0)
        panes.add(right, weight=1)
        ttk.Label(left, text='Снимки: подписано / всего').pack()
        self.frames = tk.Listbox(left, width=29, exportselection=False)
        self.frames.pack(side='left', fill='both', expand=True)
        self.frames.bind('<<ListboxSelect>>', self.select_frame)
        scrollbar = ttk.Scrollbar(left, orient='vertical', command=self.frames.yview)
        scrollbar.pack(side='right', fill='y')
        self.frames.config(yscrollcommand=scrollbar.set)
        self.canvas = tk.Canvas(right, background=P['field'], height=420, highlightthickness=0)
        self.canvas.pack(fill='x')
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.up)
        line = ttk.Frame(right)
        line.pack(fill='x', pady=5)
        ttk.Label(line, text='Область:').pack(side='left')
        self.item_name = tk.StringVar()
        self.items = ttk.Combobox(line, textvariable=self.item_name, state='readonly', width=18)
        self.items.pack(side='left', padx=5)
        self.items.bind('<<ComboboxSelected>>', self.change_item)
        ttk.Button(line, text='Добавить выделение', command=self.add_region).pack(side='left')
        ttk.Label(right, text='Можно поправить рамку мышью. Для цифр: выделите один символ, сохранив высоту строки.', wraplength=850).pack(anchor='w')
        legend = tk.Frame(right, bg=P['bg'])
        legend.pack(anchor='w', pady=(2, 0))
        tk.Label(legend, text='Цвет рамки:', bg=P['bg'], fg=P['muted'], font=font(9)).pack(side='left')
        for color, text in ((P['warn'], 'ждёт подписи'), (P['good'], 'подписана'), (P['info'], 'взята из базы'), (P['muted'], 'пропущена')):
            tk.Label(legend, text='■ ', bg=P['bg'], fg=color, font=font(11)).pack(side='left')
            tk.Label(legend, text=text + '   ', bg=P['bg'], fg=P['muted'], font=font(9)).pack(side='left')
        controls = ttk.Frame(right)
        controls.pack(fill='x', pady=6)
        self.kind_picker = ttk.Combobox(controls, textvariable=self.kind, values=['card', 'empty', 'back', 'glyph'], state='readonly', width=9)
        self.kind_picker.pack(side='left')
        self.kind_picker.bind('<<ComboboxSelected>>', lambda e: self.set_choices())
        self.label_picker = ColorChoice(controls, textvariable=self.label, color=choice_color, width=20)
        self.label_picker.pack(side='left', padx=6)
        ttk.Button(controls, text='Сохранить → дальше (Enter)', style='Accent.TButton', command=self.save_next).pack(side='left')
        ttk.Button(controls, text='Нечитаемо / пропустить', command=self.skip).pack(side='left', padx=5)
        ttk.Checkbutton(right, text='Добавлять новые образцы уже известных карт (другое освещение / перекрытие)', variable=self.add_variants, command=self.toggle_assistant).pack(anchor='w')
        self.preview = ttk.Label(right)
        self.preview.pack(anchor='w', pady=4)
        ttk.Label(right, textvariable=self.status, wraplength=850, justify='left').pack(fill='x', pady=5)
        self.root.bind('<Return>', self.enter)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.label.trace_add('write', self.cancel_analysis)
        self.refresh()
        self.root.after(100, self.poll_analysis)

    def cancel_analysis(self, *args):
        self.analysis_token += 1
        if self.analysis_future is not None:
            self.analysis_future.cancel()

    def refresh_choices(self):
        kind, label = resolve_choice(self.kind.get(), self.label.get())
        self.set_choices(label)

    def toggle_assistant(self):
        self.cancel_analysis()
        if self.record and self.item_id and self.pending_rect is None:
            self.request_analysis()

    def request_analysis(self):
        self.cancel_analysis()
        if not self.record or not self.item_id:
            return
        item = self.record['items'][self.item_id]
        if item['kind'] not in ('card', 'empty') or self.kind.get() not in ('card', 'empty'):
            return
        token = self.analysis_token
        identifier, name, revision = self.record['id'], self.item_id, self.record['revision']
        crop = Rect(*(self.pending_rect or item['rect'])).crop(self.image).copy()
        future = self.analysis_future = self.executor.submit(self.assistant.analyze, crop)
        def done(future):
            if not future.cancelled():
                try:
                    suggestion, known = future.result()
                    self.analysis_results.put((token, identifier, name, revision, suggestion, known, None))
                except Exception as exc:
                    self.analysis_results.put((token, identifier, name, revision, None, set(), str(exc)))
        future.add_done_callback(done)

    def poll_analysis(self):
        if self.closed:
            return
        while not self.analysis_results.empty():
            token, identifier, name, revision, suggestion, known, error = self.analysis_results.get_nowait()
            if token != self.analysis_token or not self.record or (identifier, name, revision) != (self.record['id'], self.item_id, self.record['revision']):
                continue
            if error:
                self.status.set('Автораспознавание недоступно: '+error)
                continue
            self.known_cards = known
            self.coverage.set(f'В базе: {len(known)}/52')
            if self.record['items'][name]['status'] != 'pending':
                self.refresh_choices()
                item = self.record['items'][name]
                self.status.set(f'{name}: {item["status"]}, {display_choice(item.get("label")) or item.get("label") or "без метки"}. Можно исправить вручную. Автоподпись не создаёт шаблонов.')
            elif suggestion and suggestion.automatic and self.auto_known.get() and not self.add_variants.get() and self.pending_rect is None:
                try:
                    self.record = self.album.accept_known(identifier, name, suggestion.kind, suggestion.label, suggestion.confidence, suggestion.method, revision)
                    self.last_auto = identifier, name
                    # No template is exported from an automatic decision.
                    self.advance()
                except (OSError, ValueError, KeyError) as exc:
                    self.status.set(str(exc))
            elif suggestion and self.auto_known.get():
                self.set_choices(suggestion.label)
                self.status.set(f'Предположение: {display_choice(suggestion.label)}, похожесть {suggestion.confidence:.0%}. Проверьте и нажмите Enter (образец сохранится в базу), либо исправьте.')
            else:
                self.refresh_choices()
                self.status.set(('Карта не распознана — выберите вручную. ' if self.auto_known.get() else 'Автопропуск выключен — выберите вручную. ')+'Чтобы выбрать знакомую карту, снимите «Скрыть уже известные карты».')
        self.root.after(100, self.poll_analysis)

    def review_last(self):
        if not self.last_auto or not self.dirty_ok():
            return
        self.auto_known.set(False)
        self.cancel_analysis()
        identifier, name = self.last_auto
        self.open_record(identifier)
        self.choose_item(name)
        self.status.set('Проверка автоподписи. Автопропуск выключен: можно исправить метку или выбрать другую область.')

    def enter(self, event=None):
        # Avoid binding a second save to the button's own activation.
        if event is None or not isinstance(event.widget, ttk.Button):
            self.save_next()
        return 'break'

    def eligible(self, record):
        return [name for name, item in record['items'].items() if not self.cards_only.get() or name.startswith(('hero', 'board')) or item['kind'] == 'card']

    def change_item(self, event=None):
        name = self.item_name.get()
        if self.dirty_ok():
            self.choose_item(name)
        else:
            self.item_name.set(self.item_id)

    def dirty_ok(self):
        return self.pending_rect is None or messagebox.askyesno('Несохранённая рамка', 'Перейти без сохранения изменённой рамки?', parent=self.root)

    def refresh(self):
        if not self.dirty_ok():
            return
        self.cancel_analysis()
        old_id = self.record['id'] if self.record else None
        records, errors = self.album.records()
        self.records = [r for r in records if not self.only_pending.get() or any(r['items'][n]['status'] == 'pending' for n in self.eligible(r))]
        self.frames.delete(0, 'end')
        for record in self.records:
            done = sum(record['items'][n]['status'] != 'pending' for n in self.eligible(record))
            self.frames.insert('end', f'{record["created_at"][11:19]}  {record["id"][:6]}  {done}/{len(self.eligible(record))}')
        self.pending_rect = None
        if self.records:
            index = next((i for i, r in enumerate(self.records) if r['id'] == old_id), 0)
            self.frames.selection_set(index)
            self.open_record(self.records[index]['id'])
        else:
            self.record = self.image = self.item_id = None
            self.canvas.delete('all')
            self.items.config(values=[])
            self.item_name.set('')
            self.preview.config(image='')
            self.status.set('Снимков пока нет. Соберите их через F8 или импортируйте файлы.')
        if errors:
            self.status.set('Некоторые файлы пропущены: '+'; '.join(errors[:3]))

    def select_frame(self, event=None):
        indices = self.frames.curselection()
        if indices and self.dirty_ok():
            self.open_record(self.records[indices[0]]['id'])

    def open_record(self, identifier):
        try:
            self.record = self.album.load(identifier)
            self.image = self.album.image(self.record)
            self.pending_rect = None
            self.items.config(values=self.eligible(self.record))
            pending = next((n for n in self.eligible(self.record) if self.record['items'][n]['status'] == 'pending'), next(iter(self.eligible(self.record)), None))
            self.render()
            if pending:
                self.choose_item(pending)
        except (OSError, ValueError, KeyError) as exc:
            self.status.set(str(exc))

    def render(self):
        if self.image is None:
            return
        h, w = self.image.shape[:2]
        self.scale = min(preview_scale(w, h, self.root.winfo_screenwidth()-260, self.root.winfo_screenheight()), max(300, self.root.winfo_screenwidth()-330)/w, max(160, min(380, self.root.winfo_screenheight()-540))/h)
        self.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)).resize((round(w*self.scale), round(h*self.scale))))
        self.canvas.config(width=self.photo.width(), height=self.photo.height())
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        for name, item in self.record['items'].items():
            x, y, cw, ch = Rect(*item['rect']).pixels(self.photo.width(), self.photo.height())
            color = {'exported': P['good'], 'reused': P['info'], 'skipped': P['muted']}.get(item['status'], P['warn'])
            self.canvas.create_rectangle(x, y, x+cw, y+ch, outline=color)
            self.canvas.create_text(x, y, text=name, anchor='sw', fill=color)

    def choose_item(self, name):
        if not self.record or name not in self.record['items']:
            return
        self.item_id = name
        self.item_name.set(name)
        self.pending_rect = None
        item = self.record['items'][name]
        # Reopen an empty card slot in the card list, with 'Пусто' selected.
        self.kind.set('card' if item['kind'] == 'empty' and name.startswith(('hero', 'board')) else item['kind'])
        self.set_choices(item.get('label'))
        self.render()
        x, y, w, h = Rect(*item['rect']).pixels(self.photo.width(), self.photo.height())
        self.box = self.canvas.create_rectangle(x, y, x+w, y+h, outline=P['text'], width=2, tags='selection')
        self.show_crop(item['rect'])
        self.status.set(f'{name}: {item["status"]}. '+('Зоны предложены автоматически — проверьте рамки! ' if self.record.get('suggested_rois') else '')+'Выберите метку и нажмите Enter. Пустой слот: пункт «Пусто» в списке карт; анимация/перекрытие: пропустить.')
        self.request_analysis()

    def set_choices(self, stored=None):
        kind = self.kind.get()
        values = filtered_choices(self.known_cards, self.missing_only.get(), stored) if kind == 'card' else (['empty'] if kind == 'empty' else (['back'] if kind == 'back' else list('0123456789.,KMB')))
        self.label_picker.config(values=values)
        if kind == 'card':
            display = display_choice(stored)
        else:
            display = stored if stored in values else (values[0] if kind in ('empty', 'back') else '')
        self.label.set(display)

    def show_crop(self, rect):
        crop = Rect(*rect).crop(self.image)
        if not crop.size:
            return
        h, w = crop.shape[:2]
        scale = min(5, 450/w, 90/h)
        self.crop_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).resize((max(1, round(w*scale)), max(1, round(h*scale)))))
        self.preview.config(image=self.crop_photo)

    def down(self, event):
        if self.image is None:
            return
        self.cancel_analysis()
        self.start = event.x, event.y
        self.canvas.delete('selection')
        self.box = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=P['text'], width=2, tags='selection')

    def drag(self, event):
        if self.start:
            self.canvas.coords(self.box, *self.start, event.x, event.y)

    def up(self, event):
        if not self.start:
            return
        x1, y1, x2, y2 = selection_bounds((*self.start, event.x, event.y), self.scale, self.image.shape[1], self.image.shape[0])
        self.start = None
        if min(x2-x1, y2-y1) < 2:
            return
        self.pending_rect = [x1/self.image.shape[1], y1/self.image.shape[0], (x2-x1)/self.image.shape[1], (y2-y1)/self.image.shape[0]]
        self.show_crop(self.pending_rect)

    def add_region(self):
        if not self.record or self.pending_rect is None:
            self.status.set('Сначала выделите дополнительный символ/область мышью на снимке.')
            return
        try:
            self.record, name = self.album.add_region(self.record['id'], self.pending_rect)
            self.items.config(values=self.eligible(self.record))
            self.choose_item(name)
        except (OSError, ValueError) as exc:
            self.status.set(str(exc))

    def apply(self, skip=False):
        """Save the human decision. A manual choice always stores its crop unless the exact same pixels exist.

        Earlier versions dropped a second photo of an already known card (status 'reused', no file),
        so the user could not add more samples. Only an automatic match skips writing now.
        """
        if not self.record or not self.item_id:
            return
        kind, label = resolve_choice(self.kind.get(), self.label.get())
        self.cancel_analysis()
        note = ''
        try:
            item = self.record['items'][self.item_id]
            rect = self.pending_rect
            crop = Rect(*(rect or item['rect'])).crop(self.image) if self.image is not None else None
            if (not skip and kind == 'card' and item['status'] == 'pending'
                    and identical_sample_exists(self.album.templates, kind, label, crop)):
                self.record = self.album.accept_known(self.record['id'], self.item_id, kind, label, 1., 'human confirmed existing',
                                                      self.record['revision'], automatic=False, rect=rect)
                note = 'Точно такой же образец уже есть в базе — файл не дублируется.'
            else:
                self.record = self.album.annotate(self.record['id'], self.item_id, kind, label,
                                                  rect=rect, skip=skip, revision=self.record['revision'])
                if not skip and kind == 'card':
                    note = f'Образец карты {label} сохранён в базу.'
            self.pending_rect = None
            self.advance()
            if note:
                self.status.set(note)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('Не удалось сохранить', str(exc), parent=self.root)

    def save_next(self):
        self.apply()

    def skip(self):
        self.apply(skip=True)

    def advance(self):
        pending = next((n for n in self.eligible(self.record) if self.record['items'][n]['status'] == 'pending'), None)
        if pending:
            self.choose_item(pending)
        else:
            # Recompute progress; optionally removes completed frames from view.
            records, _ = self.album.records()
            following = next((r for r in records if r['id'] != self.record['id'] and any(r['items'][n]['status'] == 'pending' for n in self.eligible(r))), None)
            self.refresh()
            if following:
                index = next((i for i, r in enumerate(self.records) if r['id'] == following['id']), None)
                if index is not None:
                    self.frames.selection_clear(0, 'end')
                    self.frames.selection_set(index)
                    self.open_record(following['id'])
            else:
                self.status.set('Все области разобраны. Шаблоны сохранены; можно закрыть редактор и перезапустить HUD.')

    def import_files(self):
        paths = filedialog.askopenfilenames(parent=self.root, filetypes=[('Снимки', '*.png *.jpg *.jpeg')])
        errors = []
        for path in paths:
            try:
                self.album.add(read_image(path), load_profile()['rois'], {'method': 'file import'}, suggested=True)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        self.refresh()
        if errors:
            messagebox.showerror('Ошибки импорта', '\n'.join(errors[:5]), parent=self.root)

    def close(self):
        if self.dirty_ok():
            self.closed = True
            self.cancel_analysis()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.root.destroy()

    def run(self):
        self.root.mainloop()
