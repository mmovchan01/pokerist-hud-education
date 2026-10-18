"""Exercise editor result delivery without requiring a native Tk display.

These tests check controller/view calls, not Windows fonts or visual layout.
"""
import importlib.util
from pathlib import Path
import queue
import sys
from types import SimpleNamespace

import cv2
import pytest

from editor_assistant import EditorAssistant
from profile_support import BUILTIN
from review_state import ReviewState


class Variable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Widget:
    def __init__(self):
        self.options = {}
        self.stopped = False

    def configure(self, **options):
        self.options.update(options)

    def stop(self):
        self.stopped = True


class Tree:
    def __init__(self):
        self.rows = {}

    def get_children(self):
        return list(self.rows)

    def delete(self, key):
        del self.rows[key]

    def insert(self, *args, **kwargs):
        self.rows[str(len(self.rows))] = kwargs


@pytest.fixture
def editor_class(monkeypatch):
    fake_tk = SimpleNamespace(ttk=SimpleNamespace(), messagebox=SimpleNamespace(), filedialog=SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'tkinter', fake_tk)
    monkeypatch.setitem(sys.modules, 'color_choice', SimpleNamespace(ColorChoice=None))
    theme = dict(install_theme=None, header=None, open_folder=None, ScrollFrame=None, INK='', MUTED='', SURFACE='')
    monkeypatch.setitem(sys.modules, 'ui_theme', SimpleNamespace(**theme))
    path = Path(__file__).parents[1]/'album_editor.py'
    spec = importlib.util.spec_from_file_location('isolated_album_editor', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AlbumEditor


def editor(editor_class):
    view = editor_class.__new__(editor_class)
    view.closed = False
    view.review = ReviewState()
    view.record = {'id': 'frame', 'revision': 0, 'items': {'hero1': {'status': 'pending'}}}
    view.item_id = 'hero1'
    view.pending_rect = None
    view.auto_skip, view.variant = Variable(False), Variable(False)
    view.results = queue.Queue()
    view.busy = Widget()
    view.coverage, view.advice_title, view.advice_detail, view.advice_meta = [Variable() for _ in range(4)]
    view.badge = Widget()
    view.candidates = Tree()
    view.sample_preview = Widget()
    view.selected, view.previews, view.scheduled = [], [], []
    view.set_choices = view.selected.append
    view.refilter = lambda: None
    view.set_preview = lambda *args: view.previews.append(args)
    view.root = SimpleNamespace(after=lambda *args: view.scheduled.append(args))
    return view


def report():
    image = cv2.imread(str(next((BUILTIN/'templates/card/Ks').glob('*.png'))))
    return EditorAssistant(BUILTIN/'templates').inspect(image)


def test_manual_choice_does_not_lose_recognition_evidence(editor_class):
    view = editor(editor_class)
    ticket = view.review.begin('frame', 'hero1', 0)
    view.review.select()
    result = report()
    view.results.put((ticket, result, None))
    view.poll()
    assert view.review.phase == 'ready'
    assert view.advice_title.get() == result.title
    assert view.candidates.rows
    assert view.previews
    assert not view.selected  # user choice was not overwritten
    assert view.busy.stopped
    assert view.scheduled  # polling continues


def test_default_mode_suggests_but_does_not_jump(editor_class):
    view = editor(editor_class)
    ticket = view.review.begin('frame', 'hero1', 0)
    view.results.put((ticket, report(), None))
    view.poll()
    assert view.selected == ['Ks']
    assert view.record['items']['hero1']['status'] == 'pending'


def test_stale_background_job_cannot_replace_next_card(editor_class):
    view = editor(editor_class)
    old = view.review.begin('frame', 'hero1', 0)
    view.review.begin('another-frame', 'hero2', 0)
    view.results.put((old, report(), None))
    view.poll()
    assert not view.selected
    assert not view.candidates.rows
    assert view.advice_title.get() is None


def test_opt_in_auto_accept_does_not_export_a_template(editor_class):
    view = editor(editor_class)
    view.auto_skip.set(True)
    accepted = []
    advanced = []
    view.album = SimpleNamespace(accept_known=lambda *args: accepted.append(args) or view.record)
    view.advance = lambda: advanced.append(True)
    ticket = view.review.begin('frame', 'hero1', 0)
    view.results.put((ticket, report(), None))
    view.poll()
    assert accepted and advanced
    assert view.last_auto == ('frame', 'hero1')


def test_auto_accept_error_is_visible_and_polling_continues(editor_class):
    view = editor(editor_class)
    view.auto_skip.set(True)

    def fail(*args):
        raise OSError('disk full')

    errors = []
    view.album = SimpleNamespace(accept_known=fail)
    view.reset_advice = lambda *args: errors.append(args)
    ticket = view.review.begin('frame', 'hero1', 0)
    view.results.put((ticket, report(), None))
    view.poll()
    assert 'disk full' in errors[0][1]
    assert view.scheduled
