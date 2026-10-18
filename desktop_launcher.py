"""Task-oriented desktop dashboard: capture → label → coach."""
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from setup_support import ROOT, launcher_command
from ui_theme import install_theme, header, open_folder, ScrollFrame
from review_helpers import template_inventory
from screenshot_album import Album
from screen import load_config


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Poker Lab · Главная')
        self.root.geometry(f'900x{min(810, self.root.winfo_screenheight()-70)}')
        self.root.minsize(740, 600)
        install_theme(self.root)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.child = self.log = self.log_path = None
        self.buttons = []
        self.title = tk.StringVar(value='Texas Poker')
        self.status = tk.StringVar()
        self.instructions = tk.StringVar(value='Начните со сбора снимков. Для этого калибровка не нужна.')
        self.stats = tk.StringVar()
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        header(self.root, 'Ваш покерный тренажёр', 'Собирайте примеры. Разбирайте карты. Учитесь понимать математику.').grid(row=0, column=0, sticky='ew')
        target = ttk.Frame(self.root, padding=(22, 12))
        target.grid(row=1, column=0, sticky='ew')
        ttk.Label(target, text='Окно игры', style='Heading.TLabel').pack(side='left')
        ttk.Entry(target, textvariable=self.title, width=28).pack(side='left', padx=12)
        ttk.Label(target, text='Название приложения Windows', style='Muted.TLabel').pack(side='left')
        tabs = ttk.Notebook(self.root)
        tabs.grid(row=2, column=0, sticky='nsew', padx=18)
        home_panel, setup_panel = ScrollFrame(tabs), ScrollFrame(tabs)
        home, setup = home_panel.inner, setup_panel.inner
        diagnostics = ttk.Frame(tabs, padding=16)
        tabs.add(home_panel, text='Начать работу')
        tabs.add(setup_panel, text='Настройка стола')
        tabs.add(diagnostics, text='Состояние проекта')
        ttk.Label(home, textvariable=self.stats, style='Heading.TLabel').pack(anchor='w', pady=(0, 10))
        steps = [
            ('record', '01', 'Собрать снимки', 'Играйте и нажимайте F8. Сохраняется только окно Texas Poker. Настройка зон не обязательна.'),
            ('label', '02', 'Разобрать и подписать карты', 'Снимок, увеличенная карта и результат распознавания рядом. Помощник объясняет каждый ответ.'),
            ('run', '03', 'Открыть HUD и тренера', 'Проверьте калибровку и распознанные карты. Затем изучайте эквити, шансы банка и EV.')]
        for mode, number, title, description in steps:
            card = ttk.Frame(home, padding=14, style='Card.TFrame')
            card.pack(fill='x', pady=5)
            card.columnconfigure(1, weight=1)
            tk.Label(card, text=number, background='#ffffff', foreground='#087f68', font=('Segoe UI', 18, 'bold')).grid(row=0, column=0, rowspan=2, padx=(0, 16))
            ttk.Label(card, text=title, style='Card.TLabel', font=('Segoe UI', 12, 'bold')).grid(row=0, column=1, sticky='w')
            ttk.Label(card, text=description, style='Card.TLabel', wraplength=490).grid(row=1, column=1, sticky='w', pady=(5, 0))
            button = ttk.Button(card, text='Открыть →', style='Primary.TButton', command=lambda m=mode: self.launch(m))
            button.grid(row=0, column=2, rowspan=2, padx=(12, 0))
            self.buttons.append(button)
        self.add_button(home, 'Тренироваться без запущенной игры', 'demo')
        ttk.Label(setup, text='Один раз покажите программе, где находятся карты и числа.', style='Heading.TLabel', wraplength=760).pack(anchor='w', pady=(0, 14))
        for mode, title, description in [
            ('profile', 'Применить профиль вашего 3D-стола', 'Выделите всю игровую область один раз — обязательные зоны уже расставлены.'),
            ('calibrate', 'Исправить зоны вручную', 'Укажите отдельные карты, банк, стек и сумму колла. Предыдущий config сохраняется в .bak.'),
            ('check', 'Проверить один кадр', 'Увидите, что прочитала программа, где она ошиблась и какие данные пока неизвестны.'),
            ('collect', 'Быстро сохранить одиночный шаблон', 'Дополнительный инструмент. Для большого числа снимков удобнее редактор на главной вкладке.')]:
            self.add_button(setup, title, mode)
            ttk.Label(setup, text=description, wraplength=740, style='Muted.TLabel').pack(anchor='w', pady=(0, 12))
        home_panel.enable_wheel()
        setup_panel.enable_wheel()
        self.diagnostic_text = tk.Text(diagnostics, wrap='word', font=('Segoe UI', 11), relief='flat', padx=14, pady=14, height=10)
        self.diagnostic_text.pack(fill='both', expand=True)
        ttk.Button(diagnostics, text='Обновить состояние', command=self.refresh_status).pack(anchor='w', pady=8)
        ttk.Button(diagnostics, text='Открыть папку проекта', command=self.open_folder).pack(anchor='w')
        foot = ttk.Frame(self.root, padding=(22, 12))
        foot.grid(row=3, column=0, sticky='ew')
        ttk.Label(foot, textvariable=self.instructions, wraplength=830).pack(anchor='w')
        ttk.Label(foot, textvariable=self.status, wraplength=830, style='Muted.TLabel').pack(anchor='w', pady=(5, 0))
        self.refresh_status()
        self.root.after(300, self.poll)

    def add_button(self, parent, text, mode):
        button = ttk.Button(parent, text=text, command=lambda: self.launch(mode))
        button.pack(fill='x', pady=5)
        self.buttons.append(button)

    def refresh_status(self):
        counts, _ = template_inventory(ROOT/'templates')
        records, errors = Album(ROOT/'captures/inbox', ROOT/'templates').records()
        configuration = 'Не настроена — это не мешает собирать снимки и обучать карты.'
        configured = False
        try:
            load_config(ROOT/'config.json')
            configuration, configured = 'Готова к проверке кадра.', True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if (ROOT/'config.json').exists():
                configuration = f'Есть ошибка: {exc}. Исправьте зоны на вкладке настройки.'
        self.stats.set(f'{len(records)} снимков  ·  {len(counts)}/52 карт изучено  ·  {sum(counts.values())} образцов')
        self.status.set('Калибровка: '+('есть' if configured else 'нужна для HUD')+'  ·  Всё хранится локально')
        text = (f'Калибровка\n{configuration}\n\nРаспознавание\nЭто локальное сравнение с шаблонами, не облачный ИИ. '
                f'В базе {len(counts)} из 52 карт. Если база пуста, в редакторе есть установка 13 стартовых карт. '
                'Новые карты нужно подписывать вручную. Уверенность — похожесть, не вероятность.\n\n'
                f'Снимки\n{len(records)} кадров; повреждённых записей: {len(errors)}.\n'
                f'Папка: {ROOT/"captures/inbox"}\n\n'
                'Windows 11\nF8 и PrintWindow требуют проверки на вашем ПК. Чёрные кадры отклоняются; '
                'для игры и HUD лучше безрамочный режим.\n\nЖурналы ошибок лежат в logs/.')
        if errors:
            text += '\n\nПервая ошибка альбома: '+errors[0]
        self.diagnostic_text.configure(state='normal')
        self.diagnostic_text.delete('1.0', 'end')
        self.diagnostic_text.insert('1.0', text)
        self.diagnostic_text.configure(state='disabled')

    def launch(self, mode):
        if self.child:
            messagebox.showinfo('Уже открыто', 'Сначала закройте дочернее окно, чтобы вернуться в главную панель.', parent=self.root)
            return
        if mode in ('collect', 'check', 'run'):
            try:
                load_config(ROOT/'config.json')
            except (OSError, ValueError, KeyError, TypeError):
                messagebox.showinfo('Нужна настройка стола', 'Откройте вкладку «Настройка стола» и примените профиль или разметьте зоны. Снимки и редактор доступны без этого.', parent=self.root)
                return
        if mode == 'profile' and (ROOT/'config.json').exists() and not messagebox.askyesno('Изменить профиль?', 'Новые зоны заменят текущие только после сохранения. Предыдущий config.json будет сохранён в .bak.', parent=self.root):
            return
        try:
            logs = ROOT/'logs'
            logs.mkdir(exist_ok=True)
            self.log_path = logs/f'{mode}_{time.time_ns()}.log'
            self.log = self.log_path.open('w', encoding='utf-8')
            self.child = subprocess.Popen(launcher_command(sys.executable, mode, self.title.get()), cwd=ROOT,
                                          stdout=self.log, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            self.instructions.set('После закрытия рабочего окна вы вернётесь сюда. Данные сохраняются локально.')
            for button in self.buttons:
                button.configure(state='disabled')
            self.root.iconify()
        except OSError as exc:
            if self.log:
                self.log.close()
                self.log = None
            messagebox.showerror('Запуск не удался', str(exc), parent=self.root)

    def poll(self):
        if self.child and self.child.poll() is not None:
            code = self.child.returncode
            self.child = None
            if self.log:
                self.log.close()
                self.log = None
            for button in self.buttons:
                button.configure(state='normal')
            self.root.deiconify()
            self.refresh_status()
            if code:
                tail = self.log_path.read_text(encoding='utf-8', errors='replace')[-2200:]
                messagebox.showerror('Программа завершилась с ошибкой', f'{tail}\n\nЖурнал: {self.log_path}', parent=self.root)
        self.root.after(300, self.poll)

    def open_folder(self):
        try:
            open_folder(ROOT)
        except OSError as exc:
            messagebox.showerror('Папка проекта', str(exc), parent=self.root)

    def close(self):
        if self.child and self.child.poll() is None:
            messagebox.showinfo('Есть открытое окно', 'Сначала закройте рабочее окно, чтобы не потерять текущую операцию.', parent=self.root)
            return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    Launcher().run()
