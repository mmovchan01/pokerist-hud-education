"""Guided desktop review workspace with observable, local template recognition."""
import queue
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
from PIL import Image, ImageTk

from card_choices import choice_color, display_choice, filtered_choices, resolve_choice
from color_choice import ColorChoice
from editor_assistant import EditorAssistant, has_card_template
from profile_support import load_profile, seed_templates
from review_helpers import KIND_LABELS, STATUS_LABELS, eligible_items, progress, region_title, template_inventory
from review_state import ReviewState
from screen import Rect, enable_dpi
from screenshot_album import Album, read_image
from setup_support import selection_bounds
from ui_theme import install_theme, header, open_folder, ScrollFrame, INK, MUTED, SURFACE


class AlbumEditor:
    def __init__(self, args):
        enable_dpi()
        self.args = args
        self.album = Album(args.album, args.templates)
        self.root = tk.Tk()
        self.root.title('Poker Lab · Разбор снимков')
        self.root.geometry(f'{min(1320, self.root.winfo_screenwidth()-40)}x{min(900, self.root.winfo_screenheight()-80)}')
        self.root.minsize(980, 600)
        install_theme(self.root)
        self.record = self.image = self.item_id = self.pending_rect = None
        self.records = []
        self.known_cards = set()
        self.review = ReviewState()
        self.assistant = EditorAssistant(args.templates)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='review')
        self.future = None
        self.results = queue.Queue()
        self.closed = False
        self.last_auto = None
        self.filter_snapshot = (True, False)
        self.start = None
        self.cards_only = tk.BooleanVar(value=True)
        self.pending_only = tk.BooleanVar(value=False)
        self.auto_skip = tk.BooleanVar(value=False)
        self.missing_only = tk.BooleanVar(value=False)
        self.variant = tk.BooleanVar(value=False)
        self.pin = tk.BooleanVar(value=False)
        self.label = tk.StringVar()
        self.kind = tk.StringVar(value='Карта')
        self.item_name = tk.StringVar()
        self.status = tk.StringVar(value='Импортируйте снимки или выберите кадр слева.')
        self.coverage = tk.StringVar(value='База шаблонов')
        self.scene_title = tk.StringVar(value='Выберите снимок')
        self.advice_title = tk.StringVar(value='Жду карту')
        self.advice_detail = tk.StringVar(value='Здесь появится результат сравнения с вашими шаблонами.')
        self.advice_meta = tk.StringVar(value='Локальное распознавание · без облака')
        self.progress_text = tk.StringVar(value='0 / 0')
        self._build()
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.bind('<Return>', self.enter)
        self.root.bind('<Control-r>', lambda e: self.request_analysis())
        self.root.after(50, self.refresh)
        self.root.after(100, self.poll)

    def _build(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        header(self.root, 'Разбор снимков', '1  Соберите кадры с F8     →     2  Подпишите карты     →     3  Проверьте HUD').grid(row=0, column=0, sticky='ew')
        tabs = self.tabs = ttk.Notebook(self.root)
        tabs.grid(row=1, column=0, sticky='nsew', padx=12, pady=10)
        workspace, library, help_tab = ttk.Frame(tabs), ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(workspace, text='Разобрать снимки')
        tabs.add(library, text='База карт')
        tabs.add(help_tab, text='Как работает распознавание')
        workspace.rowconfigure(1, weight=1)
        workspace.columnconfigure(1, weight=1)
        toolbar = ttk.Frame(workspace)
        toolbar.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(8, 10))
        ttk.Button(toolbar, text='+ Импорт снимков', command=self.import_files).pack(side='left')
        ttk.Button(toolbar, text='Обновить', command=self.refresh).pack(side='left', padx=6)
        ttk.Checkbutton(toolbar, text='Только карты', variable=self.cards_only, command=self.refresh).pack(side='left')
        ttk.Checkbutton(toolbar, text='Незавершённые', variable=self.pending_only, command=self.refresh).pack(side='left')
        ttk.Checkbutton(toolbar, text='Поверх окон', variable=self.pin, command=lambda: self.root.attributes('-topmost', self.pin.get())).pack(side='right')
        left = ttk.Frame(workspace, padding=(0, 0, 10, 0))
        left.grid(row=1, column=0, sticky='ns')
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text='ВАШИ СНИМКИ', style='Heading.TLabel').grid(row=0, column=0, pady=(0, 8), sticky='w')
        self.frames = ttk.Treeview(left, columns=('name', 'done'), show='headings', selectmode='browse', height=10)
        self.frames.heading('name', text='Время')
        self.frames.heading('done', text='Готово')
        self.frames.column('name', width=118, stretch=False)
        self.frames.column('done', width=55, stretch=False)
        self.frames.grid(row=1, column=0, sticky='ns')
        scroll = ttk.Scrollbar(left, command=self.frames.yview)
        scroll.grid(row=1, column=1, sticky='ns')
        self.frames.configure(yscrollcommand=scroll.set)
        self.frames.bind('<<TreeviewSelect>>', self.select_frame)
        ttk.Button(left, text='Папка снимков', command=lambda: self.show_folder(self.album.folder)).grid(row=2, column=0, sticky='ew', pady=8)
        center = ttk.Frame(workspace, padding=(0, 0, 12, 0))
        center.grid(row=1, column=1, sticky='nsew')
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)
        ttk.Label(center, textvariable=self.scene_title, style='Heading.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 8))
        self.canvas = tk.Canvas(center, background='#162f3c', highlightthickness=0, height=200, width=300)
        self.canvas.grid(row=1, column=0, sticky='nsew')
        self.canvas.bind('<Configure>', lambda e: self.render())
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.up)
        nav = ttk.Frame(center)
        nav.grid(row=2, column=0, sticky='ew', pady=7)
        ttk.Button(nav, text='←', width=3, command=lambda: self.move(-1)).pack(side='left')
        self.items = ttk.Combobox(nav, textvariable=self.item_name, state='readonly', width=25)
        self.items.pack(side='left', fill='x', expand=True, padx=5)
        self.items.bind('<<ComboboxSelected>>', self.change_item)
        ttk.Button(nav, text='→', width=3, command=lambda: self.move(1)).pack(side='left')
        comparison = ttk.Frame(center, style='Card.TFrame', padding=10)
        comparison.grid(row=3, column=0, sticky='ew')
        comparison.columnconfigure((0, 1), weight=1)
        ttk.Label(comparison, text='Текущая вырезка', style='Card.TLabel').grid(row=0, column=0)
        ttk.Label(comparison, text='Ближайший шаблон', style='Card.TLabel').grid(row=0, column=1)
        self.crop_preview = ttk.Label(comparison, style='Card.TLabel', anchor='center')
        self.crop_preview.grid(row=1, column=0, pady=6)
        self.sample_preview = ttk.Label(comparison, style='Card.TLabel', anchor='center', text='Пока нет')
        self.sample_preview.grid(row=1, column=1, pady=6)
        ttk.Label(center, text='Рамка неверна? Перерисуйте её мышью на снимке.', style='Muted.TLabel').grid(row=4, column=0, sticky='w', pady=5)
        side = ttk.Frame(workspace, width=320)
        side.grid(row=1, column=2, sticky='nsew')
        side.columnconfigure(0, weight=1)
        side.rowconfigure(3, weight=1)
        ttk.Label(side, text='РАСПОЗНАВАНИЕ', style='Heading.TLabel').grid(row=0, column=0, sticky='w')
        self.badge = tk.Label(side, textvariable=self.advice_title, anchor='w', background='#e2edf4', foreground=INK, font=('Segoe UI', 12, 'bold'), padx=12, pady=9)
        self.badge.grid(row=1, column=0, sticky='ew', pady=(8, 5))
        self.busy = ttk.Progressbar(side, mode='indeterminate')
        self.busy.grid(row=2, column=0, sticky='ew')
        detail = ttk.Notebook(side)
        detail.grid(row=3, column=0, sticky='nsew', pady=(8, 5))
        summary_scroll, settings_scroll = ScrollFrame(detail), ScrollFrame(detail)
        summary, settings = summary_scroll.inner, settings_scroll.inner
        detail.add(summary_scroll, text='Результат')
        detail.add(settings_scroll, text='Настройки')
        tk.Message(summary, textvariable=self.advice_detail, width=285, background='#f2f5f9', foreground=INK, font=('Segoe UI', 10), anchor='nw').pack(fill='x')
        ttk.Label(summary, textvariable=self.advice_meta, wraplength=285, style='Muted.TLabel').pack(fill='x', pady=7)
        self.candidates = ttk.Treeview(summary, columns=('card', 'score'), show='headings', height=3, selectmode='none')
        self.candidates.heading('card', text='Кандидат')
        self.candidates.heading('score', text='Похожесть')
        self.candidates.column('card', width=145, stretch=True)
        self.candidates.column('score', width=88, stretch=False)
        self.candidates.pack(fill='x')
        ttk.Button(summary, text='Распознать ещё раз · Ctrl+R', command=self.request_analysis).pack(fill='x', pady=7)
        ttk.Button(summary, text='Установить 13 стартовых карт', command=self.install_samples).pack(fill='x')
        ttk.Checkbutton(settings, text='Пропускать уверенно распознанные', variable=self.auto_skip).pack(anchor='w')
        ttk.Label(settings, text='По умолчанию вы подтверждаете ответ сами. Автопропуск не создаёт новых шаблонов.', wraplength=275, style='Muted.TLabel').pack(fill='x', pady=(0, 10))
        ttk.Checkbutton(settings, text='Скрывать уже знакомые карты', variable=self.missing_only, command=self.refilter).pack(anchor='w')
        ttk.Checkbutton(settings, text='Сохранять дополнительный образец', variable=self.variant).pack(anchor='w')
        ttk.Label(settings, text='Включайте для другой яркости или перекрытия. Обычное подтверждение знакомой карты не создаёт дубликат.', wraplength=275, style='Muted.TLabel').pack(fill='x', pady=6)
        ttk.Button(settings, text='Проверить последнюю автоподпись', command=self.review_last).pack(fill='x', pady=8)
        ttk.Button(settings, text='Добавить отдельный символ', command=self.add_region).pack(fill='x')
        summary_scroll.enable_wheel()
        settings_scroll.enable_wheel()
        ttk.Label(side, text='Выберите правильную метку', style='Heading.TLabel').grid(row=4, column=0, sticky='w', pady=(8, 4))
        self.kind_picker = ttk.Combobox(side, textvariable=self.kind, values=list(KIND_LABELS), state='readonly')
        self.kind_picker.grid(row=5, column=0, sticky='ew', pady=(0, 5))
        self.kind_picker.bind('<<ComboboxSelected>>', self.kind_changed)
        self.label_picker = ColorChoice(side, self.label, choice_color, width=22, on_select=self.user_selected)
        self.label_picker.grid(row=6, column=0, sticky='ew')
        self.save_button = ttk.Button(side, text='Подтвердить и дальше  ↵', style='Primary.TButton', command=self.save_next)
        self.save_button.grid(row=7, column=0, sticky='ew', pady=(9, 5))
        ttk.Button(side, text='Не видно / пропустить', command=self.skip).grid(row=8, column=0, sticky='ew')
        foot = ttk.Frame(self.root, padding=(16, 4, 16, 8))
        foot.grid(row=2, column=0, sticky='ew')
        foot.columnconfigure(0, weight=1)
        ttk.Label(foot, textvariable=self.status, wraplength=820).grid(row=0, column=0, sticky='w')
        ttk.Label(foot, textvariable=self.progress_text, style='Heading.TLabel').grid(row=0, column=1, sticky='e')
        self._library(library)
        text = tk.Text(help_tab, wrap='word', background=SURFACE, foreground=INK, font=('Segoe UI', 12), padx=30, pady=25, relief='flat')
        text.pack(fill='both', expand=True)
        text.insert('1.0', 'Как работает помощник\n\nЭто локальное сравнение с вашими шаблонами, а не нейросеть и не облачный сервис.\n\n1. Выделенная карта сравнивается с сохранёнными образцами.\n2. Справа видны результат, оценка похожести и ближайшие кандидаты.\n3. Вы подтверждаете ответ либо выбираете правильную карту.\n4. Новая карта пополняет базу. Знакомая — просто отмечается без повторного файла.\n\nЗелёный результат: знакомая карта. Жёлтый: нужно подтверждение. Серый: не удалось прочитать. Красный: ошибка в базе. Оценка похожести — не вероятность правильного ответа.\n\nЕсли база пуста, сохраните первую карту или установите стартовые примеры. Один образец не покрывает любое освещение и перекрытие. Для другого вида включите «Сохранять дополнительный образец».\n\nПо умолчанию карты не перескакивают сами. Автопропуск включается отдельно на вкладке «Настройки». Автоподписи никогда не превращаются в обучающие шаблоны.\n\nEnter — подтвердить карту. В открытом списке Enter только выбирает пункт: нажмите ещё раз для сохранения. Ctrl+R — повторить распознавание. Стрелки возле области — переход без сохранения.\n\nВсе исходные PNG и подписи остаются в captures/inbox/. Новое оформление не требует переносить старые файлы. При неверной рамке перерисуйте её на снимке: помощник проверит новую вырезку. Цифры подписываются по одному символу на вкладке настроек.\n')
        text.config(state='disabled')

    def _library(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        top = ttk.Frame(parent, padding=12)
        top.grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(top, textvariable=self.coverage, style='Heading.TLabel').pack(side='left')
        ttk.Button(top, text='Обновить базу', command=self.refresh_library).pack(side='right')
        ttk.Button(top, text='Открыть папку шаблонов', command=lambda: self.show_folder(self.album.templates)).pack(side='right', padx=6)
        self.library = ttk.Treeview(parent, columns=('card', 'count'), show='headings', selectmode='browse')
        self.library.heading('card', text='Карта')
        self.library.heading('count', text='Образцов')
        self.library.grid(row=1, column=0, sticky='nsew', padx=12, pady=12)
        self.library.bind('<<TreeviewSelect>>', self.library_selected)
        self.library.tag_configure('red', foreground='#c62828')
        self.library_preview = ttk.Label(parent, text='Выберите карту, чтобы увидеть образец', anchor='center', width=35)
        self.library_preview.grid(row=1, column=1, padx=25)

    def show_folder(self, folder):
        try:
            open_folder(folder)
        except OSError as exc:
            messagebox.showerror('Не удалось открыть папку', str(exc), parent=self.root)

    def dirty(self):
        if self.pending_rect is not None:
            return True
        if not self.record or not self.item_id or not self.review.manual_choice:
            return False
        item = self.record['items'][self.item_id]
        return resolve_choice(self.kind_code(), self.label.get()) != (item['kind'], item.get('label'))

    def can_leave(self):
        return not self.dirty() or messagebox.askyesno('Метка ещё не сохранена', 'Перейти без сохранения текущей метки или рамки?', parent=self.root)

    def kind_code(self):
        return KIND_LABELS[self.kind.get()]

    def refresh_library(self):
        counts, self.library_paths = template_inventory(self.album.templates)
        self.known_cards = set(counts)
        self.coverage.set(f'Изучено {len(counts)} из 52 карт  ·  образцов {sum(counts.values())}')
        for iid in self.library.get_children():
            self.library.delete(iid)
        for display in filtered_choices(set()):
            kind, label = resolve_choice('card', display)
            if kind == 'card':
                self.library.insert('', 'end', iid=label, values=(display, counts[label]), tags=('red',) if label[1] in 'hd' else ())

    def library_selected(self, event=None):
        selection = self.library.selection()
        if selection:
            paths = self.library_paths.get(selection[0], [])
            self.set_preview(self.library_preview, read_image(paths[0]) if paths else None, 240, 300, 'Для этой карты пока нет образцов')

    def refresh(self):
        if not self.can_leave():
            self.cards_only.set(self.filter_snapshot[0])
            self.pending_only.set(self.filter_snapshot[1])
            return
        self.filter_snapshot = self.cards_only.get(), self.pending_only.get()
        self.review.invalidate()
        self.pending_rect = None
        self.refresh_library()
        old = self.record['id'] if self.record else None
        self.records, errors = self.album.records()
        visible = [r for r in self.records if not self.pending_only.get() or progress(r, self.cards_only.get())[0] < progress(r, self.cards_only.get())[1]]
        for iid in self.frames.get_children():
            self.frames.delete(iid)
        for record in visible:
            done, total = progress(record, self.cards_only.get())
            try:
                title = datetime.fromisoformat(record['created_at']).astimezone().strftime('%d.%m %H:%M')
            except ValueError:
                title = record['id'][:8]
            self.frames.insert('', 'end', iid=record['id'], values=(title, f'{done}/{total}'))
        target = next((r for r in visible if r['id'] == old), visible[0] if visible else None)
        if target:
            self.open_record(target['id'])
        else:
            self.record = self.image = self.item_id = None
            self.canvas.delete('all')
            self.canvas.create_text(150, 110, text='Здесь будет ваш стол\n\nНажмите «Импорт снимков»\nили соберите кадры клавишей F8.', fill='#adcbd0', justify='center', font=('Segoe UI', 12))
            self.scene_title.set('Нет снимков для разбора')
            self.progress_text.set('0 / 0')
            self.items.configure(values=[])
            self.item_name.set('')
            self.set_preview(self.crop_preview, None, 200, 90, 'Нет вырезки')
            self.set_preview(self.sample_preview, None, 200, 90, 'Нет шаблона')
            self.reset_advice('Нет снимков', 'Импортируйте PNG/JPEG или вернитесь в панель и включите сбор F8.')
        if errors:
            self.status.set(f'Пропущено повреждённых файлов: {len(errors)}. Первый: {errors[0]}')

    def select_frame(self, event=None):
        selected = self.frames.selection()
        if not selected or (self.record and selected[0] == self.record['id']):
            return
        if self.can_leave():
            self.open_record(selected[0])
        elif self.record and self.frames.exists(self.record['id']):
            self.frames.selection_set(self.record['id'])

    def open_record(self, identifier, item=None):
        self.review.invalidate()
        try:
            self.record = self.album.load(identifier)
            self.image = self.album.image(self.record)
            self.pending_rect = None
            names = eligible_items(self.record, self.cards_only.get())
            self.item_ids = {region_title(name)+'  ·  '+name: name for name in names}
            self.items.configure(values=list(self.item_ids))
            if self.frames.exists(identifier):
                self.frames.selection_set(identifier)
                self.frames.see(identifier)
            target = item if item in names else next((n for n in names if self.record['items'][n]['status'] == 'pending'), names[0] if names else None)
            self.scene_title.set(f'Снимок {identifier[:8]}  ·  {self.image.shape[1]} × {self.image.shape[0]}')
            if target:
                self.choose_item(target)
            else:
                self.item_id = None
                self.render()
                self.reset_advice('Нет областей', 'Отключите «Только карты», чтобы увидеть дополнительные вырезки.')
        except (OSError, ValueError, KeyError) as exc:
            self.reset_advice('Не удалось открыть снимок', str(exc), '#f9dedc')

    def choose_item(self, name):
        self.item_id = name
        self.pending_rect = None
        item = self.record['items'][name]
        code = 'card' if item['kind'] == 'empty' and name.startswith(('hero', 'board')) else item['kind']
        self.kind.set(next(text for text, value in KIND_LABELS.items() if value == code))
        self.item_name.set(next((text for text, key in self.item_ids.items() if key == name), name))
        self.set_choices(item.get('label'))
        self.render()
        self.show_crop()
        done, total = progress(self.record, self.cards_only.get())
        self.progress_text.set(f'{done} / {total} областей')
        self.status.set(region_title(name)+' · '+STATUS_LABELS[item['status']]+(' · проверьте предложенную рамку' if self.record.get('suggested_rois') else ''))
        self.request_analysis()

    def set_choices(self, stored=None):
        kind = self.kind_code()
        values = filtered_choices(self.known_cards, self.missing_only.get(), stored) if kind == 'card' else (['empty'] if kind == 'empty' else (['back'] if kind == 'back' else list('0123456789.,KMB')))
        self.label_picker.configure(values=values)
        self.label.set(display_choice(stored) if kind == 'card' else (stored if stored in values else (values[0] if kind in ('empty', 'back') else '')))

    def refilter(self):
        _, label = resolve_choice(self.kind_code(), self.label.get())
        self.set_choices(label)

    def user_selected(self):
        self.review.select()
        self.status.set('Выбрано вручную. Нажмите «Подтвердить и дальше», чтобы сохранить.')

    def kind_changed(self, event=None):
        self.review.invalidate()
        self.review.select()
        self.busy.stop()
        self.set_choices()
        if self.kind_code() in ('glyph', 'back'):
            self.reset_advice('Ручная подпись', 'Выберите символ или рубашку. Помощник автоматически определяет только карты и пустые места.')
        else:
            self.request_analysis()
            self.review.select()

    def change_item(self, event=None):
        name = self.item_ids.get(self.item_name.get())
        if name and self.can_leave():
            self.choose_item(name)
        elif self.item_id:
            self.item_name.set(next((text for text, key in self.item_ids.items() if key == self.item_id), self.item_id))

    def move(self, delta):
        if not self.record or not self.can_leave():
            return
        names = eligible_items(self.record, self.cards_only.get())
        index = names.index(self.item_id) if self.item_id in names else 0
        self.choose_item(names[(index+delta) % len(names)])

    def render(self):
        if self.image is None:
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if min(width, height) < 20:
            return
        ih, iw = self.image.shape[:2]
        self.scale = min((width-12)/iw, (height-12)/ih)
        self.offset = ((width-round(iw*self.scale))//2, (height-round(ih*self.scale))//2)
        self.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)).resize((max(1, round(iw*self.scale)), max(1, round(ih*self.scale)))))
        self.canvas.delete('all')
        self.canvas.create_image(*self.offset, image=self.photo, anchor='nw')
        for name, item in self.record['items'].items():
            rect = self.pending_rect if name == self.item_id and self.pending_rect else item['rect']
            x, y, w, h = Rect(*rect).pixels(iw, ih)
            x, y = x*self.scale+self.offset[0], y*self.scale+self.offset[1]
            color = '#ffffff' if name == self.item_id else {'exported': '#4adc9d', 'reused': '#79c2ff', 'skipped': '#8d9ba3'}.get(item['status'], '#ddaf64')
            self.canvas.create_rectangle(x, y, x+w*self.scale, y+h*self.scale, outline=color, width=2 if name == self.item_id else 1, tags='selected' if name == self.item_id else 'roi')
            self.canvas.create_text(x, y-3, text=name, anchor='sw', fill=color, font=('Segoe UI', 8))

    def set_preview(self, widget, image, width=200, height=85, empty='Нет образца'):
        if image is None or not image.size:
            widget.configure(image='', text=empty)
            widget.photo = None
            return
        ih, iw = image.shape[:2]
        scale = min(5., width/iw, height/ih)
        widget.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).resize((max(1, round(iw*scale)), max(1, round(ih*scale)))))
        widget.configure(image=widget.photo, text='')

    def current_crop(self):
        return Rect(*(self.pending_rect or self.record['items'][self.item_id]['rect'])).crop(self.image)

    def show_crop(self):
        if self.record and self.item_id:
            self.set_preview(self.crop_preview, self.current_crop())

    def down(self, event):
        if self.image is None or not self.item_id:
            return
        self.review.invalidate()
        self.busy.stop()
        self.start = event.x, event.y
        self.canvas.delete('drag')
        self.drag_box = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='#ffffff', width=2, tags='drag')

    def drag(self, event):
        if self.start:
            self.canvas.coords(self.drag_box, *self.start, event.x, event.y)

    def up(self, event):
        if not self.start:
            return
        x1, y1, x2, y2 = selection_bounds((self.start[0]-self.offset[0], self.start[1]-self.offset[1], event.x-self.offset[0], event.y-self.offset[1]), self.scale, self.image.shape[1], self.image.shape[0])
        self.start = None
        if min(x2-x1, y2-y1) < 2:
            self.render()
            self.request_analysis()
            return
        self.pending_rect = [x1/self.image.shape[1], y1/self.image.shape[0], (x2-x1)/self.image.shape[1], (y2-y1)/self.image.shape[0]]
        self.render()
        self.show_crop()
        self.request_analysis()
        self.status.set('Рамка изменена. Распознаётся новая вырезка; сохраните её вместе с меткой.')

    def reset_advice(self, title, detail, color='#e2edf4'):
        self.busy.stop()
        self.advice_title.set(title)
        self.advice_detail.set(detail)
        self.advice_meta.set('Локальное сравнение с вашими шаблонами')
        self.badge.configure(background=color)
        for iid in self.candidates.get_children():
            self.candidates.delete(iid)

    def request_analysis(self, event=None):
        if not self.record or not self.item_id:
            return
        if self.future:
            self.future.cancel()
        ticket = self.review.begin(self.record['id'], self.item_id, self.record['revision'])
        if self.kind_code() not in ('card', 'empty'):
            self.review.invalidate()
            self.reset_advice('Ручная подпись', 'Выберите символ или рубашку. Для цифр нужен отдельный образец каждого символа.')
            return
        self.reset_advice('Сравниваю с базой…', 'Программа работает в фоне. Можно выбрать правильную карту вручную — результат проверки не исчезнет.')
        self.busy.start(12)
        self.set_preview(self.sample_preview, None)
        crop = self.current_crop().copy()
        future = self.future = self.executor.submit(self.assistant.inspect, crop)
        def done(job):
            if not job.cancelled():
                try:
                    self.results.put((ticket, job.result(), None))
                except Exception as exc:
                    self.results.put((ticket, None, str(exc)))
        future.add_done_callback(done)
        return 'break'

    def poll(self):
        if self.closed:
            return
        while not self.results.empty():
            ticket, report, error = self.results.get_nowait()
            if ticket != self.review.ticket:
                continue
            if error:
                self.review.invalidate()
                self.reset_advice('Ошибка распознавания', error, '#f9dedc')
                continue
            self.review.accept(ticket, report)
            self.busy.stop()
            self.known_cards = set(report.known_cards)
            self.coverage.set(f'Изучено {len(report.known_cards)} из 52 карт · {report.template_count} образцов карт и пустоты')
            self.advice_title.set(report.title)
            self.advice_detail.set(report.reason)
            self.advice_meta.set(f'{report.template_count} образцов  ·  {report.elapsed_ms:.0f} мс  ·  без облака')
            self.badge.configure(background={'recognized': '#d9f2e6', 'suggestion': '#fff0cf', 'conflict': '#f9dedc'}.get(report.state, '#e2edf4'))
            for iid in self.candidates.get_children():
                self.candidates.delete(iid)
            for candidate in report.candidates:
                self.candidates.insert('', 'end', values=(display_choice('empty' if candidate['kind'] == 'empty' else candidate['label']), f'{max(0, candidate["score"]):.1%}'))
            if report.candidates and report.candidates[0].get('path'):
                try:
                    self.set_preview(self.sample_preview, read_image(report.candidates[0]['path']))
                except (OSError, ValueError):
                    self.set_preview(self.sample_preview, None)
            item = self.record['items'][self.item_id]
            if report.suggestion and not self.review.manual_choice and item['status'] == 'pending':
                self.set_choices(report.suggestion.label)
            elif not self.review.manual_choice:
                self.refilter()
            if self.review.can_auto_accept(self.auto_skip.get(), self.variant.get(), item['status'] == 'pending', self.pending_rect is not None):
                try:
                    self.record = self.album.accept_known(self.record['id'], self.item_id, report.suggestion.kind, report.suggestion.label,
                                                          report.suggestion.confidence, report.suggestion.method, self.record['revision'])
                    self.last_auto = self.record['id'], self.item_id
                    self.advance()
                except (OSError, ValueError, KeyError) as exc:
                    self.reset_advice('Автоподпись не сохранена', str(exc), '#f9dedc')
        self.root.after(100, self.poll)

    def save_next(self):
        self.apply()

    def skip(self):
        self.apply(skip=True)

    def apply(self, skip=False):
        if not self.record or not self.item_id:
            return
        kind, label = resolve_choice(self.kind_code(), self.label.get())
        self.review.invalidate()
        try:
            if not skip and kind == 'card' and has_card_template(self.album.templates, label) and not self.variant.get() and self.record['items'][self.item_id]['status'] == 'pending':
                self.record = self.album.accept_known(self.record['id'], self.item_id, kind, label, 1., 'human confirmed existing', self.record['revision'], automatic=False, rect=self.pending_rect)
            else:
                self.record = self.album.annotate(self.record['id'], self.item_id, kind, label, rect=self.pending_rect,
                                                  skip=skip, revision=self.record['revision'])
            self.pending_rect = None
            self.advance()
        except (OSError, ValueError, KeyError) as exc:
            self.review.select()
            self.status.set('Не сохранено: '+str(exc))
            messagebox.showerror('Проверьте метку', str(exc), parent=self.root)

    def advance(self):
        self.busy.stop()
        done, total = progress(self.record, self.cards_only.get())
        if self.frames.exists(self.record['id']):
            self.frames.set(self.record['id'], 'done', f'{done}/{total}')
        pending = next((n for n in eligible_items(self.record, self.cards_only.get()) if self.record['items'][n]['status'] == 'pending'), None)
        if pending:
            self.choose_item(pending)
            return
        for record in self.album.records()[0]:
            names = eligible_items(record, self.cards_only.get())
            if any(record['items'][name]['status'] == 'pending' for name in names):
                self.open_record(record['id'])
                return
        self.choose_item(self.item_id)
        self.status.set('Готово! Все выбранные области разобраны. Шаблоны сохранены — можно вернуться в панель и запустить HUD.')

    def install_samples(self):
        try:
            count = seed_templates(self.album.templates)
            self.refresh_library()
            self.request_analysis()
            self.status.set(f'Добавлено {count} стартовых образцов. Это 13 карт, а не вся колода.')
        except OSError as exc:
            self.status.set('Не удалось установить образцы: '+str(exc))

    def review_last(self):
        if self.last_auto and self.can_leave():
            self.auto_skip.set(False)
            self.open_record(*self.last_auto)
            self.status.set('Автопропуск выключен. Проверьте и при необходимости исправьте эту метку.')

    def add_region(self):
        if self.pending_rect is None:
            self.status.set('Выделите один символ мышью, затем нажмите «Добавить отдельный символ».')
            return
        try:
            self.record, item = self.album.add_region(self.record['id'], self.pending_rect)
            self.cards_only.set(False)
            self.open_record(self.record['id'], item)
        except (OSError, ValueError) as exc:
            self.status.set(str(exc))

    def import_files(self):
        if not self.can_leave():
            return
        paths = filedialog.askopenfilenames(parent=self.root, filetypes=[('Снимки', '*.png *.jpg *.jpeg')])
        if not paths:
            return
        failures = []
        for path in paths:
            try:
                self.album.add(read_image(path), load_profile()['rois'], {'method': 'file import'}, suggested=True)
            except (OSError, ValueError) as exc:
                failures.append(str(exc))
        self.pending_rect = None
        self.review.invalidate()
        self.refresh()
        self.status.set(f'Импортировано {len(paths)-len(failures)} снимков. Проверьте предложенные рамки.'+(' Ошибки: '+'; '.join(failures[:2]) if failures else ''))

    def enter(self, event):
        if event.widget.winfo_class() not in ('TButton', 'Button', 'TCombobox', 'Text', 'TNotebook'):
            self.save_next()
            return 'break'

    def close(self):
        if self.can_leave():
            self.closed = True
            self.review.invalidate()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.root.destroy()

    def run(self):
        self.root.mainloop()
