"""Desktop control panel: the next step is always obvious, advanced tools are separate."""
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from setup_support import ROOT, launcher_command
from ui_theme import PALETTE as P, apply_theme, card, font

# Button titles match the instructions in README/QUICKSTART on purpose.
STEPS = [
    ('calibrate', '1. Разметить стол', 'Выделите окно игры и зоны: карты, банк, стек, кнопки соперников.', 'Начать'),
    ('collect', '2. Собрать шаблоны', 'Подпишите свои карты и цифры: программа учится на ваших скриншотах.', 'Собрать'),
    ('check', '3. Проверить один кадр', 'Один снимок стола: зелёные рамки — распознано, красные — нет.', 'Проверить'),
    ('run', '4. Запустить HUD', 'Окно с эквити, pot odds и рекомендацией поверх игры.', 'Запустить'),
]
EXTRAS = [
    ('record', 'Сбор снимков во время игры — F8', 'Нажимайте F8 в игре: окно Texas Poker сохранится в альбом без паузы.', 'Включить сбор'),
    ('label', 'Редактор накопленных снимков', 'Выберите карту из списка для каждого снимка. Можно работать после игры.', 'Открыть редактор'),
    ('profile', '★ Профиль по вашим скриншотам', 'Готовые зоны и образцы для стола Pokerist 3D 1280×719.', 'Применить профиль'),
    ('demo', 'Тренажёр без игры', 'Учебные раздачи: сначала оцените шансы сами, потом сверьте расчёт.', 'Открыть тренажёр'),
]
PRIMARY_MODE = 'run'


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        apply_theme(self.root)
        self.root.title('Pokerist — настройка и запуск')
        self.root.geometry('860x860')
        self.root.minsize(720, 700)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.child = None
        self.log = None
        self.log_path = None
        self.buttons = []
        self.badges = {}
        self.title = tk.StringVar(value='Texas Poker')
        self.status = tk.StringVar()
        self.next_step = tk.StringVar()
        self.chips = {key: tk.StringVar() for key in ('config', 'cards', 'digits')}
        self._build()
        self.refresh_status()
        self.root.after(300, self.poll)

    def _build(self):
        head = tk.Frame(self.root, bg=P['bg'])
        head.pack(fill='x', padx=26, pady=(22, 0))
        tk.Label(head, text='Pokerist HUD', bg=P['bg'], fg=P['accent'], font=font(22, 'bold')).pack(anchor='w')
        tk.Label(head, text='Учебный помощник: считает шансы по вашему экрану. Не внедряется в игру и не нажимает кнопки.',
                 bg=P['bg'], fg=P['muted'], font=font(10), wraplength=780, justify='left').pack(anchor='w', pady=(2, 0))

        banner = card(self.root, padding=(16, 10))
        banner.pack(fill='x', padx=26, pady=(16, 0))
        tk.Label(banner, text='СЛЕДУЮЩИЙ ШАГ', bg=P['surface'], fg=P['muted'], font=font(9, 'bold')).pack(anchor='w')
        tk.Label(banner, textvariable=self.next_step, bg=P['surface'], fg=P['text'], font=font(12, 'bold'),
                 wraplength=760, justify='left', anchor='w').pack(fill='x', pady=(2, 0))

        chips = tk.Frame(self.root, bg=P['bg'])
        chips.pack(fill='x', padx=26, pady=12)
        for column, key in enumerate(('config', 'cards', 'digits')):
            chips.grid_columnconfigure(column, weight=1, uniform='chips')
            chip = card(chips, padding=(12, 8))
            chip.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else 6, 0))
            tk.Label(chip, textvariable=self.chips[key], bg=P['surface'], fg=P['text'], font=font(10, 'bold'),
                     anchor='w', justify='left').pack(fill='x')

        steps = card(self.root, padding=(18, 14))
        steps.pack(fill='x', padx=26)
        tk.Label(steps, text='ПЕРВАЯ НАСТРОЙКА', bg=P['surface'], fg=P['accent'], font=font(9, 'bold')).pack(anchor='w', pady=(0, 6))
        for number, (mode, title, description, action) in enumerate(STEPS, start=1):
            self._row(steps, mode, title, description, action, number=str(number), primary=mode == PRIMARY_MODE)

        extras = card(self.root, padding=(18, 14))
        extras.pack(fill='x', padx=26, pady=12)
        tk.Label(extras, text='ДОПОЛНИТЕЛЬНО', bg=P['surface'], fg=P['accent'], font=font(9, 'bold')).pack(anchor='w', pady=(0, 6))
        for mode, title, description, action in EXTRAS:
            self._row(extras, mode, title, description, action)

        settings = card(self.root, padding=(18, 12))
        settings.pack(fill='x', padx=26)
        tk.Label(settings, text='Заголовок окна игры (Windows, необязательно)', bg=P['surface'], fg=P['text'],
                 font=font(10, 'bold')).pack(anchor='w')
        ttk.Entry(settings, textvariable=self.title).pack(fill='x', pady=(6, 4))
        tk.Label(settings, text='Уникальная часть заголовка окна. Если заполнить, клиентская область найдётся сама. '
                                'На Linux/macOS оставьте пустым.',
                 bg=P['surface'], fg=P['muted'], font=font(9), wraplength=760, justify='left', anchor='w').pack(fill='x')

        footer = tk.Frame(self.root, bg=P['bg'])
        footer.pack(fill='x', padx=26, pady=(14, 18), side='bottom')
        ttk.Button(footer, text='Открыть папку проекта и отчёты', command=self.open_folder).pack(side='left')
        tk.Label(footer, textvariable=self.status, bg=P['bg'], fg=P['muted'], font=font(9), wraplength=540,
                 justify='left', anchor='w').pack(side='left', padx=14, fill='x', expand=True)

    def _row(self, parent, mode, title, description, action, number=None, primary=False):
        row = tk.Frame(parent, bg=P['surface'])
        row.pack(fill='x', pady=5)
        row.grid_columnconfigure(1, weight=1)
        if number is not None:
            badge = tk.Label(row, text=number, bg=P['accent'] if primary else P['surface_alt'],
                             fg=P['accent_text'] if primary else P['text'], font=font(12, 'bold'), width=3, pady=4)
            badge.grid(row=0, column=0, rowspan=2, sticky='ns', padx=(0, 12))
            self.badges[mode] = badge
        tk.Label(row, text=title, bg=P['surface'], fg=P['text'], font=font(11, 'bold'), anchor='w').grid(row=0, column=1, sticky='ew')
        tk.Label(row, text=description, bg=P['surface'], fg=P['muted'], font=font(9), anchor='w', justify='left',
                 wraplength=540).grid(row=1, column=1, sticky='ew')
        button = ttk.Button(row, text=action, style='Accent.TButton' if primary else 'TButton',
                            command=lambda m=mode: self.launch(m))
        button.grid(row=0, column=2, rowspan=2, sticky='e', padx=(12, 0))
        self.buttons.append(button)

    def refresh_status(self):
        has_config = (ROOT/'config.json').exists()
        cards = sum(1 for _ in (ROOT/'templates'/'card').glob('*/*.png'))
        digits = sum(1 for _ in (ROOT/'templates'/'glyph').glob('*/*.png'))
        self.chips['config'].set('✓ Стол размечен' if has_config else '○ Стол ещё не размечен')
        self.chips['cards'].set(f'Образцов карт: {cards}')
        self.chips['digits'].set(f'Образцов цифр: {digits}')
        if not has_config:
            self.next_step.set('1. Разметить стол — выделите окно игры и зоны на снимке.')
        elif cards == 0:
            self.next_step.set('2. Собрать шаблоны — подпишите свои карты, чтобы программа их узнавала.')
        else:
            self.next_step.set('3–4. Проверить кадр и запустить HUD. Для нового стола повторите шаг 1.')
        # Steps 1..4: finished ones are green, the next recommended one is mint.
        next_index = 0 if not has_config else (1 if cards == 0 else 3)
        for index, (mode, _, _, _) in enumerate(STEPS):
            badge = self.badges[mode]
            if index < next_index:
                badge.config(bg=P['good'], fg=P['accent_text'])
            elif index == next_index:
                badge.config(bg=P['accent'], fg=P['accent_text'])
            else:
                badge.config(bg=P['surface_alt'], fg=P['text'])
        self.status.set('Наличие файлов не гарантирует точность. Перед игрой проверьте кадр (шаг 3).')

    def launch(self, mode):
        if self.child:
            messagebox.showinfo('Окно уже открыто', 'Сначала закройте открытый калибратор, сборщик, проверку или HUD.', parent=self.root)
            return
        if mode in ('collect', 'check', 'run') and not (ROOT/'config.json').exists():
            messagebox.showinfo('Сначала разметка', 'Начните с шага «1. Разметить стол».', parent=self.root)
            return
        if mode in ('calibrate', 'profile') and (ROOT/'config.json').exists():
            if not messagebox.askyesno('Редактирование зон', 'Открыть редактор? Профиль заменит зоны только после сохранения; обычная разметка загрузит текущие.\nПредыдущий config.json будет сохранён в config.json.bak.', parent=self.root):
                return
        try:
            logs = ROOT/'logs'
            logs.mkdir(exist_ok=True)
            self.log_path = logs/f'{mode}_{time.time_ns()}.log'
            self.log = self.log_path.open('w', encoding='utf-8')
            env = dict(os.environ, PYTHONIOENCODING='utf-8')
            self.child = subprocess.Popen(launcher_command(sys.executable, mode, self.title.get()),
                                          cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT, env=env)
            self.status.set('Открыто дочернее окно. Закройте его штатно, чтобы вернуться к панели. Снимки: captures/inbox/, ошибки: logs/.')
            for button in self.buttons:
                button.config(state='disabled')
            self.root.iconify()
        except OSError as exc:
            if self.log:
                self.log.close()
                self.log = None
            messagebox.showerror('Запуск', str(exc), parent=self.root)

    def poll(self):
        if self.child and self.child.poll() is not None:
            code = self.child.returncode
            self.child = None
            if self.log:
                self.log.close()
                self.log = None
            for button in self.buttons:
                button.config(state='normal')
            self.root.deiconify()
            self.refresh_status()
            if code:
                tail = self.log_path.read_text(encoding='utf-8', errors='replace')[-2500:]
                messagebox.showerror('Программа завершилась с ошибкой', f'{tail}\n\nПолный журнал: {self.log_path}', parent=self.root)
        self.root.after(300, self.poll)

    def open_folder(self):
        try:
            if sys.platform == 'win32':
                os.startfile(str(ROOT))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(ROOT)])
            else:
                subprocess.Popen(['xdg-open', str(ROOT)])
        except OSError as exc:
            messagebox.showinfo('Папка проекта', f'{ROOT}\n{exc}', parent=self.root)

    def close(self):
        if self.child and self.child.poll() is None:
            messagebox.showinfo('Открыто дочернее окно', 'Сначала штатно закройте калибратор / HUD, чтобы сохранить данные.', parent=self.root)
            return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    Launcher().run()
