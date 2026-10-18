"""Asynchronous native-window capture to the offline inbox (no Tk dependency)."""
import queue
import threading

from profile_support import load_profile
from screen import load_config
from windows_capture import capture_window


class CaptureWorker:
    def __init__(self, album, config_path, title, capture=capture_window):
        self.album, self.config_path, self.title, self.capture = album, config_path, title, capture
        self.events = queue.Queue()
        self.jobs = queue.Queue(1)
        self.stop = threading.Event()
        self.busy = threading.Lock()
        self.thread = threading.Thread(target=self._run, name='album-capture', daemon=True)
        self.thread.start()

    def request(self):
        if self.stop.is_set():
            return
        if not self.busy.acquire(blocking=False):
            self.events.put(('status', 'Предыдущий снимок ещё сохраняется — повторите нажатие.'))
            return
        self.jobs.put_nowait(True)

    def _run(self):
        while not self.stop.is_set():
            try:
                self.jobs.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                # Freeze the configuration BEFORE acquiring the frame.
                suggested = True
                config = None
                warning = ''
                try:
                    config = load_config(self.config_path)
                    same_window = self.title.casefold() in config.get('window_title', '').casefold()
                    suggested = not same_window
                    rois = config['rois']
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    rois = load_profile()['rois']
                    warning = f'Нет пригодной калибровки: {exc}'
                image, source = self.capture(self.title)
                if config is not None and not warning:
                    reference = config['capture']['width']/config['capture']['height']
                    if abs((image.shape[1]/image.shape[0])/reference-1) > .025:
                        suggested = True
                        warning = 'Соотношение сторон отличается от калибровки — проверьте рамки.'
                source.update(roi_warning=warning, requested_window=self.title)
                record = self.album.add(image, rois, source, suggested=suggested)
                self.events.put(('saved', record['id']))
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                self.busy.release()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=.5)
