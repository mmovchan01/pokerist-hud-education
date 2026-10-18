"""Tk stays on main thread; capture/CV and Monte Carlo have separate workers."""
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk

from hand_history import HandLogger
from poker_coach import Coach, fmt
from screen import enable_dpi, grab, load_config
from vision import Recognizer, Stabilizer, TableState, TemplateBank


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
    def __init__(self, args):
        enable_dpi()
        self.args = args
        self.root = tk.Tk()
        self.root.title('Pokerist • учебный HUD')
        self.pinned = tk.BooleanVar(value=True)
        self.root.attributes('-topmost', self.pinned.get())
        self.root.attributes('-alpha', .93)
        self.root.geometry('660x780+30+30')
        self.root.minsize(580, 500)
        self.root.configure(bg='#12202d')
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
        self.album_worker = self.album_hotkey = None
        self.record_enabled = tk.BooleanVar(value=False)
        self.record_status = tk.StringVar(value='F8 выключена; снимки можно разбирать после сессии.')
        self.teaching = tk.BooleanVar(value=True)
        self.hide_answer = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Загрузка…')
        self.opponents = tk.StringVar(value='Оппоненты: авто')
        self.metrics = tk.StringVar(value='—')
        self.confidence = tk.StringVar(value='Confidence: —')
        self._build()
        if not args.demo:
            try:
                self.config = load_config(args.config)
                import sys
                if sys.platform == 'win32':
                    self.config['window_title'] = args.window_title or self.config.get('window_title') or 'Texas Poker'
                self.pipeline = Pipeline(self.config, args.templates, self.coach)
                self.pipeline.start()
                # Place beside the calibrated client, not on the captured table.
                c = self.config['capture']
                x = c['left']+c['width']+8
                if x+660 <= self.root.winfo_screenwidth():
                    self.root.geometry(f'+{x}+{max(0, c["top"])}')
            except Exception as exc:
                self.status.set(f'Захват не запущен: {exc}. Доступна тестовая раздача.')
                self.demo_mode = True
        if args.demo:
            self.demo()
        self.root.after(100, self.poll)

    def _build(self):
        header = tk.Label(self.root, text='♠  POKER COACH   •   ОБУЧЕНИЕ', bg='#12202d', fg='#5ee8ba', font=('Arial', 16, 'bold'), pady=12)
        header.pack(fill='x')
        header.bind('<ButtonPress-1>', lambda e: setattr(self, 'drag_origin', (e.x_root-self.root.winfo_x(), e.y_root-self.root.winfo_y())))
        header.bind('<B1-Motion>', lambda e: self.root.geometry(f'+{e.x_root-self.drag_origin[0]}+{e.y_root-self.drag_origin[1]}'))
        bar = ttk.Frame(self.root)
        bar.pack(fill='x', padx=10)
        ttk.Button(bar, text='−', width=3, command=lambda: self.adjust(-1)).pack(side='left')
        ttk.Label(bar, textvariable=self.opponents).pack(side='left', padx=8)
        ttk.Button(bar, text='+', width=3, command=lambda: self.adjust(1)).pack(side='left')
        ttk.Button(bar, text='Авто', command=self.auto).pack(side='left', padx=5)
        ttk.Checkbutton(bar, text='Обучение', variable=self.teaching, command=self.redraw).pack(side='right')
        ttk.Checkbutton(self.root, text='Тренировка: скрыть расчёт (снимите галочку для ответа)', variable=self.hide_answer, command=self.redraw).pack(anchor='w', padx=12, pady=5)
        ttk.Checkbutton(self.root, text='Закрепить HUD поверх всех окон', variable=self.pinned,
                        command=lambda: self.root.attributes('-topmost', self.pinned.get())).pack(anchor='w', padx=12)
        recorder = ttk.Frame(self.root)
        recorder.pack(fill='x', padx=12)
        ttk.Checkbutton(recorder, text='F8: копить снимки Texas Poker', variable=self.record_enabled, command=self.toggle_recording).pack(side='left')
        ttk.Button(recorder, text='Снимок в очередь', command=self.record_snapshot).pack(side='right')
        tk.Label(self.root, textvariable=self.record_status, bg='#12202d', fg='#a5bfcc', wraplength=620).pack(fill='x', padx=12)
        self.cards = tk.Frame(self.root, bg='#12202d', height=70)
        self.cards.pack(fill='x', padx=12, pady=12)
        tk.Label(self.root, textvariable=self.metrics, justify='left', anchor='w', bg='#12202d', fg='white', font=('Arial', 13), wraplength=620).pack(fill='x', padx=12)
        tk.Label(self.root, textvariable=self.confidence, bg='#12202d', fg='#a5bfcc', wraplength=620, justify='left').pack(fill='x', padx=12, pady=6)
        self.details = tk.Text(self.root, wrap='word', height=18, bg='#1b3041', fg='#e9f4f7', font=('Arial', 11), relief='flat', padx=12, pady=12)
        self.details.config(state='disabled')
        controls = ttk.Frame(self.root)
        controls.pack(side='bottom', fill='x', padx=10, pady=8)
        ttk.Button(controls, text='Тестовая раздача', command=self.demo).pack(side='left')
        ttk.Button(controls, text='Вернуться к столу', command=self.live).pack(side='left', padx=4)
        ttk.Button(controls, text='Скриншот в базу шаблонов', command=self.collect).pack(side='left')
        tk.Label(self.root, textvariable=self.status, bg='#12202d', fg='#ffc979', justify='left', wraplength=630).pack(side='bottom', fill='x', padx=10, pady=5)
        self.details.pack(fill='both', expand=True, padx=10)

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
            self.record_status.set('F8 выключена; снимки остаются в альбоме.')

    def record_snapshot(self):
        if not self.record_enabled.get():
            self.record_enabled.set(True)
            self.toggle_recording()
        if self.album_worker:
            self.album_worker.request()

    def adjust(self, delta):
        base = self.override if self.override is not None else (self.current[0].opponents if self.current else 1)
        self.override = max(1, min(8, base+delta))
        self.opponents.set(f'Оппоненты: {self.override} (вручную)')
        if self.pipeline:
            self.pipeline.override = self.override
            self.pipeline.set_signature(None)
        if self.demo_mode and self.current:
            state = self.current[0]
            from dataclasses import replace
            self.submit_demo(replace(state, opponents=self.override))
        elif not self.demo_mode:
            self.current = None
            self.redraw()

    def auto(self):
        self.override = None
        self.opponents.set('Оппоненты: авто')
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
        self.status.set('ТЕСТ: сначала оцените ауты и Call / (Pot + Call) в уме. Расчёт…')
        def work():
            try:
                self.demo_results.put((token, state, self.coach.analyze(state), None))
            except Exception as exc:
                self.demo_results.put((token, state, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.draw_cards(state)
        self.metrics.set(f'ТЕСТ • банк {fmt(state.pot)} • колл {fmt(state.call)} • оппонентов {state.opponents}')

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
        self.status.set('Режим экрана; ожидается стабильное состояние')

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

    def draw_cards(self, state):
        for child in self.cards.winfo_children():
            child.destroy()
        colors = {'h': '#db3548', 'd': '#2778d0', 'c': '#15834a', 's': '#202830'}
        symbols = {'h': '♥', 'd': '♦', 'c': '♣', 's': '♠'}
        for title, cards in [('Вы', state.hero), ('Борд', state.board)]:
            tk.Label(self.cards, text=title, bg='#12202d', fg='white').pack(side='left', padx=4)
            for card in cards:
                tk.Label(self.cards, text=card[0]+symbols[card[1]], bg='#eff5f6', fg=colors[card[1]], font=('Arial', 18, 'bold'), padx=4, pady=8).pack(side='left', padx=2)

    def redraw(self):
        if not self.current:
            self.metrics.set('Нет актуального расчёта — ожидается валидный стабильный кадр')
            for child in self.cards.winfo_children():
                child.destroy()
            text = 'Рекомендации при неуверенном распознавании скрыты.'
        else:
            state, result = self.current
            self.draw_cards(state)
            self.opponents.set(f'Оппоненты: {state.opponents}' + (' (вручную)' if self.override else ''))
            spr = f'{result.spr:.1f}' if result.spr is not None else 'н/д'
            ev_pct = f'{result.ev_pot_percent:+.1f}%' if result.ev_pot_percent is not None else 'н/д'
            self.metrics.set(f'{result.made}\nЭквити {result.equity.equity*100:.1f}% ±{result.equity.error95*100:.1f} п.п.  |  Pot Odds {result.pot_odds:.1f}%\nEV {fmt(result.ev)} ({ev_pct} банка)  |  SPR {spr}\nБанк {fmt(state.pot)} • Колл {fmt(state.call)} • Стек {fmt(state.stack)}')
            text = result.recommendation
            if self.teaching.get():
                text = (result.explanation+'\n\n'+result.preflop+'\n\nКарты-ауты: '+(' '.join(result.draws.outs) or 'нет')+
                        '\n\nНе складывайте ауты разных дро: пересечения уже исключены. Попасть в аут ≠ выиграть раздачу.')
        if self.current and self.demo_mode and self.hide_answer.get():
            state, _ = self.current
            self.metrics.set(f'ТЕСТ • банк {fmt(state.pot)} • колл {fmt(state.call)} • стек {fmt(state.stack)} • оппонентов {state.opponents}')
            text = 'Посчитайте ауты (без дублей), шансы банка и порог безубыточности. Снимите галочку «скрыть расчёт», чтобы проверить ответ.'
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
                self.record_status.set('Снимок в альбоме: '+value[:12] if kind == 'saved' else value)
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
                    self.confidence.set('Confidence: '+ ' | '.join(f'{n} {r.value if r.value is not None else r.status} {r.confidence*100:.0f}%' for n, r in readings.items() if n.startswith('hero') or n.startswith('board')))
                    if self.pipeline.signature is None:
                        self.current = None
                        self.redraw()
                    # End of a hand only after a sustained, confident empty hero.
                    empty = all(readings.get(n) and readings[n].status == 'empty' for n in ('hero1', 'hero2'))
                    if empty:
                        if not hasattr(self, 'empty_since') or self.empty_since is None:
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
                self.status.set('ТЕСТ — сравните свой ответ с расчётом. Не является результатом распознавания экрана.')
                self.confidence.set('Confidence: тестовые карты заданы; CV не используется')
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
