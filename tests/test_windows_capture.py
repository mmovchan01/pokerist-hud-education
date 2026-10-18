"""Win32 resource/control-flow tests with fake APIs; not a Windows smoke test."""
import ctypes
from ctypes import wintypes

import numpy as np
import pytest

import windows_capture
from global_hotkey import ScreenshotHotkey


@pytest.mark.parametrize('print_success', [True, False])
def test_printwindow_client_only_and_resource_cleanup(monkeypatch, print_success):
    calls = []

    class User:
        def GetDC(self, hwnd):
            calls.append(('getdc', hwnd))
            return 100

        def PrintWindow(self, hwnd, dc, flags):
            calls.append(('print', hwnd, dc, flags))
            return print_success

        def ReleaseDC(self, hwnd, dc):
            calls.append(('release', hwnd, dc))
            return 1

    class GDI:
        def CreateCompatibleDC(self, source):
            return 200

        def CreateCompatibleBitmap(self, source, width, height):
            assert (width, height) == (80, 50)
            return 300

        def SelectObject(self, dc, obj):
            calls.append(('select', dc, obj))
            return 400

        def GetDIBits(self, dc, bitmap, start, count, buffer, header, mode):
            assert header._obj.height == -50
            assert calls[-1] == ('select', 200, 400)
            for i in range(80*50*4):
                buffer[i] = 120
            return 50

        def DeleteObject(self, bitmap):
            calls.append(('delete_bitmap', bitmap))

        def DeleteDC(self, dc):
            calls.append(('delete_dc', dc))

    monkeypatch.setattr(windows_capture, 'find_window', lambda title: (2**40, 'Texas Poker', dict(left=20, top=30, width=80, height=50)))
    monkeypatch.setattr(windows_capture, '_api', lambda: (ctypes, wintypes, User(), GDI()))
    if print_success:
        image, source = windows_capture.capture_window()
        assert image.shape == (50, 80, 3)
        assert np.all(image == 120)
        assert source['method'] == 'PrintWindow/client'
    else:
        with pytest.raises(RuntimeError, match='PrintWindow'):
            windows_capture.capture_window()
    assert ('print', 2**40, 200, 3) in calls
    assert ('delete_bitmap', 300) in calls
    assert ('delete_dc', 200) in calls
    assert ('release', 2**40, 100) in calls


def test_non_windows_no_desktop_fallback(monkeypatch):
    monkeypatch.setattr(windows_capture.sys, 'platform', 'linux')
    with pytest.raises(RuntimeError, match='Windows'):
        windows_capture.capture_window()


def test_hotkey_failures_are_reported(monkeypatch):
    import global_hotkey
    monkeypatch.setattr(global_hotkey.sys, 'platform', 'linux')
    key = ScreenshotHotkey(lambda: None)
    key.start()
    assert key.ready.wait(2)
    assert 'Windows' in key.errors.get(timeout=2)
    key.close()
    with pytest.raises(ValueError):
        ScreenshotHotkey(lambda: None, 'F1')


@pytest.mark.parametrize('fail', [False, True])
def test_live_grab_never_uses_desktop_for_bound_window(monkeypatch, fail):
    import screen
    import sys
    monkeypatch.setattr(sys, 'platform', 'win32')
    image = np.full((50, 80, 3), 100, np.uint8)

    def native(title):
        assert title == 'Texas Poker'
        if fail:
            raise RuntimeError('game not found')
        return image, {}

    class Desktop:
        def grab(self, region):
            raise AssertionError('Must not capture the desktop')

    monkeypatch.setattr(windows_capture, 'capture_window', native)
    config = dict(window_title='Texas Poker', capture=dict(left=0, top=0, width=80, height=50))
    if fail:
        with pytest.raises(RuntimeError, match='game not found'):
            screen.grab(Desktop(), config)
    else:
        assert screen.grab(Desktop(), config) is image
