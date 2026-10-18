"""Exercise countdown state transitions with a fake Tk loop, without a display.

This verifies orchestration, not native window/compositor behavior.
"""
import importlib.util
import sys
from types import SimpleNamespace

import pytest

from setup_support import ROOT


class Window:
    def __init__(self, parent=None):
        self.parent = parent
        self.children = []
        self.exists = True
        self.visibility = 'normal'
        self.protocols = {}
        self.tasks = {}
        self.counter = 0
        if parent:
            parent._root().children.append(self)

    def _root(self):
        return self.parent._root() if self.parent else self

    def winfo_children(self):
        return self.children

    def winfo_exists(self):
        return self.exists

    def state(self):
        return self.visibility

    def withdraw(self):
        self.visibility = 'withdrawn'

    def deiconify(self):
        self.visibility = 'normal'

    def iconify(self):
        self.visibility = 'iconic'

    def destroy(self):
        self.exists = False

    def title(self, text):
        self.caption = text

    def attributes(self, *args):
        self.attrs = args

    def protocol(self, name, callback):
        self.protocols[name] = callback

    def transient(self, parent):
        self.transient_parent = parent

    def grab_set(self):
        self.grabbed = True

    def after(self, delay, callback):
        self.counter += 1
        self.tasks[self.counter] = callback
        return self.counter

    def after_cancel(self, timer):
        self.tasks.pop(timer, None)

    def drain(self):
        while self.tasks:
            key = next(iter(self.tasks))
            self.tasks.pop(key)()


class Widget:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def pack(self, **kwargs):
        self.pack_args = kwargs


class Variable:
    def set(self, text):
        self.text = text


def load_fake_tk(monkeypatch):
    errors = []
    tk = SimpleNamespace(Toplevel=Window, StringVar=Variable, Label=Widget, Button=Widget,
                         messagebox=SimpleNamespace(showerror=lambda *a, **k: errors.append(a)))
    monkeypatch.setitem(sys.modules, 'tkinter', tk)
    spec = importlib.util.spec_from_file_location('isolated_capture_ui', ROOT/'capture_ui.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, errors


@pytest.mark.parametrize('fail', [False, True])
def test_hide_capture_restore(monkeypatch, fail):
    module, errors = load_fake_tk(monkeypatch)
    root = Window()
    root.withdraw()  # --collect runs with a hidden root and visible Toplevel.
    owner = Window(root)
    snapshots, accepted = [], []

    def capture():
        snapshots.append((root.state(), owner.state()))
        if fail:
            raise RuntimeError('capture unavailable')
        return 'image'

    module.fresh_capture(owner, capture, accepted.append)
    assert root._capture_busy
    root.drain()
    assert snapshots == [('withdrawn', 'withdrawn')]
    assert root.state() == 'withdrawn'
    assert owner.state() == 'normal'
    assert not root._capture_busy
    assert accepted == ([] if fail else ['image'])
    assert bool(errors) == fail


def test_cancel_and_ignore_duplicate(monkeypatch):
    module, errors = load_fake_tk(monkeypatch)
    root, accepted = Window(), []
    module.fresh_capture(root, lambda: 'image', accepted.append)
    module.fresh_capture(root, lambda: 'other image', accepted.append)
    assert len(root.children) == 1
    countdown = root.children[0]
    countdown.protocols['WM_DELETE_WINDOW']()
    root.drain()
    assert not root._capture_busy
    assert not accepted
    assert not errors
