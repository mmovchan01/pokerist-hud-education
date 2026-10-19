"""Normalized geometry and screen capture, independent of the Tk event loop."""
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def pixels(self, width, height):
        x, y = round(self.x * width), round(self.y * height)
        return x, y, max(1, round(self.w * width)), max(1, round(self.h * height))

    def crop(self, image):
        x, y, w, h = self.pixels(image.shape[1], image.shape[0])
        return image[y:y+h, x:x+w].copy()

    def as_list(self):
        return [self.x, self.y, self.w, self.h]


def load_config(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('version') != 1:
        raise ValueError('Unsupported config version; recalibrate')
    for name, values in data['rois'].items():
        if len(values) != 4 or not all(isinstance(v, (int, float)) for v in values):
            raise ValueError(f'Invalid ROI: {name}')
        x, y, w, h = values
        if not all(math.isfinite(v) for v in values) or min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.001 or y+h > 1.001:
            raise ValueError(f'ROI outside client area: {name}')
    for name in ('hero1', 'hero2', 'pot', 'stack', 'call', *[f'board{i}' for i in range(1, 6)]):
        if name not in data['rois']:
            raise ValueError(f'Missing ROI: {name}')
    region = data.get('capture', {})
    if any(not isinstance(region.get(k), int) for k in ('left', 'top', 'width', 'height')) or min(region['width'], region['height']) < 20:
        raise ValueError('Invalid capture region; recalibrate')
    if not .250 <= data.get('interval', .275) <= .300:
        raise ValueError('Capture interval must be 250–300ms')
    if not 0 < data.get('confidence', .84) <= 1 or not 0 <= data.get('margin', .04) < 1:
        raise ValueError('Invalid confidence / margin')
    return data


def window_rect(title):
    """Track native client area on Windows, including movement and resize.

    Other OSes use the manually selected desktop rectangle, deliberately not
    pretending to track a window by matching hard-coded pixels.
    """
    import sys
    if sys.platform != 'win32' or not title:
        return None
    from windows_capture import find_window
    return find_window(title)[2]


def enable_dpi():
    import sys
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def grab(sct, config):
    import sys
    if sys.platform == 'win32' and config.get('window_title'):
        from windows_capture import capture_window
        return capture_window(config['window_title'])[0]
    region = window_rect(config.get('window_title')) or config['capture']
    if region['width'] < 20 or region['height'] < 20:
        raise RuntimeError('Окно свёрнуто или имеет нулевой размер')
    return np.asarray(sct.grab(region))[:, :, :3].copy()


def preprocess(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    contrast = cv2.createCLAHE(2.0, (4, 4)).apply(gray)
    return cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
