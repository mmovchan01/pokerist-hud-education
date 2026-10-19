"""Smoke-test the Tk windows with a recording fake tkinter (no display needed).

This catches Python-level mistakes in the HUD/launcher code paths: bad names,
missing attributes, wrong state transitions. It does NOT prove pixel layout;
run the app on a desktop to check how it looks.
"""
import importlib.util
import sys
import time
from types import ModuleType, SimpleNamespace


from setup_support import ROOT
from vision import TableState


class Var:
    def __init__(self, master=None, value=None, **kwargs):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *args, **kwargs):
        return 'trace'


class Widget:
    def __init__(self, master=None, *args, **kwargs):
        self.master, self.options = master, dict(kwargs)
        self.children, self.destroyed = [], False
        if master is not None and hasattr(master, 'children'):
            master.children.append(self)

    def winfo_children(self):
        return [child for child in self.children if not child.destroyed]

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_x(self):
        return 0

    def winfo_y(self):
        return 0

    def config(self, **kwargs):
        self.options.update(kwargs)

    configure = config

    def destroy(self):
        self.destroyed = True

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return lambda *args, **kwargs: None  # pack/grid/bind/after/title/...


class PhotoImage(Widget):
    def width(self):
        return 10

    def height(self):
        return 10


class Style(Widget):
    def theme_names(self):
        return ['clam', 'default']

    def theme_use(self, name=None):
        return name

    def configure(self, style, **kwargs):
        return None

    def map(self, style, **kwargs):
        return None


def fake_tkinter(monkeypatch):
    tk = ModuleType('tkinter')
    ttk = ModuleType('tkinter.ttk')
    for name in ('Frame', 'Label', 'Button', 'Checkbutton', 'Entry', 'Combobox', 'Scrollbar', 'Treeview', 'Notebook'):
        setattr(ttk, name, type(name, (Widget,), {}))
    ttk.Style = Style
    for name in ('Tk', 'Frame', 'Label', 'Button', 'Canvas', 'Text', 'Toplevel', 'Listbox', 'Entry', 'Checkbutton'):
        setattr(tk, name, type(name, (Widget,), {}))
    tk.Tk.attributes = lambda self, *args: None
    tk.StringVar = tk.BooleanVar = tk.IntVar = Var
    tk.PhotoImage = PhotoImage
    tk.ttk = ttk
    tk.simpledialog = SimpleNamespace(askstring=lambda *a, **k: None)
    tk.filedialog = SimpleNamespace(askopenfilenames=lambda *a, **k: ())
    tk.TclError = type('TclError', (Exception,), {})
    tk.messagebox = SimpleNamespace(showinfo=lambda *a, **k: None, showerror=lambda *a, **k: None,
                                    askyesno=lambda *a, **k: True)
    monkeypatch.setitem(sys.modules, 'tkinter', tk)
    monkeypatch.setitem(sys.modules, 'tkinter.ttk', ttk)
    monkeypatch.setitem(sys.modules, 'tkinter.messagebox', tk.messagebox)
    monkeypatch.setitem(sys.modules, 'tkinter.simpledialog', tk.simpledialog)
    monkeypatch.setitem(sys.modules, 'tkinter.filedialog', tk.filedialog)
    return tk


