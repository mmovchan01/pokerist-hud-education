"""One registered Windows shortcut; no keyboard hooks or key logging."""
import queue
import sys
import threading


class ScreenshotHotkey:
    def __init__(self, callback, key='F8'):
        if key not in ('F8', 'F9', 'F10'):
            raise ValueError('Поддерживаются F8, F9, F10')
        self.key, self.callback = key, callback
        self.errors = queue.Queue()
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.thread_id = None
        self.thread = threading.Thread(target=self._run, name='screenshot-hotkey', daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        registered = False
        try:
            if sys.platform != 'win32':
                raise RuntimeError('Глобальная клавиша доступна только в Windows; используйте кнопку снимка.')
            import ctypes as ct
            from ctypes import wintypes as wt
            user, kernel = ct.windll.user32, ct.windll.kernel32
            user.RegisterHotKey.argtypes = [wt.HWND, ct.c_int, wt.UINT, wt.UINT]
            user.RegisterHotKey.restype = wt.BOOL
            user.UnregisterHotKey.argtypes = [wt.HWND, ct.c_int]
            user.GetMessageW.argtypes = [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
            user.GetMessageW.restype = ct.c_int
            kernel.GetCurrentThreadId.restype = wt.DWORD
            self.thread_id = kernel.GetCurrentThreadId()
            virtual_key = 0x70+int(self.key[1:])-1
            if not user.RegisterHotKey(None, 1, 0x4000, virtual_key):  # MOD_NOREPEAT
                raise RuntimeError(f'{self.key} уже занята. Выберите другую клавишу или используйте кнопку.')
            registered = True
            self.ready.set()
            message = wt.MSG()
            while not self.stopping.is_set():
                status = user.GetMessageW(ct.byref(message), None, 0, 0)
                if status == -1:
                    raise RuntimeError('Ошибка очереди горячей клавиши Windows')
                if status == 0:
                    break
                if message.message == 0x312:  # WM_HOTKEY
                    self.callback()
        except Exception as exc:
            self.errors.put(str(exc))
        finally:
            self.ready.set()
            if registered:
                user.UnregisterHotKey(None, 1)

    def close(self):
        self.stopping.set()
        if self.thread_id and sys.platform == 'win32':
            import ctypes as ct
            from ctypes import wintypes as wt
            user = ct.windll.user32
            user.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
            user.PostThreadMessageW(self.thread_id, 0x12, 0, 0)  # WM_QUIT
        if self.thread.is_alive():
            self.thread.join(timeout=1)
