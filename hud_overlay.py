"""Tk stays on main thread; capture/CV and Monte Carlo have separate workers."""
import queue
import random
import sys
import threading
import time
import tkinter as tk
from dataclasses import replace
from tkinter import ttk

from hand_history import HandLogger
from poker_coach import Coach, fmt
from screen import enable_dpi, grab, load_config
from plain import make_verdict, pot_line
from ui_text import card_text, short_name, signed_money
from ui_theme import PALETTE as P, SUIT_COLORS, apply_theme, card, font, tone_color
from vision import Recognizer, Stabilizer, TableState, TemplateBank

HUD_WIDTH = 680
HUD_HEIGHT = 800
HUD_HEIGHT_ADVANCED = 1040
STAT_TITLES = {'equity': 'Ваш шанс выиграть', 'odds': 'Нужно для колла'}
STAT_HINTS = {'equity': 'примерно столько банка вы получите', 'odds': 'колл окупается, если шанс не ниже'}


def replace_latest(channel, item):
    try:
        channel.put_nowait(item)
    except queue.Full:
        try:
            channel.get_nowait()
        except queue.Empty:
            return replace_latest(channel, item)
        channel.put_nowait(item)


class Pipeline:
    def __init__(self, config, template_dir, coach):
        self.config, self.template_dir, self.coach = config, template_dir, coach
        self.stop = threading.Event()
        self.reload = threading.Event()
        self.jobs = queue.Queue(1)
        self.events = queue.Queue()
        self.override = None
        self.lock = threading.Lock()
        self.frame = None
        self.token = 0
        self.signature = None
        self.threads = [threading.Thread(target=self.capture, daemon=True, name='screen-cv'),
                        threading.Thread(target=self.analyze, daemon=True, name='equity')]

    def start(self):
        for thread in self.threads:
            thread.start()

    def set_signature(self, signature):
        with self.lock:
            if signature != self.signature:
                self.signature = signature
                self.token += 1
            return self.token

    def snapshot(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def capture(self):
        try:
            import mss
            bank = TemplateBank(self.template_dir)
            recognizer = Recognizer(self.config, bank)
            stabilizer = Stabilizer()
            submitted = None
            with mss.mss() as sct:
                while not self.stop.is_set():
                    start = time.monotonic()
                    try:
                        if self.reload.is_set():
                            bank.reload()
                            stabilizer = Stabilizer()
                            self.reload.clear()
                        frame = grab(sct, self.config)
                        with self.lock:
                            self.frame = frame
                        state, readings, error = recognizer.read(frame, self.override)
                        stable = stabilizer.update(state)
                        signature = stable.signature() if stable else None
                        token = self.set_signature(signature)
                        self.events.put(('status', token, readings, error if error else ('Стабильно' if stable else 'Стабилизация: нужны 2 кадра')))
                        if stable and token != submitted:
                            replace_latest(self.jobs, (token, stable))
                            submitted = token
                    except Exception as exc:
                        stabilizer.update(None)
                        token = self.set_signature(None)
                        self.events.put(('error', token, str(exc)))
                    self.stop.wait(max(.001, self.config.get('interval', .275)-(time.monotonic()-start)))
        except Exception as exc:
            self.events.put(('error', self.set_signature(None), str(exc)))

    def analyze(self):
        while not self.stop.is_set():
            try:
                token, state = self.jobs.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                result = self.coach.analyze(state)
                self.events.put(('result', token, state, result))
            except Exception as exc:
                self.events.put(('error', token, str(exc)))

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=.5)