def load(monkeypatch, name):
    fake_tkinter(monkeypatch)
    spec = importlib.util.spec_from_file_location(f'isolated_{name}', ROOT/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hud_demo_flow_and_states(monkeypatch, tmp_path):
    hud_module = load(monkeypatch, 'hud_overlay')
    args = SimpleNamespace(demo=False, iterations=2000, seed=3, config=tmp_path/'missing.json',
                           templates=tmp_path/'templates', album=tmp_path/'album', window_title='', delay=0)
    hud = hud_module.HUD(args)  # no config -> falls back to the demo table
    hud.logger.path = tmp_path/'hands_log.csv'  # never write the real log from tests
    assert hud.demo_mode
    assert hud.mode_text.get() == 'ТРЕНИРОВКА'
    assert not hud.advanced_visible

    state = TableState(('Ac', 'Kd'), ('Qh', '7s', '2d'), 9000, 100000, 3000, 3, 100000)
    hud.submit_demo(state)
    deadline = time.monotonic() + 60
    while hud.current is None and time.monotonic() < deadline:
        hud.poll()
        time.sleep(.05)
    assert hud.current is not None
    assert hud.recommendation.get() in ('Колл выгоден', 'Пас: колл не окупается', 'Решение почти безразлично')
    assert hud.summary.get()
    assert hud.stat_values['equity'].get().startswith('около ')
    assert hud.stat_values['odds'].get().startswith('от ')

    hud.hide_answer.set(True)
    hud.redraw()
    assert hud.stat_values['equity'].get() == '?'
    assert hud.recommendation.get() == 'Ответ скрыт'

    hud.hide_answer.set(False)
    hud.redraw()
    assert hud.recommendation.get() != 'Ответ скрыт'
    hud.toggle_advanced()
    assert hud.advanced_visible and hud.advanced_button.options.get('text') == 'Скрыть подробности ▴'
    hud.toggle_advanced()
    assert not hud.advanced_visible
    hud.adjust(1)
    assert hud.opponents.get().endswith('вручную')
    hud.auto()
    assert hud.opponents.get() == 'авто'
    hud.live()
    assert 'Нет захвата' in hud.status.get()
    hud.open_learning()  # opens the lessons window as a child of the HUD
    hud.close()


def test_learn_window_runs_lesson_and_saves_progress(monkeypatch, tmp_path):
    learn_module = load(monkeypatch, 'learn_window')
    progress_file = tmp_path/'progress.json'
    window = learn_module.LearnWindow(None, progress_path=progress_file, templates=tmp_path/'none')
    lesson = learn_module.LESSONS[1]
    window.start_lesson(lesson)
    assert len(window.session) == learn_module.QUESTIONS_PER_LESSON

    # One answer per question: a second click must not change the score.
    window.answer(window.session[0].correct)
    window.answer(window.session[0].correct)
    assert window.correct == 1 and window.answered
    window.next_question()
    for question in window.session[1:]:
        window.answer(question.correct)
        window.next_question()
    assert window.correct == learn_module.QUESTIONS_PER_LESSON  # every answer was the right option
    assert window.progress.best(lesson.id) == learn_module.QUESTIONS_PER_LESSON
    assert progress_file.exists()
    assert window.progress.passed(lesson.id) == (window.correct >= learn_module.PASS_MARK)
    window.refresh_report()  # no templates yet: the window must still render text, not crash


def test_launcher_builds_and_reports_next_step(monkeypatch):
    launcher_module = load(monkeypatch, 'desktop_launcher')
    launcher = launcher_module.Launcher()
    assert set(launcher.badges) == {'calibrate', 'collect', 'check', 'run'}
    assert launcher.next_step.get()
    assert all(key in launcher.chips for key in ('config', 'cards', 'digits'))
    launcher.close()


def test_collector_uses_readable_dropdown_values(monkeypatch):
    import numpy as np
    from pathlib import Path

    class FakePhoto:
        def __init__(self, image):
            self.size = image.size

        def width(self):
            return self.size[0]

        def height(self):
            return self.size[1]

    # PIL.ImageTk needs a real Tk interpreter, so replace just that module.
    monkeypatch.setitem(sys.modules, 'PIL.ImageTk', SimpleNamespace(PhotoImage=FakePhoto))
    calibrator = load(monkeypatch, 'calibrator')
    root = sys.modules['tkinter'].Tk()
    image = np.zeros((120, 160, 3), np.uint8)
    rois = {'hero1': [.1, .1, .2, .3], 'pot': [.5, .5, .2, .1], 'opp1': [.7, .7, .1, .1]}
    dialog = calibrator.Collector(root, image, Path('unused-templates'), rois, capture=None)
    assert dialog.roi_text.get().startswith('hero1 — ')
    assert dialog.kind_text.get() == 'card · карта'
    dialog.pick_kind('glyph')
    assert dialog.kind.get() == 'glyph'
    assert dialog.kind_text.get() == 'glyph · цифра или знак'
    dialog.next_roi()
    dialog.next_roi()
    assert dialog.roi_name.get() == 'opp1' and dialog.kind.get() == 'back'
