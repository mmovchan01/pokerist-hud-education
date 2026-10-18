"""Desktop control panel, no terminal commands needed after installation."""
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from setup_support import ROOT, launcher_command


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Pokerist — настройка и запуск')
        self.root.geometry('760x760')
        self.root.minsize(650, 620)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.child = None
        self.log = None
        self.log_path = None
        self.buttons = []
        self.title = tk.StringVar(value='Texas Poker')
        self.status = tk.StringVar()
        self.instructions = tk.StringVar(value='Откройте стол в игре. Для первой настройки нажмите «1. Разметить стол».')
        ttk.Label(self.root, text='Pokerist • помощник настройки', font=('Arial', 18, 'bold')).pack(pady=15)
        ttk.Label(self.root, textvariable=self.instructions, wraplength=670, justify='left').pack(fill='x', padx=20)
        ttk.Label(self.root, text='Windows: уникальная часть заголовка окна игры (необязательно).\nЕсли заполнить, клиентская область будет выбрана автоматически.', justify='left').pack(anchor='w', padx=20, pady=(12, 2))
        ttk.Entry(self.root, textvariable=self.title).pack(fill='x', padx=20)
        modes = [
            ('record', 'Сбор снимков во время игры — F8'),
            ('label', 'Редактор накопленных снимков — выбрать карты из списка'),
            ('profile', '★ Профиль по вашим скриншотам — выбрать только область игры'),
            ('calibrate', '1. Разметить стол / исправить зоны'),
            ('collect', '2. Собрать шаблоны карт и цифр'),
            ('check', '3. Проверить один кадр'),
            ('run', '4. Запустить HUD'),
            ('demo', 'Тренажёр без игры')]
        for mode, label in modes:
            button = ttk.Button(self.root, text=label, command=lambda m=mode: self.launch(m))
            button.pack(fill='x', padx=20, pady=5)
            self.buttons.append(button)
        ttk.Button(self.root, text='Открыть папку проекта / отчёты captures', command=self.open_folder).pack(fill='x', padx=20, pady=5)
        ttk.Label(self.root, textvariable=self.status, wraplength=670, justify='left').pack(fill='x', padx=20, pady=10)
        ttk.Label(self.root, text='Помощник не внедряется в игру и не нажимает игровые кнопки.\nВо время отсчёта переключитесь на стол. После снимка вернётся окно настройки.', wraplength=670, justify='left').pack(fill='x', padx=20)
        self.refresh_status()
        self.root.after(300, self.poll)

    def refresh_status(self):
        exists = (ROOT/'config.json').exists()
        count = sum(1 for _ in (ROOT/'templates'/'card').glob('*/*.png'))
        self.status.set(f'config.json: {"есть" if exists else "ещё нет"}; образцов карт: {count}.\n'
                        'Наличие файлов не гарантирует точность — используйте проверку кадра.')

    def launch(self, mode):
        if self.child:
            messagebox.showinfo('Окно уже открыто', 'Сначала закройте открытый калибратор, сборщик, проверку или HUD.', parent=self.root)
            return
        if mode in ('collect', 'check', 'run') and not (ROOT/'config.json').exists():
            messagebox.showinfo('Сначала разметка', 'Начните с кнопки «1. Разметить стол».', parent=self.root)
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
            self.instructions.set('Закройте открытое окно помощника, чтобы вернуться к панели. Снимки хранятся в captures/inbox/, ошибки — logs/.')
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
