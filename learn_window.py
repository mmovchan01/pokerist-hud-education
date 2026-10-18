"""Learning window: lessons with quizzes, a plain-language glossary, and the recognition report.

Works without a configured table, so a new user can start learning right away.
Can be opened from the control panel, from the HUD, or on its own.
"""
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from lessons import LESSONS, PASS_MARK, QUESTIONS_PER_LESSON, Progress, make_session
from plain import GLOSSARY
from recognition_report import build_report, format_report
from setup_support import ROOT
from ui_text import card_text
from ui_theme import PALETTE as P, SUIT_COLORS, apply_theme, card, font

PROGRESS_PATH = ROOT/'progress.json'
TEMPLATES_PATH = ROOT/'templates'


class LearnWindow:
    def __init__(self, master=None, progress_path=PROGRESS_PATH, templates=TEMPLATES_PATH):
        if master is None:
            self.root = tk.Tk()
            apply_theme(self.root)
        else:
            self.root = tk.Toplevel(master)
        self.root.title('Pokerist — уроки и словарь')
        self.root.geometry('860x720')
        self.root.minsize(700, 580)
        self.root.configure(bg=P['bg'])
        self.progress = Progress(progress_path)
        self.templates = Path(templates)
        self.lesson = None
        self.session = []
        self.index = 0
        self.correct = 0
        self.answered = False

        head = tk.Frame(self.root, bg=P['bg'])
        head.pack(fill='x', padx=18, pady=(16, 0))
        tk.Label(head, text='Уроки и словарь', bg=P['bg'], fg=P['accent'], font=font(18, 'bold')).pack(anchor='w')
        tk.Label(head, text='Не нужно знать покер заранее: каждый термин объяснён простыми словами.',
                 bg=P['bg'], fg=P['muted'], font=font(10), anchor='w').pack(fill='x')

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=14, pady=14)
        self.lessons_tab = tk.Frame(self.notebook, bg=P['bg'])
        self.glossary_tab = tk.Frame(self.notebook, bg=P['bg'])
        self.recognition_tab = tk.Frame(self.notebook, bg=P['bg'])
        self.notebook.add(self.lessons_tab, text='  Уроки  ')
        self.notebook.add(self.glossary_tab, text='  Словарь  ')
        self.notebook.add(self.recognition_tab, text='  Распознавание  ')
        self._build_lessons()
        self._build_glossary()
        self._build_recognition()
        self.show_lesson_list()

    def run(self):
        self.root.mainloop()

    # --- lessons -----------------------------------------------------------
    def _build_lessons(self):
        self.lesson_list = tk.Frame(self.lessons_tab, bg=P['bg'])
        tk.Label(self.lesson_list, text=f'Каждый урок — {QUESTIONS_PER_LESSON} вопросов. Чтобы пройти урок, '
                 f'нужно ответить верно минимум на {PASS_MARK}. Настройка стола не нужна.',
                 bg=P['bg'], fg=P['muted'], font=font(10), wraplength=760, justify='left', anchor='w').pack(fill='x', pady=(0, 10))
        self.lesson_status = {}
        for lesson in LESSONS:
            box = card(self.lesson_list, padding=(16, 12))
            box.pack(fill='x', pady=5)
            row = tk.Frame(box, bg=P['surface'])
            row.pack(fill='x')
            tk.Label(row, text=lesson.title, bg=P['surface'], fg=P['text'], font=font(12, 'bold'), anchor='w').pack(side='left')
            status = tk.Label(row, text='', bg=P['surface'], fg=P['muted'], font=font(9), anchor='e')
            status.pack(side='right')
            self.lesson_status[lesson.id] = status
            tk.Label(box, text=lesson.intro, bg=P['surface'], fg=P['muted'], font=font(10), wraplength=720,
                     justify='left', anchor='w').pack(fill='x', pady=(4, 8))
            ttk.Button(box, text='Начать урок', style='Accent.TButton',
                       command=lambda item=lesson: self.start_lesson(item)).pack(anchor='w')

        self.quiz = tk.Frame(self.lessons_tab, bg=P['bg'])
        self.quiz_title = tk.Label(self.quiz, text='', bg=P['bg'], fg=P['accent'], font=font(11, 'bold'), anchor='w')
        self.quiz_title.pack(fill='x')
        self.quiz_prompt = tk.Label(self.quiz, text='', bg=P['bg'], fg=P['text'], font=font(15, 'bold'),
                                    anchor='w', justify='left', wraplength=740)
        self.quiz_prompt.pack(fill='x', pady=(8, 6))
        self.quiz_cards = tk.Frame(self.quiz, bg=P['bg'])
        self.quiz_cards.pack(fill='x', pady=(0, 10))
        self.options_frame = tk.Frame(self.quiz, bg=P['bg'])
        self.options_frame.pack(fill='x')
        self.feedback = tk.Label(self.quiz, text='', bg=P['bg'], fg=P['text'], font=font(12, 'bold'), anchor='w')
        self.feedback.pack(fill='x', pady=(12, 0))
        self.explanation = tk.Label(self.quiz, text='', bg=P['bg'], fg=P['muted'], font=font(10), anchor='w',
                                    justify='left', wraplength=740)
        self.explanation.pack(fill='x', pady=(6, 0))
        self.next_button = ttk.Button(self.quiz, text='Дальше', style='Accent.TButton', command=self.next_question)
        self.next_button.pack(anchor='w', pady=(16, 0))

        self.result = tk.Frame(self.lessons_tab, bg=P['bg'])
        self.result_text = tk.Label(self.result, text='', bg=P['bg'], fg=P['text'], font=font(14, 'bold'),
                                    anchor='w', justify='left', wraplength=740)
        self.result_text.pack(fill='x', pady=(12, 6))
        self.result_hint = tk.Label(self.result, text='', bg=P['bg'], fg=P['muted'], font=font(10), anchor='w',
                                    justify='left', wraplength=740)
        self.result_hint.pack(fill='x')
        buttons = tk.Frame(self.result, bg=P['bg'])
        buttons.pack(anchor='w', pady=(16, 0))
        ttk.Button(buttons, text='Пройти ещё раз', command=lambda: self.start_lesson(self.lesson)).pack(side='left')
        ttk.Button(buttons, text='К списку уроков', command=self.show_lesson_list).pack(side='left', padx=8)
        self.refresh_lesson_status()

    def refresh_lesson_status(self):
        for lesson in LESSONS:
            best = self.progress.best(lesson.id)
            if self.progress.passed(lesson.id):
                text, fg = f'✓ пройден · лучший результат {best} из {QUESTIONS_PER_LESSON}', P['good']
            elif best:
                text, fg = f'не пройден · лучший результат {best} из {QUESTIONS_PER_LESSON}', P['warn']
            else:
                text, fg = 'ещё не проходили', P['muted']
            self.lesson_status[lesson.id].config(text=text, fg=fg)

    def _show(self, frame):
        for other in (self.lesson_list, self.quiz, self.result):
            other.pack_forget()
        frame.pack(fill='both', expand=True, padx=18, pady=10)

    def show_lesson_list(self):
        self.refresh_lesson_status()
        self._show(self.lesson_list)

    def start_lesson(self, lesson):
        self.lesson = lesson
        self.session = make_session(lesson.id)
        self.index = 0
        self.correct = 0
        self._show_question()
        self._show(self.quiz)

    def _show_question(self):
        question = self.session[self.index]
        self.answered = False
        self.quiz_title.config(text=f'{self.lesson.title} · вопрос {self.index+1} из {len(self.session)}')
        self.quiz_prompt.config(text=question.prompt)
        for child in self.quiz_cards.winfo_children():
            child.destroy()
        for title, codes in (('Ваши карты', question.hero), ('Стол', question.board)):
            if codes:
                group = tk.Frame(self.quiz_cards, bg=P['bg'])
                group.pack(side='left', padx=(0, 24), anchor='n')
                tk.Label(group, text=title, bg=P['bg'], fg=P['muted'], font=font(9, 'bold')).pack(anchor='w')
                row = tk.Frame(group, bg=P['bg'])
                row.pack(anchor='w', pady=(4, 0))
                for code in codes:
                    tk.Label(row, text=card_text(code), bg=P['card_face'], fg=SUIT_COLORS.get(code[1], P['text']),
                             font=font(16, 'bold'), width=3, pady=6).pack(side='left', padx=3)
        for child in self.options_frame.winfo_children():
            child.destroy()
        self.option_buttons = []
        for number, option in enumerate(question.options):
            button = ttk.Button(self.options_frame, text=option, command=lambda n=number: self.answer(n))
            button.pack(fill='x', pady=4)
            self.option_buttons.append(button)
        self.feedback.config(text='Выберите ответ', fg=P['muted'])
        self.explanation.config(text='')
        self.next_button.config(text='Дальше' if self.index+1 < len(self.session) else 'Итог')
        self.next_button.state(['disabled'])

    def answer(self, number):
        if self.answered:
            return
        self.answered = True
        question = self.session[self.index]
        right = number == question.correct
        self.correct += right
        self.feedback.config(text='Верно!' if right else f'Не совсем. Верный ответ: {question.options[question.correct]}',
                             fg=P['good'] if right else P['bad'])
        self.explanation.config(text=question.explanation)
        self.next_button.state(['!disabled'])

    def next_question(self):
        self.index += 1
        if self.index < len(self.session):
            self._show_question()
            return
        try:
            self.progress.record(self.lesson.id, self.correct)
            saved = ''
        except OSError as exc:
            saved = f'\nПрогресс не сохранён: {exc}'
        passed = self.correct >= PASS_MARK
        self.result_text.config(text=f'Верно: {self.correct} из {len(self.session)}. ' +
                                ('Урок пройден!' if passed else 'Урок ещё не пройден.'),
                                fg=P['good'] if passed else P['warn'])
        self.result_hint.config(text=('Переходите к следующему уроку или словарю.' if passed else
                                      'Попробуйте ещё раз: вопросы каждый раз новые.') + saved)
        self._show(self.result)

    # --- glossary -----------------------------------------------------------
    def _build_glossary(self):
        body = tk.Frame(self.glossary_tab, bg=P['bg'])
        body.pack(fill='both', expand=True, padx=12, pady=12)
        self.terms = tk.Listbox(body, width=28, bg=P['field'], fg=P['text'], selectbackground=P['select'],
                                selectforeground=P['text'], font=font(11), relief='flat', activestyle='none',
                                highlightthickness=0)
        self.terms.pack(side='left', fill='y')
        for name, _ in GLOSSARY:
            self.terms.insert('end', name)
        self.terms.bind('<<ListboxSelect>>', self._show_term)
        self.definition = tk.Text(body, wrap='word', bg=P['surface'], fg=P['text'], font=font(12), relief='flat',
                                  padx=18, pady=14, spacing3=6)
        self.definition.pack(side='left', fill='both', expand=True, padx=(12, 0))
        self.terms.selection_set(0)
        self._show_term()

    def _show_term(self, _event=None):
        selection = self.terms.curselection()
        index = selection[0] if selection else 0
        name, text = GLOSSARY[index]
        self.definition.config(state='normal')
        self.definition.delete('1.0', 'end')
        self.definition.insert('1.0', f'{name}\n\n{text}')
        self.definition.config(state='disabled')

    # --- recognition -------------------------------------------------------
    def _build_recognition(self):
        top = tk.Frame(self.recognition_tab, bg=P['bg'])
        top.pack(fill='x', padx=12, pady=(12, 6))
        tk.Label(top, text='Что программа уже узнаёт на ваших образцах', bg=P['bg'], fg=P['text'],
                 font=font(12, 'bold'), anchor='w').pack(side='left')
        ttk.Button(top, text='Проверить снова', command=self.refresh_report).pack(side='right')
        self.report = tk.Text(self.recognition_tab, wrap='word', bg=P['field'], fg=P['text'], font=font(11),
                              relief='flat', padx=16, pady=12, spacing3=4)
        self.report.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        self.refresh_report()

    def refresh_report(self):
        try:
            text = format_report(build_report(self.templates))
        except (OSError, ValueError) as exc:
            text = f'Не удалось прочитать образцы: {exc}'
        self.report.config(state='normal')
        self.report.delete('1.0', 'end')
        self.report.insert('1.0', text+'\n\nКак добавить новые карты: откройте «Редактор накопленных снимков» на '
                           'панели запуска, выберите карту на снимке и подпишите её. Для каждой карты нужно 2–3 примера '
                           'при разном свете.')
        self.report.config(state='disabled')


if __name__ == '__main__':
    LearnWindow().run()