class HUD:
    STAT_KEYS = ('equity', 'odds')

    def __init__(self, args):
        enable_dpi()
        self.args = args
        self.root = tk.Tk()
        apply_theme(self.root)
        self.root.title('Pokerist • подсказки')
        self.pinned = tk.BooleanVar(value=True)
        self.root.attributes('-topmost', self.pinned.get())
        self.root.attributes('-alpha', .93)
        self.root.geometry(f'{HUD_WIDTH}x800+30+30')
        self.root.minsize(600, 740)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.coach = Coach(args.iterations, args.seed)
        self.logger = HandLogger()
        self.pipeline = None
        self.config = None
        self.demo_mode = args.demo
        self.demo_token = 0
        self.demo_results = queue.Queue()
        self.override = None
        self.current = None
        self.last_live = None
        self.closed = False
        self.empty_since = None
        self.drag_origin = (0, 0)
        self.album_worker = self.album_hotkey = None
        self.record_enabled = tk.BooleanVar(value=False)
        self.record_status = tk.StringVar(value='Сбор выключен. Включите F8 или нажимайте «Снимок в очередь».')
        self.hide_answer = tk.BooleanVar(value=False)
        self.advanced_visible = False
        self.status = tk.StringVar(value='Загрузка…')
        self.opponents = tk.StringVar(value='авто')
        self.made = tk.StringVar(value='Ваша рука: —')
        self.recommendation = tk.StringVar(value='Ждём стабильный кадр')
        self.summary = tk.StringVar(value='Подсказка появится, когда карты и числа распознаны уверенно.')
        self.pot_line = tk.StringVar(value='')
        self.confidence = tk.StringVar(value='Распознавание: ещё не запущено')
        self.mode_text = tk.StringVar(value='')
        self.stat_values = {key: tk.StringVar(value='—') for key in self.STAT_KEYS}
        self.stat_hints = {key: tk.StringVar(value=STAT_HINTS[key]) for key in self.STAT_KEYS}
        self.stat_labels = {}
        self._build()
        if not args.demo:
            try:
                self.config = load_config(args.config)
                if sys.platform == 'win32':
                    self.config['window_title'] = args.window_title or self.config.get('window_title') or 'Texas Poker'
                self.pipeline = Pipeline(self.config, args.templates, self.coach)
                self.pipeline.start()
                # Place beside the calibrated client, not on the captured table.
                c = self.config['capture']
                x = c['left']+c['width']+8
                if x+HUD_WIDTH <= self.root.winfo_screenwidth():
                    self.root.geometry(f'+{x}+{max(0, c["top"])}')
            except Exception as exc:
                self.status.set(f'Захват не запущен: {exc}. Доступна тестовая раздача.')
                self.demo_mode = True
        if args.demo:
            self.demo()
        self.refresh_mode()
        self.root.after(100, self.poll)

    def _build(self):
        head = tk.Frame(self.root, bg=P['bg'])
        head.pack(fill='x', padx=16, pady=(14, 2))
        title = tk.Label(head, text='♠ Pokerist HUD', bg=P['bg'], fg=P['accent'], font=font(17, 'bold'))
        title.pack(side='left')
        self.mode_badge = tk.Label(head, textvariable=self.mode_text, bg=P['muted'], fg=P['bg'], font=font(8, 'bold'), padx=9, pady=3)
        self.mode_badge.pack(side='left', padx=12)
        ttk.Checkbutton(head, text='Поверх окон', variable=self.pinned,
                        command=lambda: self.root.attributes('-topmost', self.pinned.get())).pack(side='right')
        for widget in (head, title):
            widget.bind('<ButtonPress-1>', self._drag_start)
            widget.bind('<B1-Motion>', self._drag_move)
        tk.Label(self.root, text='Перетащите заголовок, чтобы HUD не закрывал стол. Подсказки никогда не нажимают кнопки игры.',
                 bg=P['bg'], fg=P['muted'], font=font(9), anchor='w', wraplength=640, justify='left').pack(fill='x', padx=16, pady=(0, 8))

        table = card(self.root)
        table.pack(fill='x', padx=14)
        row = tk.Frame(table, bg=P['surface'])
        row.pack(fill='x')
        tk.Label(row, text='Соперников в игре:', bg=P['surface'], fg=P['muted'], font=font(10)).pack(side='left')
        ttk.Button(row, text='−', width=3, style='Card.TButton', command=lambda: self.adjust(-1)).pack(side='left', padx=(10, 2))
        tk.Label(row, textvariable=self.opponents, bg=P['surface'], fg=P['text'], font=font(11, 'bold'), width=12).pack(side='left')
        ttk.Button(row, text='+', width=3, style='Card.TButton', command=lambda: self.adjust(1)).pack(side='left', padx=2)
        ttk.Button(row, text='Авто', style='Card.TButton', command=self.auto).pack(side='left', padx=8)
        ttk.Checkbutton(table, text='Тренировка: скрыть ответ, сначала решите сами', variable=self.hide_answer,
                        style='Card.TCheckbutton', command=self.redraw).pack(anchor='w', pady=(8, 0))

        hand = card(self.root)
        hand.pack(fill='x', padx=14, pady=8)
        self.cards = tk.Frame(hand, bg=P['surface'])
        self.cards.pack(fill='x')

        verdict = card(self.root, padding=(16, 12))
        verdict.pack(fill='x', padx=14)
        tk.Label(verdict, text='ЧТО ДЕЛАТЬ', bg=P['surface'], fg=P['muted'], font=font(9, 'bold'), anchor='w').pack(fill='x')
        self.reco_label = tk.Label(verdict, textvariable=self.recommendation, bg=P['surface'], fg=P['text'],
                                   font=font(18, 'bold'), anchor='w', justify='left', wraplength=620)
        self.reco_label.pack(fill='x', pady=(2, 0))
        tk.Label(verdict, textvariable=self.summary, bg=P['surface'], fg=P['text'], font=font(10), anchor='w',
                 justify='left', wraplength=620).pack(fill='x', pady=(4, 10))
        facts = tk.Frame(verdict, bg=P['surface'])
        facts.pack(fill='x')
        for column, key in enumerate(self.STAT_KEYS):
            facts.grid_columnconfigure(column, weight=1, uniform='facts')
            tile = card(facts, padding=(10, 8))
            tile.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else 6, 0))
            tk.Label(tile, text=STAT_TITLES[key], bg=P['surface'], fg=P['muted'], font=font(9, 'bold'), anchor='w').pack(fill='x')
            value = ttk.Label(tile, textvariable=self.stat_values[key], style='CardValue.TLabel')
            value.pack(anchor='w')
            self.stat_labels[key] = value
            tk.Label(tile, textvariable=self.stat_hints[key], bg=P['surface'], fg=P['muted'], font=font(8),
                     wraplength=260, justify='left', anchor='w').pack(fill='x')
        tk.Label(verdict, textvariable=self.made, bg=P['surface'], fg=P['muted'], font=font(9), anchor='w').pack(fill='x', pady=(8, 0))
        tk.Label(verdict, textvariable=self.confidence, bg=P['surface'], fg=P['muted'], font=font(8), anchor='w',
                 justify='left', wraplength=620).pack(fill='x', pady=(2, 0))
        tk.Label(self.root, textvariable=self.pot_line, bg=P['bg'], fg=P['muted'], font=font(9), anchor='w').pack(fill='x', padx=18, pady=(6, 0))

        # Bottom rows are packed before the optional advanced panel, which expands last.
        tk.Label(self.root, textvariable=self.status, bg=P['surface_alt'], fg=P['text'], font=font(9), anchor='w',
                 justify='left', wraplength=640, padx=12, pady=6).pack(side='bottom', fill='x')
        controls = tk.Frame(self.root, bg=P['bg'])
        controls.pack(side='bottom', fill='x', padx=14, pady=(6, 8))
        ttk.Button(controls, text='Тестовая раздача', command=self.demo).pack(side='left')
        ttk.Button(controls, text='Вернуться к столу', style='Accent.TButton', command=self.live).pack(side='left', padx=6)
        ttk.Button(controls, text='Уроки и словарь', command=self.open_learning).pack(side='left')
        self.advanced_button = ttk.Button(controls, text='Подробнее ▾', command=self.toggle_advanced)
        self.advanced_button.pack(side='right')

        # Hidden by default: the maths and the screenshot tools are for later.
        self.advanced = tk.Frame(self.root, bg=P['bg'])
        tk.Label(self.advanced, text='Подробные расчёты: для тех, кто хочет понять математику. Основное решение — выше.',
                 bg=P['bg'], fg=P['muted'], font=font(9), anchor='w', wraplength=640, justify='left').pack(fill='x')
        self.details = tk.Text(self.advanced, wrap='word', height=8, bg=P['field'], fg=P['text'], font=font(10),
                               relief='flat', padx=14, pady=10, spacing1=2, spacing3=5,
                               highlightthickness=1, highlightbackground=P['border'], highlightcolor=P['border'])
        self.details.config(state='disabled')
        self.details.pack(fill='both', expand=True, pady=(4, 0))
        recorder = card(self.advanced, padding=(12, 8))
        recorder.pack(fill='x', pady=(8, 0))
        top = tk.Frame(recorder, bg=P['surface'])
        top.pack(fill='x')
        ttk.Checkbutton(top, text='F8: копить снимки Texas Poker', variable=self.record_enabled,
                        style='Card.TCheckbutton', command=self.toggle_recording).pack(side='left')
        ttk.Button(top, text='Снимок в очередь', style='Card.TButton', command=self.record_snapshot).pack(side='right')
        tk.Label(recorder, textvariable=self.record_status, bg=P['surface'], fg=P['muted'], font=font(9),
                 wraplength=620, justify='left', anchor='w').pack(fill='x', pady=(6, 0))
        ttk.Button(self.advanced, text='Скриншот в базу шаблонов', command=self.collect).pack(anchor='w', pady=(8, 0))

    def toggle_advanced(self):
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.pack(fill='both', expand=True, padx=14, pady=(0, 6))
            self.advanced_button.config(text='Скрыть подробности ▴')
            self.root.geometry(f'{HUD_WIDTH}x{HUD_HEIGHT_ADVANCED}')
        else:
            self.advanced.pack_forget()
            self.advanced_button.config(text='Подробнее ▾')
            self.root.geometry(f'{HUD_WIDTH}x{HUD_HEIGHT}')

    def open_learning(self):
        from learn_window import LearnWindow
        LearnWindow(self.root, templates=self.args.templates)

    def _drag_start(self, event):
        self.drag_origin = (event.x_root-self.root.winfo_x(), event.y_root-self.root.winfo_y())

    def _drag_move(self, event):
        self.root.geometry(f'+{event.x_root-self.drag_origin[0]}+{event.y_root-self.drag_origin[1]}')

    def refresh_mode(self):
        if self.demo_mode:
            text, tone = 'ТРЕНИРОВКА', 'warn'
        elif self.pipeline is None:
            text, tone = 'НЕТ СТОЛА', 'bad'
        else:
            text, tone = 'СТОЛ ВИДЕН', 'good'
        self.mode_text.set(text)
        self.mode_badge.config(bg=tone_color(tone))

    def toggle_recording(self):
        if self.record_enabled.get():
            from capture_worker import CaptureWorker
            from global_hotkey import ScreenshotHotkey
            from screenshot_album import Album
            try:
                self.album_worker = CaptureWorker(Album(self.args.album, self.args.templates), self.args.config, 'Texas Poker')
                self.album_hotkey = ScreenshotHotkey(self.album_worker.request)
                self.album_hotkey.start()
                self.record_status.set('Регистрация F8…')
            except (OSError, RuntimeError) as exc:
                if self.album_worker:
                    self.album_worker.close()
                self.album_worker = self.album_hotkey = None
                self.record_enabled.set(False)
                self.record_status.set(f'Не удалось включить сбор: {exc}')
        else:
            if self.album_hotkey:
                self.album_hotkey.close()
            if self.album_worker:
                self.album_worker.close()
            self.album_worker = self.album_hotkey = None
            self.record_status.set('F8 выключена. Снимки остаются в альбоме — разберите их в редакторе после игры.')

    def record_snapshot(self):
        if not self.record_enabled.get():
            self.record_enabled.set(True)
            self.toggle_recording()
        if self.album_worker:
            self.album_worker.request()

    def adjust(self, delta):
        base = self.override if self.override is not None else (self.current[0].opponents if self.current else 1)
        self.override = max(1, min(8, base+delta))
        self.opponents.set(f'{self.override} · вручную')
        if self.pipeline:
            self.pipeline.override = self.override
            self.pipeline.set_signature(None)
        if self.demo_mode and self.current:
            state = self.current[0]
            self.submit_demo(replace(state, opponents=self.override))
        elif not self.demo_mode:
            self.current = None
            self.redraw()

    def auto(self):
        self.override = None
        self.opponents.set('авто')
        if self.pipeline:
            self.pipeline.override = None
            self.pipeline.set_signature(None)
        if not self.demo_mode:
            self.current = None
            self.redraw()

    def demo(self):
        self.demo_mode = True
        self.logger.end('переход к тренажеру')
        # Scenarios deliberately cover flushes, wheel gutshots, sets, preflop,
        # river ties and multiway; no deck contains duplicate cards.
        scenarios = [
            (('Ah', 'Kh'), ('Qh', 'Jh', '2c'), 30000, 10000, 2),
            (('9s', '8s'), ('7d', '6c', 'Kh'), 12000, 4000, 1),
            (('Ac', 'Kd'), ('Qh', '7s', '2d'), 9000, 3000, 3),
            (('5c', '5h'), ('5d', 'Ks', '2s', 'Js'), 20000, 5000, 2),
            (('Ah', '4h'), ('2s', '3c', 'Kd'), 4000, 1000, 1),
            (('As', 'Ad'), (), 1500, 500, 4),
            (('2c', '3d'), ('As', 'Ks', 'Qs', 'Js', 'Ts'), 10000, 5000, 2)]
        hero, board, pot, call, opponents = random.choice(scenarios)
        state = TableState(hero, board, pot, 100000, call, self.override or opponents, 100000)
        self.submit_demo(state)

    def submit_demo(self, state):
        self.demo_token += 1
        token = self.demo_token
        self.current = None
        self.redraw()
        self.status.set('ТЕСТ: сначала прикиньте свой шанс и сравните с порогом колла. Расчёт…')
        def work():
            try:
                self.demo_results.put((token, state, self.coach.analyze(state), None))
            except Exception as exc:
                self.demo_results.put((token, state, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.draw_cards(state)
        self.pot_line.set(self.pot_text(state))
        self.opponents.set(f'{state.opponents} · ' + ('вручную' if self.override else 'тест'))

    def live(self):
        if not self.pipeline:
            self.status.set('Нет захвата. Сначала python main.py --calibrate, затем перезапустите --run.')
            return
        self.demo_mode = False
        self.demo_token += 1
        self.logger.end('возврат к столу')
        self.current = None
        if self.last_live and self.last_live[0] == self.pipeline.token and self.pipeline.signature is not None:
            self.current = self.last_live[1:]
            self.safe_log(lambda: self.logger.observe(*self.current))
        self.redraw()
        self.status.set('Режим стола: ждём два одинаковых распознанных кадра подряд.')

    def collect(self):
        frame = self.pipeline.snapshot() if self.pipeline else None
        if frame is None:
            self.status.set('Нет кадра экрана. Запустите --collect после калибровки.')
            return
        from calibrator import Collector
        def capture():
            import mss
            with mss.mss() as sct:
                return grab(sct, self.config)
        dialog = Collector(self.root, frame, self.args.templates, self.config['rois'], capture=capture)
        def done():
            dialog.destroy()
            self.pipeline.reload.set()
        dialog.protocol('WM_DELETE_WINDOW', done)

    @staticmethod
    def pot_text(state):
        return pot_line(state)

    def clear_cards(self):
        for child in self.cards.winfo_children():
            child.destroy()

    def draw_cards(self, state):
        self.clear_cards()
        self._card_group('Ваши карты', state.hero, 2, '?')
        tk.Frame(self.cards, bg=P['border'], width=1).pack(side='left', fill='y', padx=14)
        self._card_group('Борд', state.board, 5, '·')

    def _card_group(self, title, cards, slots, placeholder):
        group = tk.Frame(self.cards, bg=P['surface'])
        group.pack(side='left', anchor='n')
        tk.Label(group, text=title, bg=P['surface'], fg=P['muted'], font=font(9, 'bold'), anchor='w').pack(fill='x')
        row = tk.Frame(group, bg=P['surface'])
        row.pack(anchor='w', pady=(4, 0))
        for index in range(slots):
            if index < len(cards):
                code = cards[index]
                tk.Label(row, text=card_text(code), bg=P['card_face'], fg=SUIT_COLORS[code[1]],
                         font=font(17, 'bold'), width=3, padx=4, pady=6).pack(side='left', padx=3)
            else:
                tk.Label(row, text=placeholder, bg=P['surface_alt'], fg=P['muted'],
                         font=font(17, 'bold'), width=3, padx=4, pady=6).pack(side='left', padx=3)

    def set_stats(self, state, result=None, hidden=False):
        if hidden or result is None:
            for key in self.STAT_KEYS:
                self.stat_values[key].set('?' if hidden else '—')
                self.stat_hints[key].set('прикиньте сами' if hidden else STAT_HINTS[key])
                self.stat_labels[key].config(foreground=P['text'])
            return
        equity = result.equity.equity*100
        if state.call is None or result.pot_odds is None:
            rows = {'equity': (f'около {equity:.0f}%', STAT_HINTS['equity'], 'text'),
                    'odds': ('сумма не видна', 'сравните шанс с долей колла вручную', 'text')}
        elif state.call == 0:
            rows = {'equity': (f'около {equity:.0f}%', STAT_HINTS['equity'], 'text'),
                    'odds': ('колла нет', 'вы ничего не доплачиваете', 'text')}
        else:
            need = result.pot_odds
            tone = 'good' if equity > need else 'bad'
            rows = {'equity': (f'около {equity:.0f}%', STAT_HINTS['equity'], tone),
                    'odds': (f'от {need:.0f}%', STAT_HINTS['odds'], 'text')}
        for key, (value, hint, tone) in rows.items():
            self.stat_values[key].set(value)
            self.stat_hints[key].set(hint)
            self.stat_labels[key].config(foreground=tone_color(tone))

    def explanation(self, result):
        outs = ' '.join(card_text(code) for code in result.draws.outs) or 'нет'
        return (f'{result.explanation}\n\nСтартовая рука: {result.preflop}\n\n'
                f'Карты, которые улучшат руку (аутсы): {outs}\n\n'
                f'Выгода колла (EV): {signed_money(result.ev, fmt)}. '
                'Значение терминов — в разделе «Уроки и словарь».')

    def redraw(self):
        hidden = bool(self.current and self.demo_mode and self.hide_answer.get())
        if not self.current:
            self.clear_cards()
            self.made.set('Ваша рука: —')
            self.pot_line.set('')
            self.set_stats(None)
            tone = 'muted'
            if self.demo_mode:
                self.recommendation.set('Тестовая раздача: расчёт…')
                self.summary.set('Сначала прикиньте сами: сильна ли рука и выгоден ли колл. Ответ появится через секунду.')
                text = 'Подробный расчёт появится после тестовой раздачи.'
            else:
                self.recommendation.set('Пока нет ответа')
                self.summary.set('Подсказка появится, когда карты и числа распознаны уверенно: '
                                 'нужны два одинаковых кадра подряд.')
                text = 'Здесь появятся подробные расчёты: шансы, дро и выгода колла.'
        else:
            state, result = self.current
            self.draw_cards(state)
            self.opponents.set(f'{state.opponents} · ' + ('вручную' if self.override else 'авто'))
            self.made.set(f'Ваша рука: {result.made}')
            self.pot_line.set(self.pot_text(state))
            if hidden:
                self.set_stats(state, None, hidden=True)
                self.recommendation.set('Ответ скрыт')
                self.summary.set('Прикиньте сами: какой у вас шанс и нужен ли колл. '
                                 'Снимите галочку «Тренировка», чтобы проверить себя.')
                tone = 'muted'
                text = 'Ответ скрыт в режиме тренировки.'
            else:
                verdict = make_verdict(state, result)
                self.set_stats(state, result)
                self.recommendation.set(verdict.headline)
                self.summary.set(f'{verdict.summary}\n{verdict.caveat}')
                tone = verdict.tone
                text = self.explanation(result)
        self.reco_label.config(fg=tone_color(tone))
        self.set_details(text)
        self.refresh_mode()

    def set_details(self, text):
        self.details.config(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', text)
        self.details.config(state='disabled')

    def poll(self):
        if self.closed:
            return
        if self.album_hotkey:
            if self.album_hotkey.ready.is_set() and not getattr(self.album_hotkey, 'announced', False):
                self.album_hotkey.announced = True
                self.record_status.set('F8 готова — снимки Texas Poker сохраняются в альбом.')
            while not self.album_hotkey.errors.empty():
                self.record_status.set(self.album_hotkey.errors.get_nowait())
        if self.album_worker:
            while not self.album_worker.events.empty():
                kind, value = self.album_worker.events.get_nowait()
                self.record_status.set(f'Снимок сохранён в альбом ({value[:8]}…)' if kind == 'saved' else value)
        if self.pipeline:
            while True:
                try:
                    event = self.pipeline.events.get_nowait()
                except queue.Empty:
                    break
                kind, token, *data = event
                if token != self.pipeline.token:
                    continue
                if kind == 'result':
                    state, result = data
                    self.last_live = token, state, result
                    if not self.demo_mode:
                        self.current = state, result
                        self.safe_log(lambda: self.logger.observe(state, result))
                        self.redraw()
                elif kind == 'status' and not self.demo_mode:
                    readings, status = data
                    self.status.set(status)
                    unsure = [short_name(n) for n, r in readings.items()
                              if n.startswith(('hero', 'board')) and r.status == 'unknown']
                    self.confidence.set('Распознавание: карты видны уверенно' if not unsure
                                        else 'Программа не уверена в: ' + ', '.join(unsure))
                    if self.pipeline.signature is None:
                        self.current = None
                        self.redraw()
                    # End of a hand only after a sustained, confident empty hero.
                    empty = all(readings.get(n) and readings[n].status == 'empty' for n in ('hero1', 'hero2'))
                    if empty:
                        if self.empty_since is None:
                            self.empty_since = time.monotonic()
                        elif time.monotonic()-self.empty_since >= 1:
                            self.safe_log(self.logger.end)
                    else:
                        self.empty_since = None
                elif kind == 'error' and not self.demo_mode:
                    self.status.set('Ошибка: '+data[0])
                    self.current = None
                    self.redraw()
        while True:
            try:
                token, state, result, error = self.demo_results.get_nowait()
            except queue.Empty:
                break
            if not self.demo_mode or token != self.demo_token:
                continue
            if error:
                self.status.set(error)
            else:
                self.current = state, result
                self.safe_log(lambda: self.logger.observe(state, result, 'demo'))
                self.status.set('ТЕСТ: сравните свой ответ с подсказкой. Это не распознавание экрана.')
                self.confidence.set('Распознавание не используется: карты заданы для тренировки')
                self.redraw()
        self.root.after(100, self.poll)

    def safe_log(self, action):
        try:
            action()
        except OSError as exc:
            self.status.set(f'Ошибка записи истории: {exc}')

    def close(self):
        self.closed = True
        self.record_enabled.set(False)
        self.toggle_recording()
        if self.pipeline:
            self.pipeline.close()
        self.safe_log(self.logger.end)
        self.root.destroy()

    def run(self):
        self.root.mainloop()
